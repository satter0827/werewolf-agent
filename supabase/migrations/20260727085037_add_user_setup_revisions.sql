create table private.user_setups (
  setup_id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references auth.users(id) on delete cascade,
  display_name text not null check (length(btrim(display_name)) between 1 and 120),
  created_at timestamptz not null default timezone('utc', now())
);

create table private.user_setup_revisions (
  setup_id uuid not null references private.user_setups(setup_id) on delete cascade,
  revision integer not null check (revision >= 1),
  schema_version integer not null check (schema_version = 2),
  document jsonb not null,
  setup_checksum text not null check (length(setup_checksum) = 64),
  mechanics_checksum text not null check (length(mechanics_checksum) = 64),
  created_at timestamptz not null default timezone('utc', now()),
  primary key (setup_id, revision)
);

create index idx_user_setups_owner_created
  on private.user_setups (owner_user_id, created_at desc);

create index idx_user_setup_revisions_created
  on private.user_setup_revisions (setup_id, created_at desc);

alter table private.user_setups enable row level security;
alter table private.user_setup_revisions enable row level security;

create policy user_setups_owner_select
on private.user_setups
for select
to authenticated
using (
  (select auth.uid()) is not null
  and (select auth.uid()) = owner_user_id
  and coalesce((select auth.jwt() ->> 'is_anonymous')::boolean, false) = false
);

create policy user_setup_revisions_owner_select
on private.user_setup_revisions
for select
to authenticated
using (
  exists (
    select 1
    from private.user_setups setups
    where setups.setup_id = user_setup_revisions.setup_id
      and setups.owner_user_id = (select auth.uid())
  )
  and coalesce((select auth.jwt() ->> 'is_anonymous')::boolean, false) = false
);

revoke all on private.user_setups from anon, authenticated;
revoke all on private.user_setup_revisions from anon, authenticated;
grant select, insert on private.user_setups to service_role;
grant select, insert on private.user_setup_revisions to service_role;
