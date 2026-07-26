alter table private.llm_traces
  add column if not exists validation_status text not null default '',
  add column if not exists repair_attempts integer not null default 0,
  add column if not exists fallback_used boolean not null default false,
  add column if not exists fallback_reason text not null default '',
  add column if not exists provider_error text not null default '',
  add column if not exists input_tokens integer,
  add column if not exists output_tokens integer,
  add column if not exists total_tokens integer,
  add column if not exists usage_source text not null default 'unavailable',
  add column if not exists prompt_characters integer not null default 0,
  add column if not exists prompt_bytes integer not null default 0,
  add column if not exists response_characters integer not null default 0,
  add column if not exists response_bytes integer not null default 0;

alter table private.llm_traces
  add constraint llm_traces_normalized_metrics_non_negative
  check (
    repair_attempts >= 0
    and (input_tokens is null or input_tokens >= 0)
    and (output_tokens is null or output_tokens >= 0)
    and (total_tokens is null or total_tokens >= 0)
    and prompt_characters >= 0
    and prompt_bytes >= 0
    and response_characters >= 0
    and response_bytes >= 0
  ) not valid;
