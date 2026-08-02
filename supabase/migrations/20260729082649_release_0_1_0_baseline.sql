
-- Werewolf Agent 0.1.0 baseline.
-- This migration defines a new database from scratch and does not upgrade pre-release data.

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


CREATE EXTENSION IF NOT EXISTS "pg_net" WITH SCHEMA "extensions";






CREATE SCHEMA IF NOT EXISTS "private";


ALTER SCHEMA "private" OWNER TO "postgres";


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgmq";

SELECT "pgmq"."create"('game_operations');






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";






CREATE OR REPLACE FUNCTION "private"."set_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO ''
    AS $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;


ALTER FUNCTION "private"."set_updated_at"() OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "private"."accepted_commands" (
    "game_id" "uuid" NOT NULL,
    "operation_id" "uuid" NOT NULL,
    "version" integer NOT NULL,
    "command_type" "text" NOT NULL,
    "actor_user_id" "uuid",
    "payload" "jsonb" NOT NULL,
    "checksum" "text" NOT NULL,
    "accepted_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    CONSTRAINT "accepted_commands_version_check" CHECK (("version" >= 1))
);


ALTER TABLE "private"."accepted_commands" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "private"."agent_decisions" (
    "decision_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "game_id" "uuid" NOT NULL,
    "operation_id" "uuid",
    "state_version" integer NOT NULL,
    "player_id" "text" NOT NULL,
    "decision" "jsonb" NOT NULL,
    "checksum" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    CONSTRAINT "agent_decisions_state_version_check" CHECK (("state_version" >= 1))
);


ALTER TABLE "private"."agent_decisions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "private"."audit_events" (
    "audit_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "actor_user_id" "uuid",
    "action" "text" NOT NULL,
    "target_type" "text",
    "target_id" "text",
    "metadata" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL
);


ALTER TABLE "private"."audit_events" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "private"."game_events" (
    "game_id" "uuid" NOT NULL,
    "sequence" integer NOT NULL,
    "event_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "visibility" "text" NOT NULL,
    "phase" "text",
    "day" integer,
    "actor_id" "text",
    "event_type" "text" NOT NULL,
    "payload" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "occurred_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "version" integer DEFAULT 1 NOT NULL,
    "checksum" "text" DEFAULT ''::"text" NOT NULL,
    CONSTRAINT "game_events_day_check" CHECK (("day" >= 0)),
    CONSTRAINT "game_events_phase_check" CHECK (("phase" = ANY (ARRAY['night'::"text", 'day_discussion'::"text", 'voting'::"text", 'finished'::"text"]))),
    CONSTRAINT "game_events_sequence_check" CHECK (("sequence" >= 1)),
    CONSTRAINT "game_events_version_check" CHECK (("version" >= 1)),
    CONSTRAINT "game_events_visibility_check" CHECK (("visibility" = ANY (ARRAY['public'::"text", 'player_private'::"text", 'private'::"text", 'debug'::"text"])))
);


ALTER TABLE "private"."game_events" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "private"."game_player_observations" (
    "game_id" "uuid" NOT NULL,
    "player_id" "text" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "state_version" integer NOT NULL,
    "observation" "jsonb" NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    CONSTRAINT "game_player_observations_state_version_check" CHECK (("state_version" >= 1))
);


ALTER TABLE "private"."game_player_observations" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "private"."game_reveals" (
    "game_id" "uuid" NOT NULL,
    "reveal_payload" "jsonb" NOT NULL,
    "state_version" integer NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    CONSTRAINT "game_reveals_state_version_check" CHECK (("state_version" >= 1))
);


ALTER TABLE "private"."game_reveals" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "private"."game_snapshots" (
    "game_id" "uuid" NOT NULL,
    "config" "jsonb" NOT NULL,
    "private_state" "jsonb" NOT NULL,
    "pending_actions" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "checksum" "text" DEFAULT ''::"text" NOT NULL
);


ALTER TABLE "private"."game_snapshots" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "private"."game_state_versions" (
    "game_id" "uuid" NOT NULL,
    "version" integer NOT NULL,
    "private_state" "jsonb" NOT NULL,
    "public_state" "jsonb" NOT NULL,
    "checksum" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    CONSTRAINT "game_state_versions_version_check" CHECK (("version" >= 1))
);


ALTER TABLE "private"."game_state_versions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "private"."llm_traces" (
    "invocation_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "game_id" "uuid",
    "operation_id" "uuid",
    "trace_id" "text",
    "provider" "text" NOT NULL,
    "model" "text" NOT NULL,
    "player_id" "text",
    "phase" "text",
    "day" integer,
    "state_version" integer,
    "prompt_messages" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    "prompt_hash" "text" DEFAULT ''::"text" NOT NULL,
    "request_payload" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "raw_response" "jsonb",
    "parsed_decision" "jsonb",
    "error_payload" "jsonb",
    "latency_ms" numeric(12,3),
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "prompt_version" integer DEFAULT 1 NOT NULL,
    "setup_checksum" "text" DEFAULT ''::"text" NOT NULL,
    "mechanics_checksum" "text" DEFAULT ''::"text" NOT NULL,
    "observation_checksum" "text" DEFAULT ''::"text" NOT NULL,
    "validation_status" "text" DEFAULT ''::"text" NOT NULL,
    "fallback_used" boolean DEFAULT false NOT NULL,
    "fallback_reason" "text" DEFAULT ''::"text" NOT NULL,
    "provider_error" "text" DEFAULT ''::"text" NOT NULL,
    "input_tokens" integer,
    "output_tokens" integer,
    "total_tokens" integer,
    "usage_source" "text" DEFAULT 'unavailable'::"text" NOT NULL,
    "prompt_characters" integer DEFAULT 0 NOT NULL,
    "prompt_bytes" integer DEFAULT 0 NOT NULL,
    "response_characters" integer DEFAULT 0 NOT NULL,
    "response_bytes" integer DEFAULT 0 NOT NULL
);


ALTER TABLE "private"."llm_traces" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "private"."llm_usage" (
    "usage_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "actor_user_id" "uuid",
    "game_id" "uuid",
    "operation_id" "uuid",
    "provider" "text" NOT NULL,
    "model" "text" NOT NULL,
    "input_tokens" integer DEFAULT 0 NOT NULL,
    "output_tokens" integer DEFAULT 0 NOT NULL,
    "cost_micros" bigint DEFAULT 0 NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    CONSTRAINT "llm_usage_cost_micros_check" CHECK (("cost_micros" >= 0)),
    CONSTRAINT "llm_usage_input_tokens_check" CHECK (("input_tokens" >= 0)),
    CONSTRAINT "llm_usage_output_tokens_check" CHECK (("output_tokens" >= 0))
);


ALTER TABLE "private"."llm_usage" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "private"."user_setup_revisions" (
    "setup_id" "uuid" NOT NULL,
    "revision" integer NOT NULL,
    "schema_version" "text" NOT NULL,
    "document" "jsonb" NOT NULL,
    "setup_checksum" "text" NOT NULL,
    "mechanics_checksum" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    CONSTRAINT "user_setup_revisions_mechanics_checksum_check" CHECK (("length"("mechanics_checksum") = 64)),
    CONSTRAINT "user_setup_revisions_revision_check" CHECK (("revision" >= 1)),
    CONSTRAINT "user_setup_revisions_schema_version_check" CHECK (("schema_version" = '0.6.0'::"text")),
    CONSTRAINT "user_setup_revisions_setup_checksum_check" CHECK (("length"("setup_checksum") = 64))
);


ALTER TABLE "private"."user_setup_revisions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "private"."user_setups" (
    "setup_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "owner_user_id" "uuid" NOT NULL,
    "display_name" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    CONSTRAINT "user_setups_display_name_check" CHECK ((("length"("btrim"("display_name")) >= 1) AND ("length"("btrim"("display_name")) <= 120)))
);


ALTER TABLE "private"."user_setups" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."game_operation_requests" (
    "request_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "owner_user_id" "uuid" DEFAULT "auth"."uid"() NOT NULL,
    "operation_type" "text" NOT NULL,
    "status" "text" DEFAULT 'queued'::"text" NOT NULL,
    "game_id" "uuid",
    "player_id" "text",
    "idempotency_key" "text",
    "request_payload" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "result_payload" "jsonb",
    "error_payload" "jsonb",
    "attempt_count" integer DEFAULT 0 NOT NULL,
    "worker_id" "text",
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "started_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "expected_version" integer,
    "request_hash" "text" DEFAULT ''::"text" NOT NULL,
    "llm_mode" "text" DEFAULT 'fake'::"text" NOT NULL,
    "queue_message_id" bigint,
    CONSTRAINT "game_operation_requests_attempt_count_check" CHECK (("attempt_count" >= 0)),
    CONSTRAINT "game_operation_requests_expected_version_check" CHECK (("expected_version" >= 1)),
    CONSTRAINT "game_operation_requests_llm_mode_check" CHECK (("llm_mode" = ANY (ARRAY['fake'::"text", 'paid'::"text"]))),
    CONSTRAINT "game_operation_requests_operation_type_check" CHECK (("operation_type" = ANY (ARRAY['create_game'::"text", 'advance_game'::"text", 'submit_action'::"text"]))),
    CONSTRAINT "game_operation_requests_status_check" CHECK (("status" = ANY (ARRAY['queued'::"text", 'running'::"text", 'succeeded'::"text", 'failed'::"text"])))
);


ALTER TABLE "public"."game_operation_requests" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."game_participants" (
    "game_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "player_id" "text" NOT NULL,
    "participant_role" "text" DEFAULT 'player'::"text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    CONSTRAINT "game_participants_participant_role_check" CHECK (("participant_role" = ANY (ARRAY['owner'::"text", 'player'::"text", 'observer'::"text"])))
);


ALTER TABLE "public"."game_participants" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."game_public_turns" (
    "game_id" "uuid" NOT NULL,
    "sequence" integer NOT NULL,
    "event_sequence" integer NOT NULL,
    "version" integer NOT NULL,
    "phase" "text",
    "day" integer,
    "actor_id" "text",
    "event_type" "text" NOT NULL,
    "payload" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "occurred_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    CONSTRAINT "game_public_turns_day_check" CHECK (("day" >= 0)),
    CONSTRAINT "game_public_turns_event_sequence_check" CHECK (("event_sequence" >= 1)),
    CONSTRAINT "game_public_turns_phase_check" CHECK (("phase" = ANY (ARRAY['night'::"text", 'day_discussion'::"text", 'voting'::"text", 'finished'::"text"]))),
    CONSTRAINT "game_public_turns_sequence_check" CHECK (("sequence" >= 1)),
    CONSTRAINT "game_public_turns_version_check" CHECK (("version" >= 1))
);


ALTER TABLE "public"."game_public_turns" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."game_summaries" (
    "game_id" "uuid" NOT NULL,
    "owner_user_id" "uuid",
    "status" "text" NOT NULL,
    "phase" "text" NOT NULL,
    "day" integer NOT NULL,
    "version" integer NOT NULL,
    "seed" bigint,
    "player_count" integer NOT NULL,
    "alive_count" integer NOT NULL,
    "winner" "text",
    "step_count" integer NOT NULL,
    "turn_count" integer NOT NULL,
    "created_at" timestamp with time zone NOT NULL,
    "updated_at" timestamp with time zone NOT NULL,
    "completed_at" timestamp with time zone,
    "scenario_id" "text",
    "scenario_name" "text",
    "theme" "jsonb",
    CONSTRAINT "game_summaries_alive_count_check" CHECK (("alive_count" >= 0)),
    CONSTRAINT "game_summaries_day_check" CHECK (("day" >= 0)),
    CONSTRAINT "game_summaries_phase_check" CHECK (("phase" = ANY (ARRAY['night'::"text", 'day_discussion'::"text", 'voting'::"text", 'finished'::"text"]))),
    CONSTRAINT "game_summaries_player_count_check" CHECK (("player_count" >= 0)),
    CONSTRAINT "game_summaries_status_check" CHECK (("status" = ANY (ARRAY['running'::"text", 'completed'::"text"]))),
    CONSTRAINT "game_summaries_step_count_check" CHECK (("step_count" >= 0)),
    CONSTRAINT "game_summaries_turn_count_check" CHECK (("turn_count" >= 0)),
    CONSTRAINT "game_summaries_version_check" CHECK (("version" >= 1)),
    CONSTRAINT "game_summaries_winner_check" CHECK (("winner" = ANY (ARRAY['village'::"text", 'werewolf'::"text", 'fox'::"text"])))
);


ALTER TABLE "public"."game_summaries" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."games" (
    "game_id" "uuid" NOT NULL,
    "owner_user_id" "uuid",
    "status" "text" NOT NULL,
    "phase" "text" NOT NULL,
    "day" integer NOT NULL,
    "version" integer NOT NULL,
    "seed" bigint,
    "scenario_id" "text",
    "scenario_name" "text",
    "narration_mode" "text" DEFAULT 'standard'::"text" NOT NULL,
    "public_state" "jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "completed_at" timestamp with time zone,
    "llm_mode" "text" DEFAULT 'fake'::"text" NOT NULL,
    "state_checksum" "text" DEFAULT ''::"text" NOT NULL,
    CONSTRAINT "games_day_check" CHECK (("day" >= 0)),
    CONSTRAINT "games_llm_mode_check" CHECK (("llm_mode" = ANY (ARRAY['fake'::"text", 'paid'::"text"]))),
    CONSTRAINT "games_phase_check" CHECK (("phase" = ANY (ARRAY['night'::"text", 'day_discussion'::"text", 'voting'::"text", 'finished'::"text"]))),
    CONSTRAINT "games_status_check" CHECK (("status" = ANY (ARRAY['running'::"text", 'completed'::"text"]))),
    CONSTRAINT "games_version_check" CHECK (("version" >= 1))
);


ALTER TABLE "public"."games" OWNER TO "postgres";


ALTER TABLE ONLY "private"."accepted_commands"
    ADD CONSTRAINT "accepted_commands_game_id_version_key" UNIQUE ("game_id", "version");



ALTER TABLE ONLY "private"."accepted_commands"
    ADD CONSTRAINT "accepted_commands_pkey" PRIMARY KEY ("operation_id");



ALTER TABLE ONLY "private"."agent_decisions"
    ADD CONSTRAINT "agent_decisions_pkey" PRIMARY KEY ("decision_id");



ALTER TABLE ONLY "private"."audit_events"
    ADD CONSTRAINT "audit_events_pkey" PRIMARY KEY ("audit_id");



ALTER TABLE ONLY "private"."game_events"
    ADD CONSTRAINT "game_events_pkey" PRIMARY KEY ("game_id", "sequence");



ALTER TABLE ONLY "private"."game_player_observations"
    ADD CONSTRAINT "game_player_observations_pkey" PRIMARY KEY ("game_id", "player_id", "user_id");



ALTER TABLE ONLY "private"."game_reveals"
    ADD CONSTRAINT "game_reveals_pkey" PRIMARY KEY ("game_id");



ALTER TABLE ONLY "private"."game_snapshots"
    ADD CONSTRAINT "game_snapshots_pkey" PRIMARY KEY ("game_id");



ALTER TABLE ONLY "private"."game_state_versions"
    ADD CONSTRAINT "game_state_versions_pkey" PRIMARY KEY ("game_id", "version");



ALTER TABLE "private"."llm_traces"
    ADD CONSTRAINT "llm_traces_normalized_metrics_non_negative" CHECK (((("input_tokens" IS NULL) OR ("input_tokens" >= 0)) AND (("output_tokens" IS NULL) OR ("output_tokens" >= 0)) AND (("total_tokens" IS NULL) OR ("total_tokens" >= 0)) AND ("prompt_characters" >= 0) AND ("prompt_bytes" >= 0) AND ("response_characters" >= 0) AND ("response_bytes" >= 0))) NOT VALID;



ALTER TABLE ONLY "private"."llm_traces"
    ADD CONSTRAINT "llm_traces_pkey" PRIMARY KEY ("invocation_id");



ALTER TABLE "private"."llm_traces"
    ADD CONSTRAINT "llm_traces_prompt_version_positive" CHECK (("prompt_version" >= 1)) NOT VALID;



ALTER TABLE ONLY "private"."llm_usage"
    ADD CONSTRAINT "llm_usage_pkey" PRIMARY KEY ("usage_id");



ALTER TABLE ONLY "private"."user_setup_revisions"
    ADD CONSTRAINT "user_setup_revisions_pkey" PRIMARY KEY ("setup_id", "revision");



ALTER TABLE ONLY "private"."user_setups"
    ADD CONSTRAINT "user_setups_pkey" PRIMARY KEY ("setup_id");



ALTER TABLE ONLY "public"."game_operation_requests"
    ADD CONSTRAINT "game_operation_requests_owner_user_id_idempotency_key_key" UNIQUE ("owner_user_id", "idempotency_key");



ALTER TABLE ONLY "public"."game_operation_requests"
    ADD CONSTRAINT "game_operation_requests_pkey" PRIMARY KEY ("request_id");



ALTER TABLE ONLY "public"."game_participants"
    ADD CONSTRAINT "game_participants_pkey" PRIMARY KEY ("game_id", "user_id", "player_id");



ALTER TABLE ONLY "public"."game_public_turns"
    ADD CONSTRAINT "game_public_turns_pkey" PRIMARY KEY ("game_id", "sequence");



ALTER TABLE ONLY "public"."game_summaries"
    ADD CONSTRAINT "game_summaries_pkey" PRIMARY KEY ("game_id");



ALTER TABLE ONLY "public"."games"
    ADD CONSTRAINT "games_pkey" PRIMARY KEY ("game_id");



CREATE INDEX "idx_accepted_commands_game_version" ON "private"."accepted_commands" USING "btree" ("game_id", "version");



CREATE INDEX "idx_agent_decisions_game_version" ON "private"."agent_decisions" USING "btree" ("game_id", "state_version");



CREATE INDEX "idx_game_state_versions_game_version" ON "private"."game_state_versions" USING "btree" ("game_id", "version");



CREATE INDEX "idx_llm_traces_game_created" ON "private"."llm_traces" USING "btree" ("game_id", "created_at" DESC);



CREATE INDEX "idx_llm_usage_actor_created" ON "private"."llm_usage" USING "btree" ("actor_user_id", "created_at" DESC);



CREATE INDEX "idx_private_game_events_game_sequence" ON "private"."game_events" USING "btree" ("game_id", "sequence");



CREATE INDEX "idx_user_setup_revisions_created" ON "private"."user_setup_revisions" USING "btree" ("setup_id", "created_at" DESC);



CREATE INDEX "idx_user_setups_owner_created" ON "private"."user_setups" USING "btree" ("owner_user_id", "created_at" DESC);



CREATE UNIQUE INDEX "idx_game_operation_requests_queue_message" ON "public"."game_operation_requests" USING "btree" ("queue_message_id") WHERE ("queue_message_id" IS NOT NULL);



CREATE INDEX "idx_game_participants_user" ON "public"."game_participants" USING "btree" ("user_id", "game_id");



CREATE INDEX "idx_game_public_turns_game_sequence" ON "public"."game_public_turns" USING "btree" ("game_id", "sequence");



CREATE INDEX "idx_game_summaries_display" ON "public"."game_summaries" USING "btree" ("updated_at" DESC, "created_at" DESC);



CREATE OR REPLACE TRIGGER "game_operation_requests_set_updated_at" BEFORE UPDATE ON "public"."game_operation_requests" FOR EACH ROW EXECUTE FUNCTION "private"."set_updated_at"();



CREATE OR REPLACE TRIGGER "games_set_updated_at" BEFORE UPDATE ON "public"."games" FOR EACH ROW EXECUTE FUNCTION "private"."set_updated_at"();



ALTER TABLE ONLY "private"."accepted_commands"
    ADD CONSTRAINT "accepted_commands_actor_user_id_fkey" FOREIGN KEY ("actor_user_id") REFERENCES "auth"."users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "private"."accepted_commands"
    ADD CONSTRAINT "accepted_commands_game_id_fkey" FOREIGN KEY ("game_id") REFERENCES "public"."games"("game_id") ON DELETE CASCADE;



ALTER TABLE ONLY "private"."accepted_commands"
    ADD CONSTRAINT "accepted_commands_operation_id_fkey" FOREIGN KEY ("operation_id") REFERENCES "public"."game_operation_requests"("request_id") ON DELETE CASCADE;



ALTER TABLE ONLY "private"."agent_decisions"
    ADD CONSTRAINT "agent_decisions_game_id_fkey" FOREIGN KEY ("game_id") REFERENCES "public"."games"("game_id") ON DELETE CASCADE;



ALTER TABLE ONLY "private"."agent_decisions"
    ADD CONSTRAINT "agent_decisions_operation_id_fkey" FOREIGN KEY ("operation_id") REFERENCES "public"."game_operation_requests"("request_id") ON DELETE SET NULL;



ALTER TABLE ONLY "private"."audit_events"
    ADD CONSTRAINT "audit_events_actor_user_id_fkey" FOREIGN KEY ("actor_user_id") REFERENCES "auth"."users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "private"."game_events"
    ADD CONSTRAINT "game_events_game_id_fkey" FOREIGN KEY ("game_id") REFERENCES "public"."games"("game_id") ON DELETE CASCADE;



ALTER TABLE ONLY "private"."game_player_observations"
    ADD CONSTRAINT "game_player_observations_game_id_fkey" FOREIGN KEY ("game_id") REFERENCES "public"."games"("game_id") ON DELETE CASCADE;



ALTER TABLE ONLY "private"."game_player_observations"
    ADD CONSTRAINT "game_player_observations_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "private"."game_reveals"
    ADD CONSTRAINT "game_reveals_game_id_fkey" FOREIGN KEY ("game_id") REFERENCES "public"."games"("game_id") ON DELETE CASCADE;



ALTER TABLE ONLY "private"."game_snapshots"
    ADD CONSTRAINT "game_snapshots_game_id_fkey" FOREIGN KEY ("game_id") REFERENCES "public"."games"("game_id") ON DELETE CASCADE;



ALTER TABLE ONLY "private"."game_state_versions"
    ADD CONSTRAINT "game_state_versions_game_id_fkey" FOREIGN KEY ("game_id") REFERENCES "public"."games"("game_id") ON DELETE CASCADE;



ALTER TABLE ONLY "private"."llm_traces"
    ADD CONSTRAINT "llm_traces_game_id_fkey" FOREIGN KEY ("game_id") REFERENCES "public"."games"("game_id") ON DELETE SET NULL;



ALTER TABLE ONLY "private"."llm_traces"
    ADD CONSTRAINT "llm_traces_operation_id_fkey" FOREIGN KEY ("operation_id") REFERENCES "public"."game_operation_requests"("request_id") ON DELETE SET NULL;



ALTER TABLE ONLY "private"."llm_usage"
    ADD CONSTRAINT "llm_usage_actor_user_id_fkey" FOREIGN KEY ("actor_user_id") REFERENCES "auth"."users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "private"."llm_usage"
    ADD CONSTRAINT "llm_usage_game_id_fkey" FOREIGN KEY ("game_id") REFERENCES "public"."games"("game_id") ON DELETE SET NULL;



ALTER TABLE ONLY "private"."llm_usage"
    ADD CONSTRAINT "llm_usage_operation_id_fkey" FOREIGN KEY ("operation_id") REFERENCES "public"."game_operation_requests"("request_id") ON DELETE SET NULL;



ALTER TABLE ONLY "private"."user_setup_revisions"
    ADD CONSTRAINT "user_setup_revisions_setup_id_fkey" FOREIGN KEY ("setup_id") REFERENCES "private"."user_setups"("setup_id") ON DELETE CASCADE;



ALTER TABLE ONLY "private"."user_setups"
    ADD CONSTRAINT "user_setups_owner_user_id_fkey" FOREIGN KEY ("owner_user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."game_operation_requests"
    ADD CONSTRAINT "game_operation_requests_owner_user_id_fkey" FOREIGN KEY ("owner_user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."game_participants"
    ADD CONSTRAINT "game_participants_game_id_fkey" FOREIGN KEY ("game_id") REFERENCES "public"."games"("game_id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."game_participants"
    ADD CONSTRAINT "game_participants_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."game_public_turns"
    ADD CONSTRAINT "game_public_turns_game_id_fkey" FOREIGN KEY ("game_id") REFERENCES "public"."games"("game_id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."game_summaries"
    ADD CONSTRAINT "game_summaries_game_id_fkey" FOREIGN KEY ("game_id") REFERENCES "public"."games"("game_id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."game_summaries"
    ADD CONSTRAINT "game_summaries_owner_user_id_fkey" FOREIGN KEY ("owner_user_id") REFERENCES "auth"."users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."games"
    ADD CONSTRAINT "games_owner_user_id_fkey" FOREIGN KEY ("owner_user_id") REFERENCES "auth"."users"("id") ON DELETE SET NULL;



ALTER TABLE "private"."game_player_observations" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "private"."game_reveals" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "private"."user_setup_revisions" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "user_setup_revisions_owner_select" ON "private"."user_setup_revisions" FOR SELECT TO "authenticated" USING (((EXISTS ( SELECT 1
   FROM "private"."user_setups" "setups"
  WHERE (("setups"."setup_id" = "user_setup_revisions"."setup_id") AND ("setups"."owner_user_id" = ( SELECT "auth"."uid"() AS "uid"))))) AND (COALESCE(((( SELECT "auth"."jwt"()) ->> 'is_anonymous'::"text"))::boolean, false) = false)));



ALTER TABLE "private"."user_setups" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "user_setups_owner_select" ON "private"."user_setups" FOR SELECT TO "authenticated" USING (((( SELECT "auth"."uid"() AS "uid") IS NOT NULL) AND (( SELECT "auth"."uid"() AS "uid") = "owner_user_id") AND (COALESCE(((( SELECT "auth"."jwt"()) ->> 'is_anonymous'::"text"))::boolean, false) = false)));



ALTER TABLE "public"."game_operation_requests" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "game_operation_requests_insert_own" ON "public"."game_operation_requests" FOR INSERT TO "authenticated" WITH CHECK (("owner_user_id" = ( SELECT "auth"."uid"() AS "uid")));



ALTER TABLE "public"."game_participants" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."game_public_turns" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."game_summaries" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."games" ENABLE ROW LEVEL SECURITY;




ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";





GRANT USAGE ON SCHEMA "private" TO "service_role";



GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";




























































































































































GRANT ALL ON FUNCTION "private"."set_updated_at"() TO "service_role";


















GRANT ALL ON TABLE "private"."accepted_commands" TO "service_role";



GRANT ALL ON TABLE "private"."agent_decisions" TO "service_role";



GRANT ALL ON TABLE "private"."audit_events" TO "service_role";



GRANT ALL ON TABLE "private"."game_events" TO "service_role";



GRANT ALL ON TABLE "private"."game_player_observations" TO "service_role";



GRANT ALL ON TABLE "private"."game_reveals" TO "service_role";



GRANT ALL ON TABLE "private"."game_snapshots" TO "service_role";



GRANT ALL ON TABLE "private"."game_state_versions" TO "service_role";



GRANT ALL ON TABLE "private"."llm_traces" TO "service_role";



GRANT ALL ON TABLE "private"."llm_usage" TO "service_role";



GRANT SELECT,INSERT ON TABLE "private"."user_setup_revisions" TO "service_role";



GRANT SELECT,INSERT ON TABLE "private"."user_setups" TO "service_role";



GRANT ALL ON TABLE "public"."game_operation_requests" TO "service_role";



GRANT ALL ON TABLE "public"."game_participants" TO "service_role";



GRANT ALL ON TABLE "public"."game_public_turns" TO "service_role";



GRANT ALL ON TABLE "public"."game_summaries" TO "service_role";



GRANT ALL ON TABLE "public"."games" TO "service_role";









ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" REVOKE ALL ON SEQUENCES FROM "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" REVOKE ALL ON SEQUENCES FROM "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" REVOKE ALL ON FUNCTIONS FROM "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" REVOKE ALL ON FUNCTIONS FROM "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" REVOKE ALL ON TABLES FROM "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" REVOKE ALL ON TABLES FROM "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";

REVOKE ALL ON ALL TABLES IN SCHEMA "public" FROM "anon", "authenticated";
REVOKE ALL ON ALL SEQUENCES IN SCHEMA "public" FROM "anon", "authenticated";
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA "public" FROM "anon", "authenticated";
REVOKE ALL ON ALL TABLES IN SCHEMA "private" FROM "anon", "authenticated";
REVOKE ALL ON ALL SEQUENCES IN SCHEMA "private" FROM "anon", "authenticated";
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA "private" FROM "anon", "authenticated";
































--
-- Dumped schema changes for auth and storage
--
