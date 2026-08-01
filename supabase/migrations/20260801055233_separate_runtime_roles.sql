-- Runtime services use separate login users which inherit one of these roles.
-- Credentials are provisioned outside migrations so no reusable password enters Git.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'werewolf_api') then
    create role werewolf_api
      nologin nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'werewolf_worker') then
    create role werewolf_worker
      nologin nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
  end if;
  if exists (
    select 1 from pg_roles
    where rolname in ('werewolf_api', 'werewolf_worker')
      and (rolcanlogin or rolsuper or rolcreatedb or rolcreaterole
           or rolreplication or rolbypassrls)
  ) then
    raise exception 'runtime permission roles must be non-login and non-privileged';
  end if;
end
$$;

revoke all on schema public, private, pgmq from werewolf_api, werewolf_worker;
revoke all on all tables in schema public, private from werewolf_api, werewolf_worker;
revoke all on all sequences in schema public, private from werewolf_api, werewolf_worker;
revoke all on auth.users from werewolf_api, werewolf_worker;

grant usage on schema public, private, pgmq to werewolf_api;
grant usage on schema public, private, auth, pgmq to werewolf_worker;

-- The API authenticates callers and owns queries, setup edits, and queue submission.
grant select on public.games, public.game_summaries,
  public.game_participants, public.game_public_turns
  to werewolf_api;
grant select, insert, update on public.game_operation_requests to werewolf_api;
grant select on private.game_snapshots, private.game_events,
  private.game_state_versions, private.accepted_commands,
  private.game_reveals, private.llm_traces, private.llm_usage
  to werewolf_api;
grant select, insert on private.user_setups, private.user_setup_revisions
  to werewolf_api;

-- The worker consumes accepted commands and owns state/materialization writes.
grant select, insert, update on public.games, public.game_summaries to werewolf_worker;
grant select, insert on public.game_participants, public.game_public_turns
  to werewolf_worker;
grant select, update on public.game_operation_requests to werewolf_worker;
grant select, insert, update on private.game_snapshots to werewolf_worker;
grant select, insert on private.game_events, private.game_state_versions,
  private.accepted_commands to werewolf_worker;
grant select, insert on private.llm_traces to werewolf_worker;
grant insert on private.llm_usage, private.agent_decisions,
  private.audit_events to werewolf_worker;
grant insert, update on private.game_player_observations to werewolf_worker;
grant select, insert, update, delete on private.game_reveals to werewolf_worker;
grant select on auth.users to werewolf_worker;

-- Extension versions vary in argument types. Restrict by the stable function names
-- used by the adapters, while removing PostgreSQL's default PUBLIC execute grant.
revoke execute on all functions in schema pgmq from public;
do $$
declare
  function_row record;
  required_name text;
begin
  foreach required_name in array array['send', 'list_queues'] loop
    if not exists (
      select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
      where n.nspname = 'pgmq' and p.proname = required_name
    ) then
      raise exception 'required pgmq function is missing: %', required_name;
    end if;
    for function_row in
      select p.oid::regprocedure as signature
      from pg_proc p join pg_namespace n on n.oid = p.pronamespace
      where n.nspname = 'pgmq' and p.proname = required_name
    loop
      execute format('grant execute on function %s to werewolf_api', function_row.signature);
    end loop;
  end loop;

  foreach required_name in array array['read', 'read_with_poll', 'set_vt', 'archive'] loop
    if not exists (
      select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
      where n.nspname = 'pgmq' and p.proname = required_name
    ) then
      raise exception 'required pgmq function is missing: %', required_name;
    end if;
    for function_row in
      select p.oid::regprocedure as signature
      from pg_proc p join pg_namespace n on n.oid = p.pronamespace
      where n.nspname = 'pgmq' and p.proname = required_name
    loop
      execute format('grant execute on function %s to werewolf_worker', function_row.signature);
    end loop;
  end loop;
end
$$;

-- RLS remains enabled. Internal roles receive rows only on objects they can access;
-- table grants above still determine which operations each process may perform.
create policy runtime_api_all on public.game_operation_requests
  for all to werewolf_api using (true) with check (true);
create policy runtime_api_select on public.games
  for select to werewolf_api using (true);
create policy runtime_api_select on public.game_summaries
  for select to werewolf_api using (true);
create policy runtime_api_select on public.game_participants
  for select to werewolf_api using (true);
create policy runtime_api_select on public.game_public_turns
  for select to werewolf_api using (true);
create policy runtime_api_all on private.user_setups
  for all to werewolf_api using (true) with check (true);
create policy runtime_api_all on private.user_setup_revisions
  for all to werewolf_api using (true) with check (true);
create policy runtime_api_select on private.game_reveals
  for select to werewolf_api using (true);

create policy runtime_worker_all on public.games
  for all to werewolf_worker using (true) with check (true);
create policy runtime_worker_all on public.game_summaries
  for all to werewolf_worker using (true) with check (true);
create policy runtime_worker_all on public.game_participants
  for all to werewolf_worker using (true) with check (true);
create policy runtime_worker_all on public.game_public_turns
  for all to werewolf_worker using (true) with check (true);
create policy runtime_worker_all on public.game_operation_requests
  for all to werewolf_worker using (true) with check (true);
create policy runtime_worker_all on private.game_player_observations
  for all to werewolf_worker using (true) with check (true);
create policy runtime_worker_all on private.game_reveals
  for all to werewolf_worker using (true) with check (true);

-- New objects are denied until a later migration grants the owning runtime role.
alter default privileges for role postgres in schema public
  revoke all on tables from werewolf_api, werewolf_worker;
alter default privileges for role postgres in schema private
  revoke all on tables from werewolf_api, werewolf_worker;
