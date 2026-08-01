-- Expose only the Auth decisions required by each runtime role.
create or replace function private.is_auth_session_active(
  expected_user_id text,
  expected_session_id text
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from auth.sessions session
    where session.user_id::text = expected_user_id
      and session.id::text = expected_session_id
  )
$$;

create or replace function private.auth_user_is_anonymous(expected_user_id text)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select user_record.is_anonymous
  from auth.users user_record
  where user_record.id::text = expected_user_id
  limit 1
$$;

revoke all on function private.is_auth_session_active(text, text) from public;
revoke all on function private.auth_user_is_anonymous(text) from public;
revoke all on auth.users from werewolf_worker;
revoke usage on schema auth from werewolf_worker;

grant execute on function private.is_auth_session_active(text, text) to werewolf_api;
grant execute on function private.auth_user_is_anonymous(text) to werewolf_worker;
