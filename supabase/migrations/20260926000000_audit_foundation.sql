-- Competitive Visibility Audit: durable ownership, execution, progress, and usage.
-- Apply with the Supabase migration tool after reviewing this migration.
-- Browser clients receive SELECT only; all writes go through the trusted API/worker.

create table public.workspaces (
    id uuid primary key default gen_random_uuid(),
    kind text not null default 'personal'
        check (kind in ('personal', 'team')),
    name text not null check (length(trim(name)) between 1 and 200),
    created_by uuid references auth.users (id) on delete set null,
    created_at timestamptz not null default now()
);

create unique index workspaces_one_personal_per_user_idx
    on public.workspaces (created_by)
    where kind = 'personal' and created_by is not null;

create table public.workspace_members (
    workspace_id uuid not null references public.workspaces (id) on delete cascade,
    user_id uuid not null references auth.users (id) on delete cascade,
    role text not null check (role in ('owner', 'admin', 'member')),
    joined_at timestamptz not null default now(),
    primary key (workspace_id, user_id)
);

create index workspace_members_user_id_idx
    on public.workspace_members (user_id, workspace_id);

create table public.workshops (
    id uuid primary key default gen_random_uuid(),
    organizer_workspace_id uuid references public.workspaces (id) on delete restrict,
    slug text not null unique
        check (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
    name text not null check (length(trim(name)) between 1 and 200),
    opens_at timestamptz,
    closes_at timestamptz,
    max_total_audits integer check (max_total_audits > 0),
    max_concurrent_audits integer check (max_concurrent_audits > 0),
    max_audits_per_user integer check (max_audits_per_user > 0),
    budget_usd numeric(14, 4) check (budget_usd >= 0),
    retention_days integer not null default 30
        check (retention_days between 1 and 3650),
    created_at timestamptz not null default now(),
    check (opens_at is null or closes_at is null or opens_at < closes_at)
);

create table public.audits (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces (id) on delete restrict,
    workshop_id uuid references public.workshops (id) on delete restrict,
    created_by uuid not null references auth.users (id) on delete restrict,
    client_request_id uuid not null,
    rerun_of uuid,
    company_name text not null check (length(trim(company_name)) between 1 and 300),
    company_domain text not null check (length(trim(company_domain)) between 1 and 500),
    audit_focus text check (audit_focus is null or length(audit_focus) <= 1000),
    country_code text not null check (country_code ~ '^[A-Z]{2}$'),
    input_options jsonb not null default '{}'::jsonb
        check (jsonb_typeof(input_options) = 'object'),
    input_schema_version integer not null default 1
        check (input_schema_version > 0),
    engine_commit text not null check (length(trim(engine_commit)) > 0),
    methodology_version text not null
        check (length(trim(methodology_version)) > 0),
    report_schema_version integer check (report_schema_version > 0),
    status text not null default 'queued'
        check (status in (
            'queued', 'dispatching', 'running', 'completed',
            'failed', 'interrupted', 'cancelled'
        )),
    dispatch_attempts integer not null default 0
        check (dispatch_attempts >= 0),
    last_dispatch_at timestamptz,
    started_at timestamptz,
    finished_at timestamptz,
    last_heartbeat_at timestamptz,
    error_code text,
    error_message text check (error_message is null or length(error_message) <= 2000),
    summary jsonb check (summary is null or jsonb_typeof(summary) = 'object'),
    usage_summary jsonb
        check (usage_summary is null or jsonb_typeof(usage_summary) = 'object'),
    expires_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (created_by, client_request_id),
    unique (id, workspace_id),
    foreign key (rerun_of, workspace_id)
        references public.audits (id, workspace_id) on delete set null (rerun_of),
    check (finished_at is null or started_at is null or finished_at >= started_at)
);

create index audits_workspace_history_idx
    on public.audits (workspace_id, created_at desc);
create index audits_workshop_status_idx
    on public.audits (workshop_id, status, created_at)
    where workshop_id is not null;
create index audits_workshop_user_idx
    on public.audits (workshop_id, created_by, created_at)
    where workshop_id is not null;
create index audits_dispatch_idx
    on public.audits (status, created_at)
    where status in ('queued', 'dispatching');
create index audits_expiration_idx
    on public.audits (expires_at)
    where expires_at is not null;

create table public.audit_executions (
    id uuid primary key default gen_random_uuid(),
    audit_id uuid not null references public.audits (id) on delete cascade,
    attempt_number integer not null check (attempt_number > 0),
    platform_execution_id text unique,
    claim_token uuid not null default gen_random_uuid(),
    status text not null default 'pending'
        check (status in (
            'pending', 'running', 'succeeded', 'failed',
            'interrupted', 'ignored'
        )),
    started_at timestamptz,
    last_heartbeat_at timestamptz,
    finished_at timestamptz,
    error_code text,
    created_at timestamptz not null default now(),
    unique (audit_id, attempt_number),
    unique (id, audit_id),
    check (finished_at is null or started_at is null or finished_at >= started_at)
);

-- A duplicate Cloud Run dispatch may exist, but only one execution may run.
create unique index audit_executions_one_running_idx
    on public.audit_executions (audit_id)
    where status = 'running';

create table public.audit_steps (
    audit_id uuid not null references public.audits (id) on delete cascade,
    step_key text not null check (step_key ~ '^[a-z][a-z0-9_]*$'),
    label text not null check (length(trim(label)) between 1 and 200),
    status text not null default 'pending'
        check (status in ('pending', 'running', 'completed', 'failed', 'skipped')),
    progress_current integer check (progress_current >= 0),
    progress_total integer check (progress_total > 0),
    started_at timestamptz,
    finished_at timestamptz,
    updated_at timestamptz not null default now(),
    primary key (audit_id, step_key),
    check (
        progress_current is null or progress_total is null
        or progress_current <= progress_total
    )
);

create table public.audit_events (
    id bigint generated always as identity primary key,
    audit_id uuid not null references public.audits (id) on delete cascade,
    execution_id uuid,
    step_key text,
    event_kind text not null check (length(trim(event_kind)) between 1 and 80),
    severity text not null default 'info'
        check (severity in ('debug', 'info', 'warning', 'error')),
    message text not null check (length(message) between 1 and 2000),
    details jsonb not null default '{}'::jsonb
        check (jsonb_typeof(details) = 'object'),
    created_at timestamptz not null default now(),
    foreign key (execution_id, audit_id)
        references public.audit_executions (id, audit_id) on delete set null (execution_id)
);

create index audit_events_feed_idx on public.audit_events (audit_id, id);

create table public.audit_artifacts (
    id uuid primary key default gen_random_uuid(),
    audit_id uuid not null references public.audits (id) on delete cascade,
    kind text not null check (kind ~ '^[a-z][a-z0-9_]*$'),
    bucket_id text not null default 'audit-artifacts',
    object_path text not null,
    content_type text not null,
    size_bytes bigint not null check (size_bytes >= 0),
    sha256 text check (sha256 is null or sha256 ~ '^[0-9a-f]{64}$'),
    expires_at timestamptz,
    created_at timestamptz not null default now(),
    unique (bucket_id, object_path)
);

create index audit_artifacts_audit_idx
    on public.audit_artifacts (audit_id, created_at);

create table public.brightdata_operations (
    id uuid primary key default gen_random_uuid(),
    audit_id uuid not null references public.audits (id) on delete cascade,
    execution_id uuid not null,
    source_operation_id integer not null check (source_operation_id > 0),
    operation_name text not null
        check (length(trim(operation_name)) between 1 and 200),
    dataset_id text,
    snapshot_id text,
    operation_status text not null default 'started',
    accepted boolean,
    input_count integer not null default 1 check (input_count >= 0),
    expected_result_count integer check (expected_result_count >= 0),
    confirmed_result_count integer check (confirmed_result_count >= 0),
    unit_price_usd_per_1000 numeric(12, 6)
        check (unit_price_usd_per_1000 >= 0),
    estimated_cost_usd numeric(14, 6) check (estimated_cost_usd >= 0),
    estimate_is_lower_bound boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (execution_id, source_operation_id),
    foreign key (execution_id, audit_id)
        references public.audit_executions (id, audit_id) on delete cascade
);

create index brightdata_operations_audit_idx
    on public.brightdata_operations (audit_id, created_at);
create index brightdata_operations_snapshot_idx
    on public.brightdata_operations (snapshot_id)
    where snapshot_id is not null;

-- Server-only admission is one transaction. The workshop row lock serializes
-- concurrent submissions against total/per-user limits; a request UUID makes
-- client retries idempotent. Concurrency and spend caps belong to dispatch.
create function public.submit_audit(
    p_user_id uuid,
    p_client_request_id uuid,
    p_company_name text,
    p_company_domain text,
    p_country_code text,
    p_engine_commit text,
    p_methodology_version text,
    p_audit_focus text default null,
    p_input_options jsonb default '{}'::jsonb,
    p_workshop_id uuid default null,
    p_workspace_id uuid default null,
    p_rerun_of uuid default null
) returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_workspace_id uuid;
    v_workshop public.workshops%rowtype;
    v_existing public.audits%rowtype;
    v_audit_id uuid;
    v_name text := trim(p_company_name);
    v_domain text := trim(p_company_domain);
    v_focus text := nullif(trim(p_audit_focus), '');
    v_country text := upper(trim(p_country_code));
    v_options jsonb := coalesce(p_input_options, '{}'::jsonb);
begin
    if p_user_id is null or p_client_request_id is null then
        raise exception 'user and client request ID are required'
            using errcode = '22023';
    end if;

    if p_workspace_id is null then
        select w.id into v_workspace_id
          from public.workspaces w
         where w.kind = 'personal' and w.created_by = p_user_id;
        if v_workspace_id is null then
            insert into public.workspaces (kind, name, created_by)
            values ('personal', 'My audits', p_user_id)
            on conflict (created_by)
                where kind = 'personal' and created_by is not null
                do nothing
            returning id into v_workspace_id;
            if v_workspace_id is null then
                select w.id into v_workspace_id
                  from public.workspaces w
                 where w.kind = 'personal' and w.created_by = p_user_id;
            end if;
        end if;
        insert into public.workspace_members (workspace_id, user_id, role)
        values (v_workspace_id, p_user_id, 'owner')
        on conflict do nothing;
    else
        v_workspace_id := p_workspace_id;
        if not exists (
            select 1 from public.workspace_members m
             where m.workspace_id = v_workspace_id and m.user_id = p_user_id
        ) then
            raise exception 'user is not a workspace member'
                using errcode = '42501';
        end if;
    end if;

    select * into v_existing from public.audits
     where created_by = p_user_id and client_request_id = p_client_request_id;
    if found then
        if v_existing.workspace_id is distinct from v_workspace_id
           or v_existing.workshop_id is distinct from p_workshop_id
           or v_existing.company_name is distinct from v_name
           or v_existing.company_domain is distinct from v_domain
           or v_existing.audit_focus is distinct from v_focus
           or v_existing.country_code is distinct from v_country
           or v_existing.input_options is distinct from v_options
           or v_existing.rerun_of is distinct from p_rerun_of then
            raise exception 'client request ID reused with different input'
                using errcode = '22023';
        end if;
        return v_existing.id;
    end if;

    if p_workshop_id is not null then
        select * into v_workshop from public.workshops
         where id = p_workshop_id for update;
        if not found then
            raise exception 'workshop not found' using errcode = '22023';
        end if;
        if (v_workshop.opens_at is not null and now() < v_workshop.opens_at)
           or (v_workshop.closes_at is not null and now() >= v_workshop.closes_at) then
            raise exception 'workshop is not accepting audits'
                using errcode = '22023';
        end if;
        if v_workshop.max_total_audits is not null and (
            select count(*) from public.audits a
             where a.workshop_id = p_workshop_id
        ) >= v_workshop.max_total_audits then
            raise exception 'workshop audit limit reached'
                using errcode = '22023';
        end if;
        if v_workshop.max_audits_per_user is not null and (
            select count(*) from public.audits a
             where a.workshop_id = p_workshop_id and a.created_by = p_user_id
        ) >= v_workshop.max_audits_per_user then
            raise exception 'user workshop audit limit reached'
                using errcode = '22023';
        end if;
    end if;

    insert into public.audits (
        workspace_id, workshop_id, created_by, client_request_id, rerun_of,
        company_name, company_domain, audit_focus, country_code, input_options,
        engine_commit, methodology_version, expires_at
    ) values (
        v_workspace_id, p_workshop_id, p_user_id, p_client_request_id, p_rerun_of,
        v_name, v_domain, v_focus, v_country, v_options,
        p_engine_commit, p_methodology_version,
        case when p_workshop_id is null then null
             else now() + make_interval(days => v_workshop.retention_days)
        end
    )
    on conflict (created_by, client_request_id) do nothing
    returning id into v_audit_id;

    if v_audit_id is null then
        select * into v_existing from public.audits
         where created_by = p_user_id and client_request_id = p_client_request_id;
        if v_existing.workspace_id is distinct from v_workspace_id
           or v_existing.workshop_id is distinct from p_workshop_id
           or v_existing.company_name is distinct from v_name
           or v_existing.company_domain is distinct from v_domain
           or v_existing.audit_focus is distinct from v_focus
           or v_existing.country_code is distinct from v_country
           or v_existing.input_options is distinct from v_options
           or v_existing.rerun_of is distinct from p_rerun_of then
            raise exception 'client request ID reused with different input'
                using errcode = '22023';
        end if;
        return v_existing.id;
    end if;

    return v_audit_id;
end;
$$;

revoke all on function public.submit_audit(
    uuid, uuid, text, text, text, text, text,
    text, jsonb, uuid, uuid, uuid
) from public, anon, authenticated;
grant execute on function public.submit_audit(
    uuid, uuid, text, text, text, text, text,
    text, jsonb, uuid, uuid, uuid
) to service_role;

-- Reserve a Cloud Run dispatch once. If the API loses the Cloud Run response,
-- a reconciler may re-dispatch after the timeout. Duplicate workers still
-- cannot claim the audit twice or repeat paid requests.
create function public.reserve_audit_dispatch(p_audit_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_audit public.audits%rowtype;
    v_workshop public.workshops%rowtype;
begin
    select * into v_audit from public.audits where id = p_audit_id;
    if not found or v_audit.status not in ('queued', 'dispatching') then
        return false;
    end if;
    if v_audit.workshop_id is not null then
        select * into v_workshop from public.workshops
         where id = v_audit.workshop_id for update;
        if v_workshop.max_concurrent_audits is not null and (
            select count(*) from public.audits a
             where a.workshop_id = v_audit.workshop_id
               and a.id <> p_audit_id
               and a.status in ('dispatching', 'running')
        ) >= v_workshop.max_concurrent_audits then
            return false;
        end if;
    end if;

    update public.audits
       set status = 'dispatching',
           dispatch_attempts = dispatch_attempts + 1,
           last_dispatch_at = now(),
           updated_at = now()
     where id = p_audit_id
       and (
           status = 'queued'
           or (status = 'dispatching'
               and last_dispatch_at < now() - interval '5 minutes')
       );
    return found;
end;
$$;

revoke all on function public.reserve_audit_dispatch(uuid)
    from public, anon, authenticated;
grant execute on function public.reserve_audit_dispatch(uuid) to service_role;

-- The worker calls this after Cloud Run dispatch, before any paid API request.
-- Concurrent or duplicate invocations race on the audit row; only one wins.
create function public.claim_audit(
    p_audit_id uuid,
    p_platform_execution_id text default null
) returns table (execution_id uuid, claim_token uuid)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_attempt_number integer;
begin
    update public.audits
       set status = 'running',
           started_at = coalesce(started_at, now()),
           last_heartbeat_at = now(),
           updated_at = now()
     where id = p_audit_id
       and status in ('queued', 'dispatching');

    if not found then
        return;
    end if;

    select coalesce(max(e.attempt_number), 0) + 1
      into v_attempt_number
      from public.audit_executions e
     where e.audit_id = p_audit_id;

    return query
    insert into public.audit_executions (
        audit_id, attempt_number, platform_execution_id,
        status, started_at, last_heartbeat_at
    ) values (
        p_audit_id, v_attempt_number, p_platform_execution_id,
        'running', now(), now()
    )
    returning id, audit_executions.claim_token;
end;
$$;

revoke all on function public.claim_audit(uuid, text)
    from public, anon, authenticated;
grant execute on function public.claim_audit(uuid, text) to service_role;

create function public.heartbeat_audit(
    p_execution_id uuid,
    p_claim_token uuid
) returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_audit_id uuid;
begin
    update public.audit_executions
       set last_heartbeat_at = now()
     where id = p_execution_id
       and claim_token = p_claim_token
       and status = 'running'
    returning audit_id into v_audit_id;
    if not found then
        return false;
    end if;
    update public.audits
       set last_heartbeat_at = now(), updated_at = now()
     where id = v_audit_id and status = 'running';
    return found;
end;
$$;

revoke all on function public.heartbeat_audit(uuid, uuid)
    from public, anon, authenticated;
grant execute on function public.heartbeat_audit(uuid, uuid) to service_role;

create function public.finish_audit(
    p_execution_id uuid,
    p_claim_token uuid,
    p_outcome text,
    p_summary jsonb default null,
    p_usage_summary jsonb default null,
    p_report_schema_version integer default null,
    p_error_code text default null,
    p_error_message text default null
) returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_audit_id uuid;
begin
    if p_outcome not in ('completed', 'failed', 'interrupted') then
        raise exception 'invalid audit outcome' using errcode = '22023';
    end if;
    update public.audit_executions
       set status = case when p_outcome = 'completed' then 'succeeded'
                         else p_outcome end,
           finished_at = now(),
           last_heartbeat_at = now(),
           error_code = p_error_code
     where id = p_execution_id
       and claim_token = p_claim_token
       and status = 'running'
    returning audit_id into v_audit_id;
    if not found then
        return false;
    end if;
    update public.audits
       set status = p_outcome,
           finished_at = now(),
           last_heartbeat_at = now(),
           updated_at = now(),
           summary = p_summary,
           usage_summary = p_usage_summary,
           report_schema_version = p_report_schema_version,
           error_code = p_error_code,
           error_message = p_error_message
     where id = v_audit_id and status = 'running';
    if not found then
        raise exception 'audit is no longer running' using errcode = '22023';
    end if;
    return true;
end;
$$;

revoke all on function public.finish_audit(
    uuid, uuid, text, jsonb, jsonb, integer, text, text
) from public, anon, authenticated;
grant execute on function public.finish_audit(
    uuid, uuid, text, jsonb, jsonb, integer, text, text
) to service_role;

-- An OOM kill or platform timeout cannot call finish_audit. A scheduled
-- reconciler marks executions with no heartbeat as interrupted; it does not
-- automatically restart paid work.
create function public.interrupt_stale_audits(
    p_stale_after interval default interval '10 minutes'
) returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_count integer;
begin
    if p_stale_after is null or p_stale_after < interval '5 minutes' then
        raise exception 'stale threshold must be at least five minutes'
            using errcode = '22023';
    end if;

    with stale as (
        update public.audit_executions e
           set status = 'interrupted',
               finished_at = now(),
               error_code = 'heartbeat_timeout'
         where e.status = 'running'
           and e.last_heartbeat_at < now() - p_stale_after
        returning e.audit_id
    )
    update public.audits a
       set status = 'interrupted',
           finished_at = now(),
           updated_at = now(),
           error_code = 'heartbeat_timeout',
           error_message = 'Audit worker stopped reporting progress'
      from stale s
     where a.id = s.audit_id and a.status = 'running';

    get diagnostics v_count = row_count;
    return v_count;
end;
$$;

revoke all on function public.interrupt_stale_audits(interval)
    from public, anon, authenticated;
grant execute on function public.interrupt_stale_audits(interval) to service_role;

-- Files remain private. The trusted API checks audit access before minting a
-- short-lived download URL; browser clients cannot list or upload objects.
insert into storage.buckets (id, name, public)
values ('audit-artifacts', 'audit-artifacts', false)
on conflict (id) do update set public = false;

alter table public.workspaces enable row level security;
alter table public.workspace_members enable row level security;
alter table public.workshops enable row level security;
alter table public.audits enable row level security;
alter table public.audit_executions enable row level security;
alter table public.audit_steps enable row level security;
alter table public.audit_events enable row level security;
alter table public.audit_artifacts enable row level security;
alter table public.brightdata_operations enable row level security;

revoke all on public.workspaces, public.workspace_members, public.workshops,
    public.audits, public.audit_executions, public.audit_steps,
    public.audit_events, public.audit_artifacts, public.brightdata_operations
    from public, anon, authenticated;

grant select on public.workspaces, public.workspace_members, public.workshops,
    public.audits, public.audit_executions, public.audit_steps,
    public.audit_events, public.audit_artifacts, public.brightdata_operations
    to authenticated;

grant all on public.workspaces, public.workspace_members, public.workshops,
    public.audits, public.audit_executions, public.audit_steps,
    public.audit_events, public.audit_artifacts, public.brightdata_operations
    to service_role;

create policy workspace_members_select_own
    on public.workspace_members for select to authenticated
    using (user_id = (select auth.uid()));

create policy workspaces_select_member
    on public.workspaces for select to authenticated
    using (exists (
        select 1 from public.workspace_members m
        where m.workspace_id = id and m.user_id = (select auth.uid())
    ));

create policy workshops_select_organizer
    on public.workshops for select to authenticated
    using (exists (
        select 1 from public.workspace_members m
        where m.workspace_id = organizer_workspace_id
          and m.user_id = (select auth.uid())
    ));

create policy audits_select_workspace_member
    on public.audits for select to authenticated
    using (exists (
        select 1 from public.workspace_members m
        where m.workspace_id = audits.workspace_id
          and m.user_id = (select auth.uid())
    ));

create policy audit_executions_select_workspace_member
    on public.audit_executions for select to authenticated
    using (exists (
        select 1 from public.audits a
        join public.workspace_members m on m.workspace_id = a.workspace_id
        where a.id = audit_executions.audit_id
          and m.user_id = (select auth.uid())
    ));

create policy audit_steps_select_workspace_member
    on public.audit_steps for select to authenticated
    using (exists (
        select 1 from public.audits a
        join public.workspace_members m on m.workspace_id = a.workspace_id
        where a.id = audit_steps.audit_id
          and m.user_id = (select auth.uid())
    ));

create policy audit_events_select_workspace_member
    on public.audit_events for select to authenticated
    using (exists (
        select 1 from public.audits a
        join public.workspace_members m on m.workspace_id = a.workspace_id
        where a.id = audit_events.audit_id
          and m.user_id = (select auth.uid())
    ));

create policy audit_artifacts_select_workspace_member
    on public.audit_artifacts for select to authenticated
    using (exists (
        select 1 from public.audits a
        join public.workspace_members m on m.workspace_id = a.workspace_id
        where a.id = audit_artifacts.audit_id
          and m.user_id = (select auth.uid())
    ));

create policy brightdata_operations_select_workspace_member
    on public.brightdata_operations for select to authenticated
    using (exists (
        select 1 from public.audits a
        join public.workspace_members m on m.workspace_id = a.workspace_id
        where a.id = brightdata_operations.audit_id
          and m.user_id = (select auth.uid())
    ));
