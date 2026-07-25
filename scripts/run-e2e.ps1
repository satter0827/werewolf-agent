param(
    [switch]$UpdateSnapshots
)

$ErrorActionPreference = "Stop"

$repository = Split-Path -Parent $PSScriptRoot
Push-Location $repository

try {
    $statusValues = @{}
    $statusOutput = & cmd /c "supabase status -o env 2>nul"
    if ($LASTEXITCODE -ne 0) {
        throw "Supabase local stack is not ready. Run supabase start first."
    }
    $statusOutput | ForEach-Object {
        if ($_ -match '^([A-Z_]+)="?(.*?)"?$') {
            $statusValues[$matches[1]] = $matches[2].TrimEnd('"')
        }
    }
    if (-not $statusValues.ContainsKey("PUBLISHABLE_KEY")) {
        throw "Supabase local stack is not ready. Run supabase start first."
    }

    $env:WEREWOLF_SUPABASE_URL = "http://host.docker.internal:54321"
    $env:WEREWOLF_SUPABASE_PUBLISHABLE_KEY = $statusValues["PUBLISHABLE_KEY"]
    $env:WEREWOLF_COMPOSE_SUPABASE_DB_DSN =
        "postgresql://postgres:postgres@host.docker.internal:54322/postgres"
    # Local tokens use the public CLI URL as `iss`, while containers reach JWKS
    # through the Docker host alias.
    $env:WEREWOLF_SUPABASE_JWT_ISSUER = "http://127.0.0.1:54321/auth/v1"
    $env:WEREWOLF_SUPABASE_JWKS_URL =
        "http://host.docker.internal:54321/auth/v1/.well-known/jwks.json"
    # Parallel browser projects share one Docker gateway address. Keep the
    # production default unchanged while avoiding cross-test rate-limit coupling.
    $env:WEREWOLF_API_RATE_LIMIT_REQUESTS = "1000"
    if ($UpdateSnapshots) {
        $env:PLAYWRIGHT_VISUAL_REGRESSION = "1"
    }
    $env:VITE_WEREWOLF_API_URL = "http://api:8000"
    $env:VITE_SUPABASE_URL = "http://host.docker.internal:54321"
    $env:VITE_SUPABASE_PUBLISHABLE_KEY = $statusValues["PUBLISHABLE_KEY"]

    docker compose --profile e2e build
    if ($LASTEXITCODE -ne 0) {
        throw "Docker image build failed."
    }
    docker compose --profile e2e run --rm migrate
    if ($LASTEXITCODE -ne 0) {
        throw "Migration service failed."
    }
    docker compose --profile e2e up -d --wait api worker frontend streamlit
    if ($LASTEXITCODE -ne 0) {
        throw "E2E services did not become healthy."
    }
    if ($UpdateSnapshots) {
        docker compose --profile e2e run --rm `
            --volume "./frontend/e2e:/workspace/frontend/e2e" `
            e2e npm run test:e2e -- --update-snapshots
    }
    else {
        docker compose --profile e2e run --rm e2e
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Browser E2E failed."
    }
}
finally {
    docker compose --profile e2e down
    Pop-Location
}
