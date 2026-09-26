-- Opt-in retention for existing workshops; new workshops default to 48 hours.
-- Physical Storage deletion is performed by the trusted purge worker before
-- these functions remove database rows. No existing report is purged by this
-- migration alone.
alter table public.workshops
    add column anonymous_retention_hours integer
        check (anonymous_retention_hours between 12 and 168),
    add column purge_started_at timestamptz,
    add column purged_at timestamptz;
alter table public.workshops
    alter column anonymous_retention_hours set default 48;

create table public.workshop_purge_totals (
    workshop_id uuid primary key references public.workshops (id) on delete restrict,
    submitted_audits bigint not null default 0,
    completed_audits bigint not null default 0,
    failed_audits bigint not null default 0,
    interrupted_audits bigint not null default 0,
    cancelled_audits bigint not null default 0,
    brightdata_operations bigint not null default 0,
    brightdata_accepted bigint not null default 0,
    brightdata_confirmed_results bigint not null default 0,
    brightdata_estimated_cost_usd numeric(14, 6) not null default 0,
    updated_at timestamptz not null default now()
);

create table public.workshop_purge_users (
    user_id uuid primary key references auth.users (id) on delete cascade,
    workshop_id uuid not null references public.workshops (id) on delete restrict,
    queued_at timestamptz not null default now()
);
create index workshop_purge_users_workshop_idx
    on public.workshop_purge_users (workshop_id);

alter table public.workshop_purge_totals enable row level security;
alter table public.workshop_purge_users enable row level security;
revoke all on public.workshop_purge_totals, public.workshop_purge_users
    from public, anon, authenticated;
grant all on public.workshop_purge_totals, public.workshop_purge_users
    to service_role;

create function public.prevent_workshop_reopening_after_purge()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if old.purge_started_at is not null and (
        new.closes_at is distinct from old.closes_at
        or new.anonymous_retention_hours is distinct from old.anonymous_retention_hours
    ) then
        raise exception 'workshop retention is locked after purge begins'
            using errcode = '22023';
    end if;
    return new;
end;
$$;
create trigger workshop_purge_lock
before update on public.workshops
for each row execute function public.prevent_workshop_reopening_after_purge();

create or replace function public.admin_list_workshops(p_user_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_workspaces jsonb;
    v_workshops jsonb;
begin
    select coalesce(jsonb_agg(jsonb_build_object(
        'id', w.id, 'name', w.name
    ) order by w.created_at), '[]'::jsonb)
      into v_workspaces
      from public.workspaces w
      join public.workspace_members m on m.workspace_id = w.id
     where w.kind = 'team' and m.user_id = p_user_id
       and m.role in ('owner', 'admin');

    select coalesce(jsonb_agg(jsonb_build_object(
        'id', s.id,
        'organizer_workspace_id', s.organizer_workspace_id,
        'slug', s.slug,
        'name', s.name,
        'opens_at', s.opens_at,
        'closes_at', s.closes_at,
        'anonymous_retention_hours', s.anonymous_retention_hours,
        'purge_started_at', s.purge_started_at,
        'purged_at', s.purged_at,
        'max_total_audits', s.max_total_audits,
        'max_concurrent_audits', s.max_concurrent_audits,
        'max_audits_per_user', s.max_audits_per_user,
        'created_at', s.created_at,
        'used_audits', counts.used_audits + coalesce(t.submitted_audits, 0),
        'active_audits', counts.active_audits,
        'queued_audits', counts.queued_audits,
        'completed_audits', counts.completed_audits + coalesce(t.completed_audits, 0),
        'failed_audits', counts.failed_audits + coalesce(t.failed_audits, 0),
        'purged_anonymous_audits', coalesce(t.submitted_audits, 0),
        'brightdata_operations', usage.operations + coalesce(t.brightdata_operations, 0),
        'brightdata_confirmed_results', usage.results + coalesce(t.brightdata_confirmed_results, 0),
        'brightdata_estimated_cost_usd', usage.estimated_cost + coalesce(t.brightdata_estimated_cost_usd, 0)
    ) order by s.created_at desc), '[]'::jsonb)
      into v_workshops
      from public.workshops s
      join public.workspace_members m on m.workspace_id = s.organizer_workspace_id
      left join public.workshop_purge_totals t on t.workshop_id = s.id
      cross join lateral (
          select count(*)::bigint as used_audits,
                 count(*) filter (where a.status in ('dispatching', 'running'))::bigint as active_audits,
                 count(*) filter (where a.status = 'queued')::bigint as queued_audits,
                 count(*) filter (where a.status = 'completed')::bigint as completed_audits,
                 count(*) filter (where a.status = 'failed')::bigint as failed_audits
            from public.audits a where a.workshop_id = s.id
      ) counts
      cross join lateral (
          select count(*)::bigint as operations,
                 coalesce(sum(o.confirmed_result_count), 0)::bigint as results,
                 coalesce(sum(o.estimated_cost_usd), 0)::numeric(14, 6) as estimated_cost
            from public.brightdata_operations o
            join public.audits a on a.id = o.audit_id
           where a.workshop_id = s.id
      ) usage
     where m.user_id = p_user_id and m.role in ('owner', 'admin');

    return jsonb_build_object('workspaces', v_workspaces, 'workshops', v_workshops);
end;
$$;

create function public.admin_set_workshop_retention(
    p_user_id uuid,
    p_workshop_id uuid,
    p_hours integer
) returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_before public.workshops%rowtype;
    v_after public.workshops%rowtype;
begin
    select * into v_before from public.workshops
     where id = p_workshop_id for update;
    if not found then
        raise exception 'workshop not found' using errcode = '22023';
    end if;
    if not exists (
        select 1 from public.workspace_members m
         where m.workspace_id = v_before.organizer_workspace_id
           and m.user_id = p_user_id and m.role in ('owner', 'admin')
    ) then
        raise exception 'organizer access required' using errcode = '42501';
    end if;
    if v_before.purge_started_at is not null then
        raise exception 'retention is locked after purge begins' using errcode = '22023';
    end if;
    if p_hours is not null and (p_hours < 12 or p_hours > 168) then
        raise exception 'retention must be between 12 and 168 hours' using errcode = '22023';
    end if;
    if v_before.closes_at is not null and v_before.closes_at <= now()
       and p_hours is distinct from v_before.anonymous_retention_hours then
        raise exception 'retention cannot be changed after a workshop closes'
            using errcode = '22023';
    end if;
    update public.workshops
       set anonymous_retention_hours = p_hours
     where id = p_workshop_id returning * into v_after;
    if to_jsonb(v_after) is distinct from to_jsonb(v_before) then
        insert into public.workshop_admin_events (
            workshop_id, actor_id, action, before_state, after_state
        ) values (
            p_workshop_id, p_user_id, 'updated',
            to_jsonb(v_before), to_jsonb(v_after)
        );
    end if;
    return p_workshop_id;
end;
$$;
revoke all on function public.admin_set_workshop_retention(uuid, uuid, integer)
    from public, anon, authenticated;
grant execute on function public.admin_set_workshop_retention(uuid, uuid, integer)
    to service_role;

-- The hourly worker is harmless when no workshop is due. A workshop is due
-- only after it closes, every audit is terminal, and the download window
-- following the later of closure or last completion has elapsed.
create function public.purge_due_workshops(p_limit integer default 20)
returns jsonb
language sql
security definer
set search_path = ''
as $$
    select coalesce(jsonb_agg(x.id), '[]'::jsonb)
      from (
          select w.id
            from public.workshops w
           where w.anonymous_retention_hours is not null
             and w.closes_at is not null
             and w.purged_at is null
             and (
                 w.purge_started_at is not null
                 or (
                     not exists (
                         select 1 from public.audits a
                          where a.workshop_id = w.id
                            and a.status in ('queued', 'dispatching', 'running')
                     )
                     and now() >= greatest(
                         w.closes_at,
                         coalesce((
                             select max(coalesce(a.finished_at, a.updated_at, a.created_at))
                               from public.audits a where a.workshop_id = w.id
                         ), w.closes_at)
                     ) + make_interval(hours => w.anonymous_retention_hours)
                 )
             )
           order by w.closes_at, w.id
           limit least(greatest(p_limit, 1), 100)
      ) x;
$$;
revoke all on function public.purge_due_workshops(integer)
    from public, anon, authenticated;
grant execute on function public.purge_due_workshops(integer) to service_role;

create function public.purge_workshop_batch(
    p_workshop_id uuid,
    p_limit integer default 100,
    p_dry_run boolean default false
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_workshop public.workshops%rowtype;
    v_ids uuid[];
    v_paths text[];
    v_last_finished timestamptz;
begin
    select * into v_workshop from public.workshops
     where id = p_workshop_id for update;
    if not found or v_workshop.anonymous_retention_hours is null
       or v_workshop.closes_at is null or v_workshop.purged_at is not null then
        return jsonb_build_object('state', 'not_due');
    end if;
    if v_workshop.purge_started_at is null then
        if exists (
            select 1 from public.audits a
             where a.workshop_id = p_workshop_id
               and a.status in ('queued', 'dispatching', 'running')
        ) then
            return jsonb_build_object('state', 'active');
        end if;
        select max(coalesce(a.finished_at, a.updated_at, a.created_at))
          into v_last_finished
          from public.audits a where a.workshop_id = p_workshop_id;
        if now() < greatest(v_workshop.closes_at,
                            coalesce(v_last_finished, v_workshop.closes_at))
                   + make_interval(hours => v_workshop.anonymous_retention_hours) then
            return jsonb_build_object('state', 'not_due');
        end if;
        if not p_dry_run then
            update public.workshops set purge_started_at = now()
             where id = p_workshop_id;
        end if;
    end if;

    select coalesce(array_agg(x.id), '{}'::uuid[]) into v_ids
      from (
          select a.id from public.audits a
          join auth.users u on u.id = a.created_by
           where a.workshop_id = p_workshop_id and u.is_anonymous is true
           order by a.created_at, a.id
           limit least(greatest(p_limit, 1), 100)
      ) x;

    select coalesce(array_agg(x.object_path order by x.object_path), '{}'::text[])
      into v_paths
      from (
          select ar.object_path
            from public.audit_artifacts ar
           where ar.audit_id = any(v_ids)
          union
          select o.name
            from storage.objects o
            join public.audits a on a.id = any(v_ids)
           where o.bucket_id = 'audit-artifacts'
             and o.name like 'workspaces/' || a.workspace_id
                             || '/audits/' || a.id || '/%'
      ) x;

    return jsonb_build_object(
        'state', 'ready', 'audit_ids', to_jsonb(v_ids),
        'object_paths', to_jsonb(v_paths)
    );
end;
$$;
revoke all on function public.purge_workshop_batch(uuid, integer, boolean)
    from public, anon, authenticated;
grant execute on function public.purge_workshop_batch(uuid, integer, boolean)
    to service_role;

create function public.purge_finalize_batch(
    p_workshop_id uuid,
    p_audit_ids uuid[]
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_workshop public.workshops%rowtype;
    v_ids uuid[];
    v_users uuid[];
    v_submitted bigint;
    v_completed bigint;
    v_failed bigint;
    v_interrupted bigint;
    v_cancelled bigint;
    v_operations bigint;
    v_accepted bigint;
    v_results bigint;
    v_cost numeric(14, 6);
begin
    select * into v_workshop from public.workshops
     where id = p_workshop_id for update;
    if not found or v_workshop.purge_started_at is null
       or v_workshop.purged_at is not null then
        raise exception 'workshop purge has not started' using errcode = '22023';
    end if;
    if coalesce(array_length(p_audit_ids, 1), 0) > 100 then
        raise exception 'purge batch is too large' using errcode = '22023';
    end if;
    select coalesce(array_agg(a.id), '{}'::uuid[]),
           coalesce(array_agg(distinct a.created_by), '{}'::uuid[]),
           count(*)::bigint,
           count(*) filter (where a.status = 'completed')::bigint,
           count(*) filter (where a.status = 'failed')::bigint,
           count(*) filter (where a.status = 'interrupted')::bigint,
           count(*) filter (where a.status = 'cancelled')::bigint
      into v_ids, v_users, v_submitted, v_completed, v_failed,
           v_interrupted, v_cancelled
      from public.audits a
      join auth.users u on u.id = a.created_by
     where a.workshop_id = p_workshop_id and a.id = any(p_audit_ids)
       and u.is_anonymous is true
       and a.status not in ('queued', 'dispatching', 'running');
    if v_submitted = 0 then
        return jsonb_build_object('deleted', 0);
    end if;
    select count(*)::bigint,
           count(*) filter (where o.accepted is true)::bigint,
           coalesce(sum(o.confirmed_result_count), 0)::bigint,
           coalesce(sum(o.estimated_cost_usd), 0)::numeric(14, 6)
      into v_operations, v_accepted, v_results, v_cost
      from public.brightdata_operations o
     where o.audit_id = any(v_ids);

    insert into public.workshop_purge_totals (
        workshop_id, submitted_audits, completed_audits, failed_audits,
        interrupted_audits, cancelled_audits, brightdata_operations,
        brightdata_accepted, brightdata_confirmed_results,
        brightdata_estimated_cost_usd
    ) values (
        p_workshop_id, v_submitted, v_completed, v_failed,
        v_interrupted, v_cancelled, v_operations, v_accepted,
        v_results, v_cost
    ) on conflict (workshop_id) do update set
        submitted_audits = public.workshop_purge_totals.submitted_audits
                           + excluded.submitted_audits,
        completed_audits = public.workshop_purge_totals.completed_audits
                           + excluded.completed_audits,
        failed_audits = public.workshop_purge_totals.failed_audits
                        + excluded.failed_audits,
        interrupted_audits = public.workshop_purge_totals.interrupted_audits
                             + excluded.interrupted_audits,
        cancelled_audits = public.workshop_purge_totals.cancelled_audits
                           + excluded.cancelled_audits,
        brightdata_operations = public.workshop_purge_totals.brightdata_operations
                                + excluded.brightdata_operations,
        brightdata_accepted = public.workshop_purge_totals.brightdata_accepted
                              + excluded.brightdata_accepted,
        brightdata_confirmed_results = public.workshop_purge_totals.brightdata_confirmed_results
                                       + excluded.brightdata_confirmed_results,
        brightdata_estimated_cost_usd = public.workshop_purge_totals.brightdata_estimated_cost_usd
                                        + excluded.brightdata_estimated_cost_usd,
        updated_at = now();

    delete from public.audits a where a.id = any(v_ids);
    delete from public.workspaces w
     where w.kind = 'personal' and w.created_by = any(v_users)
       and not exists (select 1 from public.audits a where a.workspace_id = w.id);
    insert into public.workshop_purge_users (user_id, workshop_id)
    select u.id, p_workshop_id from auth.users u
     where u.id = any(v_users) and u.is_anonymous is true
       and not exists (select 1 from public.audits a where a.created_by = u.id)
    on conflict (user_id) do nothing;
    return jsonb_build_object('deleted', v_submitted);
end;
$$;
revoke all on function public.purge_finalize_batch(uuid, uuid[])
    from public, anon, authenticated;
grant execute on function public.purge_finalize_batch(uuid, uuid[])
    to service_role;

create function public.purge_workshop_users(p_workshop_id uuid)
returns jsonb
language sql
security definer
set search_path = ''
as $$
    select coalesce(jsonb_agg(q.user_id), '[]'::jsonb)
      from public.workshop_purge_users q
     where q.workshop_id = p_workshop_id;
$$;
revoke all on function public.purge_workshop_users(uuid)
    from public, anon, authenticated;
grant execute on function public.purge_workshop_users(uuid)
    to service_role;

create function public.purge_complete_workshop(p_workshop_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_workshop public.workshops%rowtype;
begin
    select * into v_workshop from public.workshops
     where id = p_workshop_id for update;
    if not found or v_workshop.purge_started_at is null then
        return false;
    end if;
    if v_workshop.purged_at is not null then
        return true;
    end if;
    if exists (
        select 1 from public.audits a join auth.users u on u.id = a.created_by
         where a.workshop_id = p_workshop_id and u.is_anonymous is true
    ) or exists (
        select 1 from public.workshop_purge_users q
         where q.workshop_id = p_workshop_id
    ) then
        return false;
    end if;
    update public.workshops set purged_at = now() where id = p_workshop_id;
    return true;
end;
$$;
revoke all on function public.purge_complete_workshop(uuid)
    from public, anon, authenticated;
grant execute on function public.purge_complete_workshop(uuid)
    to service_role;
