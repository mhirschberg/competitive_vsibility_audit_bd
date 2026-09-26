-- Run after local_postgres_bootstrap.sql and the foundation migration.
-- Every assertion aborts the transaction on failure.
begin;

insert into auth.users (id) values
    ('00000000-0000-0000-0000-000000000001'),
    ('00000000-0000-0000-0000-000000000002');

set role service_role;
insert into public.workspaces (id, kind, name, created_by) values
    ('10000000-0000-0000-0000-000000000001', 'personal', 'User A',
     '00000000-0000-0000-0000-000000000001'),
    ('10000000-0000-0000-0000-000000000002', 'personal', 'User B',
     '00000000-0000-0000-0000-000000000002');
insert into public.workspace_members (workspace_id, user_id, role) values
    ('10000000-0000-0000-0000-000000000001',
     '00000000-0000-0000-0000-000000000001', 'owner'),
    ('10000000-0000-0000-0000-000000000002',
     '00000000-0000-0000-0000-000000000002', 'owner');
insert into public.audits (
    id, workspace_id, created_by, client_request_id, company_name,
    company_domain, country_code, engine_commit, methodology_version
) values
    ('20000000-0000-0000-0000-000000000001',
     '10000000-0000-0000-0000-000000000001',
     '00000000-0000-0000-0000-000000000001',
     '30000000-0000-0000-0000-000000000001',
     'Company A', 'a.example', 'DE', 'test-commit', 'v1'),
    ('20000000-0000-0000-0000-000000000002',
     '10000000-0000-0000-0000-000000000002',
     '00000000-0000-0000-0000-000000000002',
     '30000000-0000-0000-0000-000000000002',
     'Company B', 'b.example', 'GB', 'test-commit', 'v1');
insert into public.audit_steps (audit_id, step_key, label) values
    ('20000000-0000-0000-0000-000000000001', 'serp_discovery', 'Search'),
    ('20000000-0000-0000-0000-000000000002', 'serp_discovery', 'Search');
insert into public.audit_artifacts
    (audit_id, kind, object_path, content_type, size_bytes) values
    ('20000000-0000-0000-0000-000000000001', 'report_json',
     'a/report.json', 'application/json', 42),
    ('20000000-0000-0000-0000-000000000002', 'report_json',
     'b/report.json', 'application/json', 42);
do $$
begin
    begin
        insert into public.audits (
            workspace_id, created_by, client_request_id, company_name,
            company_domain, country_code, engine_commit, methodology_version
        ) values (
            '10000000-0000-0000-0000-000000000001',
            '00000000-0000-0000-0000-000000000001',
            '30000000-0000-0000-0000-000000000001',
            'Duplicate', 'duplicate.example', 'DE', 'test-commit', 'v1'
        );
        raise exception 'duplicate request unexpectedly succeeded';
    exception when unique_violation then
        null;
    end;

    begin
        insert into public.audits (
            workspace_id, created_by, client_request_id, rerun_of,
            company_name, company_domain, country_code,
            engine_commit, methodology_version
        ) values (
            '10000000-0000-0000-0000-000000000002',
            '00000000-0000-0000-0000-000000000002',
            '30000000-0000-0000-0000-000000000003',
            '20000000-0000-0000-0000-000000000001',
            'Cross-workspace rerun', 'rerun.example', 'GB',
            'test-commit', 'v1'
        );
        raise exception 'cross-workspace rerun unexpectedly succeeded';
    exception when foreign_key_violation then
        null;
    end;
end;
$$;

do $$
declare
    v_execution_id uuid;
    v_claim_token uuid;
begin
    if not public.reserve_audit_dispatch(
        '20000000-0000-0000-0000-000000000001'
    ) then
        raise exception 'first dispatch reservation failed';
    end if;
    if public.reserve_audit_dispatch(
        '20000000-0000-0000-0000-000000000001'
    ) then
        raise exception 'duplicate dispatch reservation succeeded';
    end if;
    select execution_id, claim_token into v_execution_id, v_claim_token
      from public.claim_audit(
          '20000000-0000-0000-0000-000000000001', 'cloud-execution-a'
      );
    if v_execution_id is null or v_claim_token is null then
        raise exception 'first worker could not claim audit';
    end if;
    if (
        select count(*) from public.claim_audit(
            '20000000-0000-0000-0000-000000000001', 'cloud-execution-b'
        )
    ) <> 0 then
        raise exception 'duplicate worker claimed audit';
    end if;
    if public.reserve_audit_dispatch(
        '20000000-0000-0000-0000-000000000001'
    ) then
        raise exception 'running audit was dispatched again';
    end if;
    begin
        insert into public.audit_executions
            (audit_id, attempt_number, status) values
            ('20000000-0000-0000-0000-000000000001', 2, 'running');
        raise exception 'second running execution unexpectedly succeeded';
    exception when unique_violation then
        null;
    end;
    if public.heartbeat_audit(
        v_execution_id, '99999999-9999-9999-9999-999999999999'
    ) then
        raise exception 'wrong claim token refreshed heartbeat';
    end if;
    if not public.heartbeat_audit(v_execution_id, v_claim_token) then
        raise exception 'valid claim token failed heartbeat';
    end if;
    if not public.finish_audit(
        v_execution_id, v_claim_token, 'completed', '{}'::jsonb
    ) then
        raise exception 'valid claim token failed completion';
    end if;
    if public.finish_audit(
        v_execution_id, v_claim_token, 'completed', '{}'::jsonb
    ) then
        raise exception 'execution completed twice';
    end if;
end;
$$;
reset role;

set role authenticated;
select set_config('request.jwt.claim.sub',
    '00000000-0000-0000-0000-000000000001', true);
do $$
begin
    if (select count(*) from public.workspaces) <> 1 then
        raise exception 'user A workspace isolation failed';
    end if;
    if (select count(*) from public.audits) <> 1 then
        raise exception 'user A audit isolation failed';
    end if;
    if (select count(*) from public.audit_steps) <> 1 then
        raise exception 'user A step isolation failed';
    end if;
    if (select count(*) from public.audit_artifacts) <> 1 then
        raise exception 'user A artifact isolation failed';
    end if;
    begin
        insert into public.audit_events
            (audit_id, event_kind, message)
        values
            ('20000000-0000-0000-0000-000000000001', 'fake', 'write');
        raise exception 'authenticated write unexpectedly succeeded';
    exception when insufficient_privilege then
        null;
    end;
end;
$$;
reset role;

set role authenticated;
select set_config('request.jwt.claim.sub',
    '00000000-0000-0000-0000-000000000002', true);
do $$
begin
    if (select count(*) from public.audits) <> 1 then
        raise exception 'user B audit isolation failed';
    end if;
    if exists (
        select 1 from public.audits
        where id = '20000000-0000-0000-0000-000000000001'
    ) then
        raise exception 'user B can see user A audit';
    end if;
end;
$$;
reset role;

insert into auth.users (id)
values ('00000000-0000-0000-0000-000000000003');
set role service_role;
do $$
declare
    v_first uuid;
    v_second uuid;
    v_parallel_a uuid;
    v_parallel_b uuid;
    v_stale_execution uuid;
    v_stale_token uuid;
begin
    v_first := public.submit_audit(
        p_user_id => '00000000-0000-0000-0000-000000000003',
        p_client_request_id => '30000000-0000-0000-0000-000000000003',
        p_company_name => 'Company C',
        p_company_domain => 'c.example',
        p_country_code => 'DE',
        p_engine_commit => 'test-commit',
        p_methodology_version => 'v1'
    );
    v_second := public.submit_audit(
        p_user_id => '00000000-0000-0000-0000-000000000003',
        p_client_request_id => '30000000-0000-0000-0000-000000000003',
        p_company_name => 'Company C',
        p_company_domain => 'c.example',
        p_country_code => 'DE',
        p_engine_commit => 'test-commit',
        p_methodology_version => 'v1'
    );
    if v_first is null or v_first <> v_second then
        raise exception 'idempotent submission failed';
    end if;
    if (
        select count(*) from public.workspaces
        where kind = 'personal'
          and created_by = '00000000-0000-0000-0000-000000000003'
    ) <> 1 then
        raise exception 'personal workspace creation failed';
    end if;

    insert into public.workshops (id, slug, name, max_total_audits)
    values (
        '40000000-0000-0000-0000-000000000001',
        'test-workshop', 'Test workshop', 1
    );
    perform public.submit_audit(
        p_user_id => '00000000-0000-0000-0000-000000000001',
        p_client_request_id => '30000000-0000-0000-0000-000000000004',
        p_company_name => 'Workshop A',
        p_company_domain => 'workshop-a.example',
        p_country_code => 'DE',
        p_engine_commit => 'test-commit',
        p_methodology_version => 'v1',
        p_workshop_id => '40000000-0000-0000-0000-000000000001'
    );
    begin
        perform public.submit_audit(
            p_user_id => '00000000-0000-0000-0000-000000000002',
            p_client_request_id => '30000000-0000-0000-0000-000000000005',
            p_company_name => 'Workshop B',
            p_company_domain => 'workshop-b.example',
            p_country_code => 'DE',
            p_engine_commit => 'test-commit',
            p_methodology_version => 'v1',
            p_workshop_id => '40000000-0000-0000-0000-000000000001'
        );
        raise exception 'workshop total limit was not enforced';
    exception when invalid_parameter_value then
        null;
    end;
    begin
        perform public.submit_audit(
            p_user_id => '00000000-0000-0000-0000-000000000001',
            p_client_request_id => '30000000-0000-0000-0000-000000000006',
            p_company_name => 'Wrong workspace',
            p_company_domain => 'wrong.example',
            p_country_code => 'DE',
            p_engine_commit => 'test-commit',
            p_methodology_version => 'v1',
            p_workspace_id => '10000000-0000-0000-0000-000000000002'
        );
        raise exception 'cross-workspace submission unexpectedly succeeded';
    exception when insufficient_privilege then
        null;
    end;

    insert into public.workshops (
        id, slug, name, max_total_audits, max_concurrent_audits
    ) values (
        '40000000-0000-0000-0000-000000000002',
        'parallel-workshop', 'Parallel workshop', 3, 1
    );
    v_parallel_a := public.submit_audit(
        p_user_id => '00000000-0000-0000-0000-000000000001',
        p_client_request_id => '30000000-0000-0000-0000-000000000007',
        p_company_name => 'Parallel A',
        p_company_domain => 'parallel-a.example',
        p_country_code => 'DE',
        p_engine_commit => 'test-commit',
        p_methodology_version => 'v1',
        p_workshop_id => '40000000-0000-0000-0000-000000000002'
    );
    v_parallel_b := public.submit_audit(
        p_user_id => '00000000-0000-0000-0000-000000000002',
        p_client_request_id => '30000000-0000-0000-0000-000000000008',
        p_company_name => 'Parallel B',
        p_company_domain => 'parallel-b.example',
        p_country_code => 'DE',
        p_engine_commit => 'test-commit',
        p_methodology_version => 'v1',
        p_workshop_id => '40000000-0000-0000-0000-000000000002'
    );
    if not public.reserve_audit_dispatch(v_parallel_a) then
        raise exception 'first workshop slot was not reserved';
    end if;
    if public.reserve_audit_dispatch(v_parallel_b) then
        raise exception 'workshop concurrency limit was bypassed';
    end if;
    update public.audits set status = 'completed' where id = v_parallel_a;
    if not public.reserve_audit_dispatch(v_parallel_b) then
        raise exception 'workshop slot did not reopen';
    end if;
    select execution_id, claim_token into v_stale_execution, v_stale_token
      from public.claim_audit(v_parallel_b, 'cloud-stale-execution');
    update public.audit_executions
       set last_heartbeat_at = now() - interval '11 minutes'
     where id = v_stale_execution;
    if public.interrupt_stale_audits() <> 1 then
        raise exception 'stale worker was not interrupted';
    end if;
    if (select status from public.audits where id = v_parallel_b) <> 'interrupted' then
        raise exception 'audit stayed running after worker interruption';
    end if;
    if public.heartbeat_audit(v_stale_execution, v_stale_token) then
        raise exception 'interrupted worker still has a live claim';
    end if;
end;
$$;
reset role;

set role anon;
do $$
begin
    begin
        perform 1 from public.audits;
        raise exception 'unauthenticated audit read unexpectedly succeeded';
    exception when insufficient_privilege then
        null;
    end;
end;
$$;
reset role;

do $$
begin
    if (select public from storage.buckets where id = 'audit-artifacts') then
        raise exception 'artifact bucket is public';
    end if;
end;
$$;

rollback;
