create extension if not exists pgcrypto with schema extensions;

create schema if not exists private;

create function public.is_admin()
returns boolean
language sql
stable
as $$
  select coalesce(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'admin'
$$;

create function private.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

create table public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default '',
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table public.user_preferences (
  user_id uuid primary key references auth.users(id) on delete cascade,
  locale text not null default 'ja',
  settings jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table public.definition_items (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid references auth.users(id) on delete cascade,
  scope text not null check (scope in ('system', 'user')),
  kind text not null check (kind in ('ruleset', 'role', 'character', 'scenario', 'setup_preset', 'narration_profile')),
  item_key text not null,
  payload jsonb not null,
  active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (scope, owner_user_id, kind, item_key)
);

create table public.games (
  game_id uuid primary key,
  owner_user_id uuid references auth.users(id) on delete set null,
  status text not null check (status in ('running', 'completed')),
  phase text not null check (phase in ('night', 'day_discussion', 'voting', 'finished')),
  day integer not null check (day >= 0),
  version integer not null check (version >= 1),
  seed integer,
  scenario_id text,
  scenario_name text,
  narration_mode text not null default 'standard',
  public_state jsonb not null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  completed_at timestamptz
);

create table public.game_summaries (
  game_id uuid primary key references public.games(game_id) on delete cascade,
  owner_user_id uuid references auth.users(id) on delete set null,
  status text not null check (status in ('running', 'completed')),
  phase text not null check (phase in ('night', 'day_discussion', 'voting', 'finished')),
  day integer not null check (day >= 0),
  version integer not null check (version >= 1),
  seed integer,
  player_count integer not null check (player_count >= 0),
  alive_count integer not null check (alive_count >= 0),
  winner text check (winner in ('villagers', 'werewolves')),
  step_count integer not null check (step_count >= 0),
  turn_count integer not null check (turn_count >= 0),
  created_at timestamptz not null,
  updated_at timestamptz not null,
  completed_at timestamptz
);

create table public.game_participants (
  game_id uuid not null references public.games(game_id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  player_id text not null,
  participant_role text not null default 'player' check (participant_role in ('owner', 'player', 'observer')),
  created_at timestamptz not null default timezone('utc', now()),
  primary key (game_id, user_id, player_id)
);

create table public.game_public_turns (
  game_id uuid not null references public.games(game_id) on delete cascade,
  sequence integer not null check (sequence >= 1),
  event_sequence integer not null check (event_sequence >= 1),
  version integer not null check (version >= 1),
  phase text check (phase in ('night', 'day_discussion', 'voting', 'finished')),
  day integer check (day >= 0),
  actor_id text,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default timezone('utc', now()),
  primary key (game_id, sequence)
);

create table public.game_player_observations (
  game_id uuid not null references public.games(game_id) on delete cascade,
  player_id text not null,
  user_id uuid not null references auth.users(id) on delete cascade,
  state_version integer not null check (state_version >= 1),
  observation jsonb not null,
  updated_at timestamptz not null default timezone('utc', now()),
  primary key (game_id, player_id, user_id)
);

create table public.game_reveals (
  game_id uuid primary key references public.games(game_id) on delete cascade,
  reveal_payload jsonb not null,
  state_version integer not null check (state_version >= 1),
  updated_at timestamptz not null default timezone('utc', now())
);

create table public.game_operation_requests (
  request_id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  operation_type text not null check (operation_type in ('create_game', 'advance_game', 'submit_action')),
  status text not null default 'queued' check (status in ('queued', 'running', 'completed', 'failed', 'cancelled')),
  game_id uuid,
  player_id text,
  idempotency_key text,
  request_payload jsonb not null default '{}'::jsonb,
  result_payload jsonb,
  error_payload jsonb,
  attempt_count integer not null default 0 check (attempt_count >= 0),
  worker_id text,
  claimed_until timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz not null default timezone('utc', now()),
  unique (owner_user_id, idempotency_key)
);

create table public.llm_invocations (
  invocation_id uuid primary key default gen_random_uuid(),
  game_id uuid references public.games(game_id) on delete set null,
  request_id uuid references public.game_operation_requests(request_id) on delete set null,
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

create table public.audit_events (
  audit_id uuid primary key default gen_random_uuid(),
  actor_user_id uuid references auth.users(id) on delete set null,
  action text not null,
  target_table text,
  target_id text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create table public.retention_runs (
  run_id uuid primary key default gen_random_uuid(),
  policy_name text not null,
  cutoff_at timestamptz not null,
  deleted_counts jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create table private.game_snapshots (
  game_id uuid primary key references public.games(game_id) on delete cascade,
  config jsonb not null,
  private_state jsonb not null,
  pending_actions jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default timezone('utc', now())
);

create table private.game_events (
  game_id uuid not null references public.games(game_id) on delete cascade,
  sequence integer not null check (sequence >= 1),
  event_id uuid not null default gen_random_uuid(),
  visibility text not null check (visibility in ('public', 'player_private', 'debug')),
  phase text check (phase in ('night', 'day_discussion', 'voting', 'finished')),
  day integer check (day >= 0),
  actor_id text,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default timezone('utc', now()),
  primary key (game_id, sequence)
);

create index idx_definition_items_lookup on public.definition_items (kind, scope, active);
create index idx_game_summaries_display on public.game_summaries (updated_at desc, created_at desc);
create index idx_game_participants_user on public.game_participants (user_id, game_id);
create index idx_game_public_turns_game_sequence on public.game_public_turns (game_id, sequence);
create index idx_game_operation_requests_queue on public.game_operation_requests (status, claimed_until, created_at);
create index idx_llm_invocations_game_created on public.llm_invocations (game_id, created_at desc);
create index idx_private_game_events_game_sequence on private.game_events (game_id, sequence);

create trigger profiles_set_updated_at
before update on public.profiles
for each row execute function private.set_updated_at();

create trigger user_preferences_set_updated_at
before update on public.user_preferences
for each row execute function private.set_updated_at();

create trigger definition_items_set_updated_at
before update on public.definition_items
for each row execute function private.set_updated_at();

create trigger games_set_updated_at
before update on public.games
for each row execute function private.set_updated_at();

create trigger game_operation_requests_set_updated_at
before update on public.game_operation_requests
for each row execute function private.set_updated_at();

alter table public.profiles enable row level security;
alter table public.user_preferences enable row level security;
alter table public.definition_items enable row level security;
alter table public.games enable row level security;
alter table public.game_summaries enable row level security;
alter table public.game_participants enable row level security;
alter table public.game_public_turns enable row level security;
alter table public.game_player_observations enable row level security;
alter table public.game_reveals enable row level security;
alter table public.game_operation_requests enable row level security;
alter table public.llm_invocations enable row level security;
alter table public.audit_events enable row level security;
alter table public.retention_runs enable row level security;

create policy profiles_select_own_or_admin on public.profiles
for select to authenticated
using (user_id = auth.uid() or public.is_admin());

create policy profiles_insert_own on public.profiles
for insert to authenticated
with check (user_id = auth.uid());

create policy profiles_update_own on public.profiles
for update to authenticated
using (user_id = auth.uid())
with check (user_id = auth.uid());

create policy user_preferences_own on public.user_preferences
for all to authenticated
using (user_id = auth.uid())
with check (user_id = auth.uid());

create policy definition_items_select_visible on public.definition_items
for select to authenticated
using (
  public.is_admin()
  or (active and scope = 'system')
  or (active and scope = 'user' and owner_user_id = auth.uid())
);

create policy definition_items_insert_user on public.definition_items
for insert to authenticated
with check (
  (scope = 'user' and owner_user_id = auth.uid())
  or public.is_admin()
);

create policy definition_items_update_user on public.definition_items
for update to authenticated
using (
  (scope = 'user' and owner_user_id = auth.uid())
  or public.is_admin()
)
with check (
  (scope = 'user' and owner_user_id = auth.uid())
  or public.is_admin()
);

create policy games_select_participant_or_admin on public.games
for select to authenticated
using (
  owner_user_id = auth.uid()
  or public.is_admin()
  or exists (
    select 1 from public.game_participants gp
    where gp.game_id = games.game_id
      and gp.user_id = auth.uid()
  )
);

create policy game_summaries_select_participant_or_admin on public.game_summaries
for select to authenticated
using (
  owner_user_id = auth.uid()
  or public.is_admin()
  or exists (
    select 1 from public.game_participants gp
    where gp.game_id = game_summaries.game_id
      and gp.user_id = auth.uid()
  )
);

create policy game_participants_select_self_or_admin on public.game_participants
for select to authenticated
using (user_id = auth.uid() or public.is_admin());

create policy game_public_turns_select_participant_or_admin on public.game_public_turns
for select to authenticated
using (
  public.is_admin()
  or exists (
    select 1 from public.game_participants gp
    where gp.game_id = game_public_turns.game_id
      and gp.user_id = auth.uid()
  )
);

create policy game_player_observations_select_self_or_admin on public.game_player_observations
for select to authenticated
using (user_id = auth.uid() or public.is_admin());

create policy game_reveals_admin_only on public.game_reveals
for select to authenticated
using (public.is_admin());

create policy game_operation_requests_insert_own on public.game_operation_requests
for insert to authenticated
with check (owner_user_id = auth.uid());

create policy game_operation_requests_select_own_or_admin on public.game_operation_requests
for select to authenticated
using (owner_user_id = auth.uid() or public.is_admin());

create policy llm_invocations_admin_only on public.llm_invocations
for select to authenticated
using (public.is_admin());

create policy audit_events_admin_only on public.audit_events
for select to authenticated
using (public.is_admin());

create policy retention_runs_admin_only on public.retention_runs
for select to authenticated
using (public.is_admin());

grant usage on schema public to authenticated;
grant select, insert, update on public.profiles to authenticated;
grant select, insert, update, delete on public.user_preferences to authenticated;
grant select, insert, update on public.definition_items to authenticated;
grant select on public.games to authenticated;
grant select on public.game_summaries to authenticated;
grant select on public.game_participants to authenticated;
grant select on public.game_public_turns to authenticated;
grant select on public.game_player_observations to authenticated;
grant select on public.game_reveals to authenticated;
grant select, insert on public.game_operation_requests to authenticated;
grant select on public.llm_invocations to authenticated;
grant select on public.audit_events to authenticated;
grant select on public.retention_runs to authenticated;

grant usage on schema private to service_role;
grant all on all tables in schema public to service_role;
grant all on all tables in schema private to service_role;
grant execute on function private.set_updated_at() to service_role;
