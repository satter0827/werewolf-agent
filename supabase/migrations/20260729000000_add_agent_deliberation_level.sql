update private.game_runs
set config = jsonb_set(config, '{deliberation_level}', '"standard"'::jsonb, true)
where not config ? 'deliberation_level';

alter table private.llm_traces
  drop constraint if exists llm_traces_normalized_metrics_non_negative;

alter table private.llm_traces
  drop column if exists repair_attempts;

alter table private.llm_traces
  add constraint llm_traces_normalized_metrics_non_negative
  check (
    (input_tokens is null or input_tokens >= 0)
    and (output_tokens is null or output_tokens >= 0)
    and (total_tokens is null or total_tokens >= 0)
    and prompt_characters >= 0
    and prompt_bytes >= 0
    and response_characters >= 0
    and response_bytes >= 0
  ) not valid;
