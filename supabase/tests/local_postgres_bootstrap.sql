-- Minimal stand-ins for Supabase-managed roles/schemas in a throwaway Postgres.
-- This validates our migration syntax and RLS, not the full Supabase platform.
create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;

create schema auth;
create table auth.users (id uuid primary key);
create function auth.uid() returns uuid
language sql stable
as $$
    select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;

create schema storage;
create table storage.buckets (
    id text primary key,
    name text not null,
    public boolean not null default false
);

grant usage on schema public, auth to authenticated;
grant usage on schema public to service_role;
grant execute on function auth.uid() to authenticated;
