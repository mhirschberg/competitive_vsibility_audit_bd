-- Project-wide cost telemetry is visible only to the explicit site owner.
-- Purged workshop totals are included, while runtime and storage reflect only
-- retained records (the purge intentionally removes their detailed history).
create function public.admin_cost_overview(p_user_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_result jsonb;
begin
    if not exists (select 1 from public.site_admins where user_id = p_user_id) then
        raise exception 'site admin access required' using errcode = '42501';
    end if;

    with live_audits as (
        select count(*)::bigint as total,
               count(*) filter (where status = 'completed')::bigint as completed,
               count(*) filter (where status in ('queued', 'dispatching', 'running'))::bigint as active,
               count(*) filter (where workshop_id is null)::bigint as trial,
               count(*) filter (where workshop_id is not null)::bigint as workshop
          from public.audits
    ), operations as (
        select count(*)::bigint as total,
               count(*) filter (where accepted is true)::bigint as accepted,
               coalesce(sum(confirmed_result_count), 0)::bigint as results,
               coalesce(sum(estimated_cost_usd), 0)::numeric(14, 6) as estimate,
               count(*) filter (where estimated_cost_usd is null)::bigint as unknown,
               count(*) filter (where estimate_is_lower_bound and estimated_cost_usd is not null)::bigint as lower_bound
          from public.brightdata_operations
    ), purged as (
        select coalesce(sum(submitted_audits), 0)::bigint as total,
               coalesce(sum(completed_audits), 0)::bigint as completed,
               coalesce(sum(brightdata_operations), 0)::bigint as operations,
               coalesce(sum(brightdata_accepted), 0)::bigint as accepted,
               coalesce(sum(brightdata_confirmed_results), 0)::bigint as results,
               coalesce(sum(brightdata_estimated_cost_usd), 0)::numeric(14, 6) as estimate
          from public.workshop_purge_totals
    ), artifacts as (
        select coalesce(sum(size_bytes), 0)::bigint as bytes
          from public.audit_artifacts
    ), runtime as (
        select coalesce(sum(extract(epoch from finished_at - started_at)), 0)::bigint as seconds
          from public.audit_executions
         where started_at is not null and finished_at is not null
    )
    select jsonb_build_object(
        'audits', a.total + p.total,
        'completed_audits', a.completed + p.completed,
        'active_audits', a.active,
        'trial_audits', a.trial,
        'workshop_audits', a.workshop + p.total,
        'purged_audits', p.total,
        'brightdata_operations', o.total + p.operations,
        'brightdata_accepted', o.accepted + p.accepted,
        'brightdata_confirmed_results', o.results + p.results,
        'brightdata_estimated_cost_usd', o.estimate + p.estimate,
        'brightdata_unknown_cost_operations', o.unknown,
        'brightdata_lower_bound_operations', o.lower_bound,
        'retained_artifact_bytes', f.bytes,
        'retained_worker_seconds', r.seconds,
        'calculated_at', now()
    ) into v_result
      from live_audits a cross join operations o cross join purged p
      cross join artifacts f cross join runtime r;
    return v_result;
end;
$$;

revoke all on function public.admin_cost_overview(uuid) from public, anon, authenticated;
grant execute on function public.admin_cost_overview(uuid) to service_role;
