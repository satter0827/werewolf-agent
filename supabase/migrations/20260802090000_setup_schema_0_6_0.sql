-- Accept only setup documents owned by the current application contract.
alter table private.user_setup_revisions
  drop constraint user_setup_revisions_schema_version_check;

alter table private.user_setup_revisions
  add constraint user_setup_revisions_schema_version_check
  check (schema_version = '0.6.0');
