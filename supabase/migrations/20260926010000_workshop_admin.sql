-- Organizer controls. Only the trusted API (service_role) may call these
-- functions; it supplies the user ID after validating a Supabase Auth token.

create table public.workshop_admin_events (
    id bigint generated always as identity primary key,
    workshop_id uuid not null references public.workshops (id) on delete restrict,
    actor_id uuid not null references auth.users (id) on delete restrict,
    action text not null check (action in ('created', 'updated')),
    before_state jsonb,
    after_state jsonb not null,
    created_at timestamptz not null default now()
);

create index workshop_admin_events_workshop_time_idx
    on public.workshop_admin_events (workshop_id, created_at desc);

alter table public.workshop_admin_events enable row level security;
revoke all on public.workshop_admin_events from public, anon, authenticated;
grant all on public.workshop_admin_events to service_role;

create function public.admin_list_workshops(p_user_id uuid)
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
        'max_total_audits', s.max_total_audits,
        'max_concurrent_audits', s.max_concurrent_audits,
        'max_audits_per_user', s.max_audits_per_user,
        'created_at', s.created_at,
        'used_audits', counts.used_audits,
        'active_audits', counts.active_audits,
        'queued_audits', counts.queued_audits,
        'completed_audits', counts.completed_audits
    ) order by s.created_at desc), '[]'::jsonb)
      into v_workshops
      from public.workshops s
      join public.workspace_members m on m.workspace_id = s.organizer_workspace_id
      cross join lateral (
          select count(*)::integer as used_audits,
                 count(*) filter (where a.status in ('dispatching', 'running'))::integer as active_audits,
                 count(*) filter (where a.status = 'queued')::integer as queued_audits,
                 count(*) filter (where a.status = 'completed')::integer as completed_audits
            from public.audits a where a.workshop_id = s.id
      ) counts
     where m.user_id = p_user_id and m.role in ('owner', 'admin');

    return jsonb_build_object('workspaces', v_workspaces, 'workshops', v_workshops);
end;
$$;

revoke all on function public.admin_list_workshops(uuid)
    from public, anon, authenticated;
grant execute on function public.admin_list_workshops(uuid) to service_role;

create function public.admin_create_workshop(
    p_user_id uuid,
    p_workspace_id uuid,
    p_slug text,
    p_name text,
    p_opens_at timestamptz,
    p_closes_at timestamptz,
    p_max_total_audits integer,
    p_max_concurrent_audits integer,
    p_max_audits_per_user integer
) returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_workshop public.workshops%rowtype;
begin
    if not exists (
        select 1 from public.workspaces w
        join public.workspace_members m on m.workspace_id = w.id
        where w.id = p_workspace_id and w.kind = 'team'
          and m.user_id = p_user_id and m.role in ('owner', 'admin')
    ) then
        raise exception 'organizer access required' using errcode = '42501';
    end if;
    if p_max_total_audits is null or p_max_concurrent_audits is null
       or p_max_audits_per_user is null then
        raise exception 'all workshop limits are required' using errcode = '22023';
    end if;
    insert into public.workshops (
        organizer_workspace_id, slug, name, opens_at, closes_at,
        max_total_audits, max_concurrent_audits, max_audits_per_user
    ) values (
        p_workspace_id, trim(p_slug), trim(p_name), p_opens_at, p_closes_at,
        p_max_total_audits, p_max_concurrent_audits, p_max_audits_per_user
    ) returning * into v_workshop;
    insert into public.workshop_admin_events (
        workshop_id, actor_id, action, after_state
    ) values (
        v_workshop.id, p_user_id, 'created', to_jsonb(v_workshop)
    );
    return v_workshop.id;
end;
$$;

revoke all on function public.admin_create_workshop(
    uuid, uuid, text, text, timestamptz, timestamptz, integer, integer, integer
) from public, anon, authenticated;
grant execute on function public.admin_create_workshop(
    uuid, uuid, text, text, timestamptz, timestamptz, integer, integer, integer
) to service_role;

create function public.admin_update_workshop(
    p_user_id uuid,
    p_workshop_id uuid,
    p_name text,
    p_opens_at timestamptz,
    p_closes_at timestamptz,
    p_max_total_audits integer,
    p_max_concurrent_audits integer,
    p_max_audits_per_user integer
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
    if p_max_total_audits is null or p_max_concurrent_audits is null
       or p_max_audits_per_user is null then
        raise exception 'all workshop limits are required' using errcode = '22023';
    end if;
    update public.workshops set
        name = trim(p_name),
        opens_at = p_opens_at,
        closes_at = p_closes_at,
        max_total_audits = p_max_total_audits,
        max_concurrent_audits = p_max_concurrent_audits,
        max_audits_per_user = p_max_audits_per_user
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

revoke all on function public.admin_update_workshop(
    uuid, uuid, text, timestamptz, timestamptz, integer, integer, integer
) from public, anon, authenticated;
grant execute on function public.admin_update_workshop(
    uuid, uuid, text, timestamptz, timestamptz, integer, integer, integer
) to service_role;
