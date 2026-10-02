-- Give the single existing site owner a larger personal trial allowance.
-- This is a one-time seed: future site admins do not inherit the override.
create table public.personal_trial_overrides (
    user_id uuid primary key references auth.users (id) on delete cascade,
    audit_limit integer not null check (audit_limit between 1 and 999),
    cooldown_hours integer not null check (cooldown_hours >= 0),
    granted_at timestamptz not null default now()
);

alter table public.personal_trial_overrides enable row level security;
revoke all on public.personal_trial_overrides from public, anon, authenticated;
grant all on public.personal_trial_overrides to service_role;

insert into public.personal_trial_overrides (user_id, audit_limit, cooldown_hours)
select user_id, 999, 0
  from public.site_admins
 where (select count(*) from public.site_admins) = 1
on conflict (user_id) do nothing;

create or replace function public.trial_status(p_user_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_used integer;
    v_last timestamptz;
    v_limit integer := 3;
    v_cooldown_hours integer := 24;
begin
    select o.audit_limit, o.cooldown_hours
      into v_limit, v_cooldown_hours
      from public.personal_trial_overrides o
     where o.user_id = p_user_id;
    v_limit := coalesce(v_limit, 3);
    v_cooldown_hours := coalesce(v_cooldown_hours, 24);

    select count(*)::integer, max(a.created_at)
      into v_used, v_last
      from public.audits a
     where a.created_by = p_user_id and a.workshop_id is null;
    return jsonb_build_object(
        'limit', v_limit,
        'used', v_used,
        'remaining', greatest(0, v_limit - v_used),
        'cooldown_hours', v_cooldown_hours,
        'next_available_at', case
            when v_used < v_limit and v_cooldown_hours > 0
                 and v_last > now() - make_interval(hours => v_cooldown_hours)
            then v_last + make_interval(hours => v_cooldown_hours)
            else null
        end,
        'can_submit', v_used < v_limit and (
            v_cooldown_hours = 0 or v_last is null
            or v_last <= now() - make_interval(hours => v_cooldown_hours)
        )
    );
end;
$$;

revoke all on function public.trial_status(uuid) from public, anon, authenticated;
grant execute on function public.trial_status(uuid) to service_role;

create or replace function public.submit_trial_audit(
    p_user_id uuid,
    p_client_request_id uuid,
    p_company_name text,
    p_company_domain text,
    p_country_code text,
    p_engine_commit text,
    p_methodology_version text,
    p_audit_focus text default null,
    p_input_options jsonb default '{}'::jsonb
) returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_existing uuid;
    v_used integer;
    v_last timestamptz;
    v_limit integer := 3;
    v_cooldown_hours integer := 24;
begin
    if p_user_id is null or p_client_request_id is null then
        raise exception 'user and client request ID are required' using errcode = '22023';
    end if;
    perform 1 from auth.users u where u.id = p_user_id for update;
    if not found then
        raise exception 'user not found' using errcode = '42501';
    end if;

    -- Idempotent retries remain valid after either quota boundary is reached.
    select a.id into v_existing from public.audits a
     where a.created_by = p_user_id and a.client_request_id = p_client_request_id;
    if v_existing is null then
        select o.audit_limit, o.cooldown_hours
          into v_limit, v_cooldown_hours
          from public.personal_trial_overrides o
         where o.user_id = p_user_id;
        v_limit := coalesce(v_limit, 3);
        v_cooldown_hours := coalesce(v_cooldown_hours, 24);

        select count(*)::integer, max(a.created_at)
          into v_used, v_last
          from public.audits a
         where a.created_by = p_user_id and a.workshop_id is null;
        if v_used >= v_limit then
            raise exception 'trial_total_limit' using errcode = 'P0001';
        end if;
        if v_cooldown_hours > 0
           and v_last > now() - make_interval(hours => v_cooldown_hours) then
            raise exception 'trial_daily_limit' using errcode = 'P0001';
        end if;
    end if;

    return public.submit_audit(
        p_user_id => p_user_id,
        p_client_request_id => p_client_request_id,
        p_company_name => p_company_name,
        p_company_domain => p_company_domain,
        p_country_code => p_country_code,
        p_engine_commit => p_engine_commit,
        p_methodology_version => p_methodology_version,
        p_audit_focus => p_audit_focus,
        p_input_options => p_input_options,
        p_workshop_id => null
    );
end;
$$;

revoke all on function public.submit_trial_audit(
    uuid, uuid, text, text, text, text, text, text, jsonb
) from public, anon, authenticated;
grant execute on function public.submit_trial_audit(
    uuid, uuid, text, text, text, text, text, text, jsonb
) to service_role;
