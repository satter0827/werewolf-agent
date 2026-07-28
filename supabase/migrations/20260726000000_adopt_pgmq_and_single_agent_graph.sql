create extension if not exists pgmq;

do $$
begin
  if not exists (
    select 1 from pgmq.list_queues() where queue_name = 'game_operations'
  ) then
    perform pgmq.create('game_operations');
  end if;
end
$$;

alter table public.game_operation_requests
  add column if not exists queue_message_id bigint;

create unique index if not exists idx_game_operation_requests_queue_message
  on public.game_operation_requests (queue_message_id)
  where queue_message_id is not null;

update public.game_operation_requests
set status = 'failed',
    error_payload = jsonb_build_object(
      'type', 'tag:werewolf-agent,2026:problem:operation.upgrade_interrupted',
      'title', 'Operation Interrupted by Upgrade',
      'status', 409,
      'code', 'operation.upgrade_interrupted',
      'detail', 'The queued operation must be submitted again.',
      'instance', 'database-migration'
    ),
    completed_at = timezone('utc', now())
where status in ('queued', 'running');

drop index if exists public.idx_game_operation_requests_queue;

alter table public.game_operation_requests
  drop column if exists claimed_until;

update private.game_snapshots
set config = config - 'agent_strategy_id'
where config ? 'agent_strategy_id';

update public.game_operation_requests
set request_payload = request_payload - 'agent_strategy_id' - 'decision_graph_id'
where request_payload ? 'agent_strategy_id'
   or request_payload ? 'decision_graph_id';

update private.llm_traces
set request_payload = request_payload - 'agent_strategy_id' - 'decision_graph_id'
where request_payload ? 'agent_strategy_id'
   or request_payload ? 'decision_graph_id';
