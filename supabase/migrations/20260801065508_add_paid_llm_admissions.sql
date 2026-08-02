create table if not exists private.paid_llm_admissions (
  admission_id uuid default gen_random_uuid() primary key,
  operation_id uuid not null unique
    references public.game_operation_requests(request_id) on delete restrict,
  actor_user_id uuid not null,
  worker_id text not null,
  status text not null default 'active'
    check (status in ('active', 'completed', 'failed', 'expired')),
  reserved_at timestamptz not null default now(),
  expires_at timestamptz not null,
  released_at timestamptz,
  check (expires_at > reserved_at),
  check (
    (status = 'active' and released_at is null)
    or (status <> 'active' and released_at is not null)
  )
);

comment on table private.paid_llm_admissions is
  'Atomic paid-LLM advance budget and concurrency reservations.';

create index paid_llm_admissions_actor_reserved_idx
  on private.paid_llm_admissions (actor_user_id, reserved_at desc);
create index paid_llm_admissions_active_expires_idx
  on private.paid_llm_admissions (expires_at)
  where status = 'active';

revoke all on private.paid_llm_admissions from anon, authenticated, service_role;
grant select, insert, update on private.paid_llm_admissions to werewolf_worker;
