"""Supabase CLI の安定したローカル構成値。"""

LOCAL_EXCLUDED_SERVICES = (
    "edge-runtime",
    "imgproxy",
    "logflare",
    "mailpit",
    "postgres-meta",
    "realtime",
    "storage-api",
    "studio",
    "vector",
)

LOCAL_EXCLUDED_SERVICES_CSV = ",".join(LOCAL_EXCLUDED_SERVICES)

REQUIRED_LOCAL_IMAGES = (
    "public.ecr.aws/supabase/gotrue:v2.189.0",
    "public.ecr.aws/supabase/kong:2.8.1",
    "public.ecr.aws/supabase/postgres:17.6.1.132",
    "public.ecr.aws/supabase/postgrest:v14.12",
)
