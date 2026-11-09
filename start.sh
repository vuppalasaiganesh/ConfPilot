#!/usr/bin/env bash
# ConfPilot: one command to start everything (Elasticsearch + data load + web app).
# Usage:  ./start.sh          start (or restart) everything
#         ./start.sh stop     stop everything
#         ./start.sh logs     follow the app logs
#         ./start.sh reset    stop and delete all data, then start fresh
#         ./start.sh tracing  start with OpenTelemetry tracing + Jaeger UI at http://localhost:16686
set -euo pipefail
cd "$(dirname "$0")"

URL="http://localhost:8000"
say()  { printf "\033[1;34m==>\033[0m %s\n" "$*"; }
fail() { printf "\033[1;31mError:\033[0m %s\n" "$*" >&2; exit 1; }

# 1. Docker installed?
command -v docker >/dev/null 2>&1 || fail "Docker is not installed.
  Install Docker Desktop from https://www.docker.com/products/docker-desktop/ , open it once, then run this again."

# 2. Docker running? On a Mac, try to open Docker Desktop and wait for it.
if ! docker info >/dev/null 2>&1; then
  if [[ "$(uname)" == "Darwin" ]]; then
    say "Starting Docker Desktop..."
    open -a Docker || true
    say "If Docker asks you to accept its terms, do that now. Waiting up to 3 minutes..."
  else
    say "Docker is not running. Start Docker Desktop (or 'sudo systemctl start docker')."
  fi
  for _ in $(seq 1 90); do docker info >/dev/null 2>&1 && break; sleep 2; done
  docker info >/dev/null 2>&1 || fail "Docker did not start. Open Docker Desktop, wait for it to say 'running', then try again."
fi

# 3. Compose available? Docker Desktop registers it on first launch; also look inside the app itself.
DESKTOP_COMPOSE="/Applications/Docker.app/Contents/Resources/cli-plugins/docker-compose"
if docker compose version >/dev/null 2>&1; then DC="docker compose"
elif [[ -x "$DESKTOP_COMPOSE" ]]; then DC="$DESKTOP_COMPOSE"
elif command -v docker-compose >/dev/null 2>&1; then DC="docker-compose"
else fail "Docker Compose is missing. Open Docker Desktop once (Applications > Docker), wait until it is running, then try again."; fi

case "${1:-start}" in
  stop)  $DC --profile tracing down; exit 0 ;;
  logs)  $DC logs -f app; exit 0 ;;
  reset) $DC --profile tracing down -v ;;
  tracing)
    export COMPOSE_PROFILES=tracing OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
    say "Tracing on: traces will be at http://localhost:16686 (service 'confpilot')" ;;
  start) ;;
  *) fail "Unknown option '$1'. Use: start | stop | logs | reset | tracing" ;;
esac

# 4. .env with optional LLM key (asked once, stored only on this computer).
if [[ ! -f .env ]]; then
  cp .env.example .env
  if [[ -t 0 ]]; then
    printf "Paste your Grok (xAI) API key for AI answers, or press Enter to skip: "
    read -rs KEY; echo
    if [[ -n "$KEY" ]]; then
      sed -i.bak "s|^LLM_API_KEY=.*|LLM_API_KEY=$KEY|" .env && rm -f .env.bak
      say "Key saved in .env (this file is git-ignored)."
    else
      say "No key: the app runs with rule-based answers. Add LLM_API_KEY to .env later and run ./start.sh again."
    fi
  fi
fi

# 5. Build and start. The first run downloads images and Python packages (5-10 minutes).
say "Building and starting ConfPilot (first run takes a few minutes)..."
$DC up --build -d

# 6. Wait for the app to answer, then open the browser.
say "Waiting for Elasticsearch, data load and the app..."
for i in $(seq 1 120); do
  if curl -fs "$URL/api/facets" >/dev/null 2>&1; then
    say "ConfPilot is running at $URL"
    if command -v open >/dev/null 2>&1; then open "$URL"; elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 || true; fi
    echo "Stop it with: ./start.sh stop     Logs: ./start.sh logs"
    exit 0
  fi
  if [[ "$($DC ps -a --format '{{.Service}} {{.State}} {{.ExitCode}}' 2>/dev/null | awk '$1=="ingest" && $2=="exited" && $3!="0"')" ]]; then
    $DC logs ingest | tail -20
    fail "Loading the data failed (logs above)."
  fi
  sleep 5
done
$DC ps
$DC logs --tail 30
fail "The app did not come up in 10 minutes. Logs are above. Elasticsearch needs about 2 GB of free memory in Docker Desktop."
