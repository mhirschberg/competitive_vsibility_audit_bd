-- A project-wide registrant list is more sensitive than workshop settings.
-- Seed only when one distinct owner already runs a workshop. An ambiguous or
-- fresh installation grants nobody access until an operator adds an owner.
-- Future organizers do not inherit project-wide access.
create table public.site_admins (
    user_id uuid primary key references auth.users (id) on delete cascade,
    granted_at timestamptz not null default now()
);

alter table public.site_admins enable row level security;
revoke all on public.site_admins from public, anon, authenticated;
grant all on public.site_admins to service_role;

with existing_owners as (
    select distinct m.user_id
      from public.workspace_members m
      join public.workspaces w on w.id = m.workspace_id
     where w.kind = 'team' and m.role = 'owner'
       and exists (
           select 1 from public.workshops s
            where s.organizer_workspace_id = w.id
       )
)
insert into public.site_admins (user_id)
select user_id from existing_owners
 where (select count(*) from existing_owners) = 1;

create function public.admin_list_registered_users(
    p_user_id uuid,
    p_limit integer default 25,
    p_offset integer default 0
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_total integer;
    v_users jsonb;
begin
    if not exists (
        select 1 from public.site_admins sa where sa.user_id = p_user_id
    ) then
        raise exception 'site admin access required' using errcode = '42501';
    end if;
    if p_limit is null or p_limit < 1 or p_limit > 100
       or p_offset is null or p_offset < 0 then
        raise exception 'invalid page' using errcode = '22023';
    end if;

    select count(*)::integer into v_total
      from auth.users u
     where u.is_anonymous is not true
       and exists (
           select 1 from auth.identities i
            where i.user_id = u.id and i.provider = 'google'
       );

    select coalesce(jsonb_agg(jsonb_build_object(
        'id', u.id,
        'email', u.email,
        'name', coalesce(nullif(u.raw_user_meta_data->>'full_name', ''),
                         nullif(u.raw_user_meta_data->>'name', '')),
        'registered_at', u.created_at,
        'last_sign_in_at', u.last_sign_in_at,
        'audit_count', stats.audit_count,
        'completed_count', stats.completed_count,
        'last_audit_at', stats.last_audit_at,
        'last_audit_status', latest.status
    ) order by u.created_at desc, u.id desc), '[]'::jsonb)
      into v_users
      from (
          select u.id, u.email, u.raw_user_meta_data, u.created_at,
                 u.last_sign_in_at
            from auth.users u
           where u.is_anonymous is not true
             and exists (
                 select 1 from auth.identities i
                  where i.user_id = u.id and i.provider = 'google'
             )
           order by u.created_at desc, u.id desc
           limit p_limit offset p_offset
      ) u
      cross join lateral (
          select count(*)::integer as audit_count,
                 count(*) filter (where a.status = 'completed')::integer as completed_count,
                 max(a.created_at) as last_audit_at
            from public.audits a
           where a.created_by = u.id and a.workshop_id is null
      ) stats
      left join lateral (
          select a.status from public.audits a
           where a.created_by = u.id and a.workshop_id is null
           order by a.created_at desc, a.id desc limit 1
      ) latest on true;

    return jsonb_build_object('total', v_total, 'users', v_users);
end;
$$;

revoke all on function public.admin_list_registered_users(uuid, integer, integer)
    from public, anon, authenticated;
grant execute on function public.admin_list_registered_users(uuid, integer, integer)
    to service_role;
