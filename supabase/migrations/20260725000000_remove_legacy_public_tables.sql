-- The second-stage runtime serves game data only through FastAPI.
-- Remove first-stage Data API tables that no current application path uses.
drop table if exists public.user_preferences;
drop table if exists public.profiles;
drop table if exists public.definition_items;
drop table if exists public.retention_runs;
