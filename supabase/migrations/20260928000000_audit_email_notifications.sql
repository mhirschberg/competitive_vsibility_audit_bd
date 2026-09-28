-- Opt-in completion mail for registered personal audits only. A database
-- trigger creates the outbox row in the same transaction as audit completion.
create table public.audit_email_notifications (
    audit_id uuid primary key references public.audits (id) on delete cascade,
    recipient_user_id uuid not null references auth.users (id) on delete cascade,
    recipient_email text not null check (length(recipient_email) between 3 and 320),
    status text not null default 'pending'
        check (status in ('pending', 'sending', 'retry', 'sent', 'abandoned')),
    attempts integer not null default 0 check (attempts between 0 and 8),
    next_attempt_at timestamptz not null default now(),
    claim_token uuid,
    lease_until timestamptz,
    provider_message_id text,
    last_error_code text,
    sent_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check ((status = 'sending') = (claim_token is not null and lease_until is not null))
);

create index audit_email_notifications_due_idx
    on public.audit_email_notifications (status, next_attempt_at)
    where status in ('pending', 'retry', 'sending');

alter table public.audit_email_notifications enable row level security;
revoke all on public.audit_email_notifications from public, anon, authenticated;
grant select, insert, update on public.audit_email_notifications to service_role;

create function public.enqueue_audit_ready_email()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if new.status = 'completed'
       and old.status is distinct from 'completed'
       and new.workshop_id is null
       and new.input_options ->> 'email_when_ready' = 'true' then
        insert into public.audit_email_notifications
            (audit_id, recipient_user_id, recipient_email)
        select new.id, new.created_by, u.email
          from auth.users u
         where u.id = new.created_by
           and u.is_anonymous is not true
           and u.email is not null
        on conflict (audit_id) do nothing;
    end if;
    return new;
end;
$$;

revoke all on function public.enqueue_audit_ready_email()
    from public, anon, authenticated;

create trigger audits_enqueue_ready_email
after update of status on public.audits
for each row execute function public.enqueue_audit_ready_email();

create function public.claim_audit_ready_email(p_audit_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_row public.audit_email_notifications%rowtype;
begin
    update public.audit_email_notifications n
       set status = 'abandoned',
           claim_token = null,
           lease_until = null,
           updated_at = now()
     where n.audit_id = p_audit_id
       and n.status = 'sending'
       and n.attempts >= 8
       and n.lease_until <= now();

    update public.audit_email_notifications n
       set status = 'sending',
           attempts = n.attempts + 1,
           claim_token = gen_random_uuid(),
           lease_until = now() + interval '5 minutes',
           updated_at = now()
     where n.audit_id = p_audit_id
       and n.attempts < 8
       and (
            (n.status in ('pending', 'retry') and n.next_attempt_at <= now())
            or (n.status = 'sending' and n.lease_until <= now())
       )
    returning n.* into v_row;
    if not found then
        return null;
    end if;
    return jsonb_build_object(
        'audit_id', v_row.audit_id,
        'email', v_row.recipient_email,
        'claim_token', v_row.claim_token,
        'attempts', v_row.attempts
    );
end;
$$;

revoke all on function public.claim_audit_ready_email(uuid)
    from public, anon, authenticated;
grant execute on function public.claim_audit_ready_email(uuid) to service_role;

create function public.finish_audit_ready_email(
    p_audit_id uuid,
    p_claim_token uuid,
    p_provider_message_id text
) returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
    update public.audit_email_notifications
       set status = 'sent',
           provider_message_id = left(p_provider_message_id, 200),
           sent_at = now(),
           claim_token = null,
           lease_until = null,
           updated_at = now()
     where audit_id = p_audit_id
       and claim_token = p_claim_token
       and status = 'sending';
    return found;
end;
$$;

revoke all on function public.finish_audit_ready_email(uuid, uuid, text)
    from public, anon, authenticated;
grant execute on function public.finish_audit_ready_email(uuid, uuid, text) to service_role;

create function public.defer_audit_ready_email(
    p_audit_id uuid,
    p_claim_token uuid,
    p_error_code text
) returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
    update public.audit_email_notifications
       set status = case when attempts >= 8 then 'abandoned' else 'retry' end,
           next_attempt_at = now() + make_interval(
               mins => least(60, (power(2, attempts))::integer)
           ),
           last_error_code = left(p_error_code, 100),
           claim_token = null,
           lease_until = null,
           updated_at = now()
     where audit_id = p_audit_id
       and claim_token = p_claim_token
       and status = 'sending';
    return found;
end;
$$;

revoke all on function public.defer_audit_ready_email(uuid, uuid, text)
    from public, anon, authenticated;
grant execute on function public.defer_audit_ready_email(uuid, uuid, text) to service_role;
