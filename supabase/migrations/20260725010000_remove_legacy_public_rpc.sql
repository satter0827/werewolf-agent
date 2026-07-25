-- Authorization is enforced by FastAPI and verified Supabase JWT claims.
-- Remove the obsolete PostgREST-callable helper and its unused RLS policies.
drop function if exists public.is_admin() cascade;
