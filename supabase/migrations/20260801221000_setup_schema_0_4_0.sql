-- Preserve immutable legacy rows while accepting only the current schema from the application.
alter table private.user_setup_revisions
  drop constraint user_setup_revisions_schema_version_check;

alter table private.user_setup_revisions
  add constraint user_setup_revisions_schema_version_check
  check (schema_version in ('0.3.0', '0.4.0'));
