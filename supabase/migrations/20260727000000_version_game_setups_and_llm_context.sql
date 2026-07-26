alter table private.llm_traces
  add column if not exists prompt_version integer not null default 1,
  add column if not exists setup_checksum text not null default '',
  add column if not exists mechanics_checksum text not null default '',
  add column if not exists observation_checksum text not null default '';

alter table private.llm_traces
  add constraint llm_traces_prompt_version_positive
  check (prompt_version >= 1) not valid;

alter table public.game_summaries
  drop constraint if exists game_summaries_winner_check;

alter table public.game_summaries
  add constraint game_summaries_winner_check
  check (winner in ('village', 'werewolf', 'fox'));

alter table public.game_summaries
  add column if not exists scenario_id text,
  add column if not exists scenario_name text,
  add column if not exists theme jsonb;
