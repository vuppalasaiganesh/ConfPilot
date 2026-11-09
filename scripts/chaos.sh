#!/usr/bin/env bash
# Turn demo faults on and off while the app runs (needs CHAOS_ENABLED=true in .env).
#   scripts/chaos.sh slow      query embedding becomes slow (3 s per search)
#   scripts/chaos.sh ai        every AI call times out (app falls back to rule-based answers)
#   scripts/chaos.sh baddata   40% of searches hit a corrupt talk record -> HTTP 500s
#   scripts/chaos.sh off       back to normal
#   scripts/chaos.sh status    show what is on
# Set URL=http://... to target another deployment (e.g. the Kubernetes port-forward).
set -euo pipefail
URL="${URL:-http://localhost:8000}"
post() { curl -fsS -X POST "$URL/api/chaos" -H 'content-type: application/json' -d "$1"; echo; }
case "${1:-status}" in
  slow)    post '{"slow_search_ms": 3000}' ;;
  ai)      post '{"llm_outage": true}' ;;
  baddata) post '{"bad_data_rate": 0.4}' ;;
  off)     post '{"reset": true}' ;;
  status)  curl -fsS "$URL/api/chaos"; echo ;;
  *) echo "Usage: $0 slow|ai|baddata|off|status" >&2; exit 1 ;;
esac
