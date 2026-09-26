-- Registered trial audits are separate from anonymous workshop audits.
-- Serialize admission per Auth user so simultaneous requests cannot evade limits.
create index if not exists audits_trial_user_created_idx
    on public.audits (created_by, created_at desc)
    where workshop_id is null;

create function public.trial_status(p_user_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_used integer;
    v_last timestamptz;
begin
    select count(*)::integer, max(a.created_at)
      into v_used, v_last
      from public.audits a
     where a.created_by = p_user_id and a.workshop_id is null;
    return jsonb_build_object(
        'limit', 3,
        'used', v_used,
        'remaining', greatest(0, 3 - v_used),
        'next_available_at', case
            when v_used < 3 and v_last > now() - interval '24 hours'
            then v_last + interval '24 hours'
            else null
        end,
        'can_submit', v_used < 3 and
            (v_last is null or v_last <= now() - interval '24 hours')
    );
end;
$$;

revoke all on function public.trial_status(uuid) from public, anon, authenticated;
grant execute on function public.trial_status(uuid) to service_role;

create function public.submit_trial_audit(
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
begin
    if p_user_id is null or p_client_request_id is null then
        raise exception 'user and client request ID are required' using errcode = '22023';
    end if;
    perform 1 from auth.users u where u.id = p_user_id for update;
    if not found then
        raise exception 'user not found' using errcode = '42501';
    end if;

    -- Let the underlying function validate idempotent retries against the
    -- original payload, even after the account has reached either limit.
    select a.id into v_existing from public.audits a
     where a.created_by = p_user_id and a.client_request_id = p_client_request_id;
    if v_existing is null then
        select count(*)::integer, max(a.created_at)
          into v_used, v_last
          from public.audits a
         where a.created_by = p_user_id and a.workshop_id is null;
        if v_used >= 3 then
            raise exception 'trial_total_limit' using errcode = 'P0001';
        end if;
        if v_last > now() - interval '24 hours' then
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
