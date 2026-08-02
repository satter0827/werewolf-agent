alter table private.game_snapshots
add column seed bigint;

update private.game_snapshots snapshot
set seed = game.seed
from public.games game
where game.game_id = snapshot.game_id;

create function private.canonical_jsonb_20260801(payload jsonb)
returns text
language plpgsql
immutable
strict
set search_path = ''
as $$
declare
  canonical text;
begin
  case jsonb_typeof(payload)
    when 'object' then
      select '{' || coalesce(
        string_agg(
          to_jsonb(entry.key)::text || ':' || private.canonical_jsonb_20260801(entry.value),
          ',' order by entry.key collate "C"
        ),
        ''
      ) || '}'
      into canonical
      from jsonb_each(payload) as entry;
    when 'array' then
      select '[' || coalesce(
        string_agg(
          private.canonical_jsonb_20260801(entry.value),
          ',' order by entry.ordinality
        ),
        ''
      ) || ']'
      into canonical
      from jsonb_array_elements(payload) with ordinality as entry(value, ordinality);
    else
      canonical := payload::text;
  end case;
  return canonical;
end;
$$;

with normalized as (
  select
    game.game_id,
    game.version,
    snapshot.private_state,
    game.public_state - 'seed' as public_state
  from public.games game
  join private.game_snapshots snapshot on snapshot.game_id = game.game_id
)
update public.games game
set
  public_state = normalized.public_state,
  state_checksum = encode(
    extensions.digest(
      convert_to(
        private.canonical_jsonb_20260801(
          jsonb_build_object(
            'version', normalized.version,
            'private_state', normalized.private_state,
            'public_state', normalized.public_state
          )
        ),
        'UTF8'
      ),
      'sha256'
    ),
    'hex'
  )
from normalized
where game.game_id = normalized.game_id;

update public.game_operation_requests
set result_payload = jsonb_set(
  result_payload,
  '{state}',
  (result_payload -> 'state') - 'seed'
)
where result_payload -> 'state' ? 'seed';

drop function private.canonical_jsonb_20260801(jsonb);

alter table public.game_summaries drop column seed;
alter table public.games drop column seed;
