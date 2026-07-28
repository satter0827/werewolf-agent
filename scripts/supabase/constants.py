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
SUPPORTED_CLI_VERSION = "2.104.0"
