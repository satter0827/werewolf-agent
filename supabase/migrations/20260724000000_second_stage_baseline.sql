-- Second-stage persistence baseline.
-- Existing local data is intentionally not migrated; reset the local stack before applying.

alter table public.games
  add column definition_snapshot jsonb not null default '{}'::jsonb,
  add column engine_version text not null default '0.1.0',
  add column llm_mode text not null default 'fake'
    check (llm_mode in ('fake', 'paid')),
  add column state_checksum text not null default '';

alter table public.game_operation_requests
  add column expected_version integer check (expected_version >= 1),
  add column request_hash text not null default '',
  add column llm_mode text not null default 'fake'
    check (llm_mode in ('fake', 'paid'));

alter table public.game_operation_requests
  drop constraint if exists game_operation_requests_status_check;

alter table public.game_operation_requests
  add constraint game_operation_requests_status_check
  check (status in ('queued', 'running', 'succeeded', 'failed'));

alter table private.game_events
  add column version integer not null default 1 check (version >= 1),
  add column checksum text not null default '';

alter table private.game_events
  drop constraint if exists game_events_visibility_check;

alter table private.game_events
  add constraint game_events_visibility_check
  check (visibility in ('public', 'player_private', 'private', 'debug'));

alter table private.game_snapshots
  add column checksum text not null default '';

-- Private projections must not be discoverable through the exposed public schema.
alter table public.game_player_observations set schema private;
alter table public.game_reveals set schema private;

create table private.accepted_commands (
  game_id uuid not null references public.games(game_id) on delete cascade,
  operation_id uuid not null references public.game_operation_requests(request_id) on delete cascade,
  version integer not null check (version >= 1),
  command_type text not null,
  actor_user_id uuid references auth.users(id) on delete set null,
  payload jsonb not null,
  checksum text not null,
  accepted_at timestamptz not null default timezone('utc', now()),
  primary key (operation_id),
  unique (game_id, version)
);

create table private.game_state_versions (
  game_id uuid not null references public.games(game_id) on delete cascade,
  version integer not null check (version >= 1),
  private_state jsonb not null,
  public_state jsonb not null,
  checksum text not null,
  created_at timestamptz not null default timezone('utc', now()),
  primary key (game_id, version)
);

create table private.agent_decisions (
  decision_id uuid primary key default gen_random_uuid(),
  game_id uuid not null references public.games(game_id) on delete cascade,
  operation_id uuid references public.game_operation_requests(request_id) on delete set null,
  state_version integer not null check (state_version >= 1),
  player_id text not null,
  decision jsonb not null,
  checksum text not null,
  created_at timestamptz not null default timezone('utc', now())
);

create table private.llm_traces (
  invocation_id uuid primary key default gen_random_uuid(),
  game_id uuid references public.games(game_id) on delete set null,
  operation_id uuid references public.game_operation_requests(request_id) on delete set null,
  trace_id text,
  provider text not null,
  model text not null,
  player_id text,
  phase text,
  day integer,
  state_version integer,
  prompt_messages jsonb not null default '[]'::jsonb,
  prompt_hash text not null default '',
  request_payload jsonb not null default '{}'::jsonb,
  raw_response jsonb,
  parsed_decision jsonb,
  error_payload jsonb,
  latency_ms numeric(12, 3),
  created_at timestamptz not null default timezone('utc', now())
);

create table private.audit_events (
  audit_id uuid primary key default gen_random_uuid(),
  actor_user_id uuid references auth.users(id) on delete set null,
  action text not null,
  target_type text,
  target_id text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create table private.llm_usage (
  usage_id uuid primary key default gen_random_uuid(),
  actor_user_id uuid references auth.users(id) on delete set null,
  game_id uuid references public.games(game_id) on delete set null,
  operation_id uuid references public.game_operation_requests(request_id) on delete set null,
  provider text not null,
  model text not null,
  input_tokens integer not null default 0 check (input_tokens >= 0),
  output_tokens integer not null default 0 check (output_tokens >= 0),
  cost_micros bigint not null default 0 check (cost_micros >= 0),
  created_at timestamptz not null default timezone('utc', now())
);

create index idx_accepted_commands_game_version
  on private.accepted_commands (game_id, version);
create index idx_game_state_versions_game_version
  on private.game_state_versions (game_id, version);
create index idx_agent_decisions_game_version
  on private.agent_decisions (game_id, state_version);
create index idx_llm_traces_game_created
  on private.llm_traces (game_id, created_at desc);
create index idx_llm_usage_actor_created
  on private.llm_usage (actor_user_id, created_at desc);

drop table if exists public.llm_invocations;
drop table if exists public.audit_events;

-- Game data is served by FastAPI. Browser clients retain Supabase Auth only.
revoke all on public.games from anon, authenticated;
revoke all on public.game_summaries from anon, authenticated;
revoke all on public.game_participants from anon, authenticated;
revoke all on public.game_public_turns from anon, authenticated;
revoke all on public.game_operation_requests from anon, authenticated;
revoke all on public.definition_items from anon, authenticated;

revoke all on all tables in schema private from anon, authenticated;
grant usage on schema private to service_role;
grant all on all tables in schema private to service_role;
