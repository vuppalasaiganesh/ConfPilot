#!/usr/bin/env bash
# Check everything the demo needs and print PASS / WARN / FAIL for each item.
#   scripts/validate.sh
# Safe to run any time: it only reads, plus one test request to each running app.
# Never prints secrets.
cd "$(dirname "$0")/.."
URL="${URL:-http://localhost:8000}"
NS=confpilot
P=0; W=0; F=0
pass() { printf "  \033[32mPASS\033[0m  %s\n" "$*"; P=$((P+1)); }
warn() { printf "  \033[33mWARN\033[0m  %s\n" "$*"; W=$((W+1)); }
fail() { printf "  \033[31mFAIL\033[0m  %s\n" "$*"; F=$((F+1)); }
head() { printf "\n\033[1m%s\033[0m\n" "$*"; }
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1], {'d': d}))" "$1" 2>/dev/null; }
env_set() { grep -qE "^$1=.+" .env 2>/dev/null; }

head "Basics"
command -v python3 >/dev/null && pass "python3 found" || fail "python3 not found (needed by this check and scripts/load.py)"
docker info >/dev/null 2>&1 && pass "Docker is running" || fail "Docker is not running: open Docker Desktop"
[[ -f .env ]] && pass ".env exists" || warn ".env missing: cp .env.example .env"
git fetch -q origin main 2>/dev/null
if [[ "$(git rev-parse HEAD 2>/dev/null)" == "$(git rev-parse origin/main 2>/dev/null)" ]]; then pass "Code is up to date with GitHub"
else warn "Local code differs from GitHub: run git pull, then ./start.sh"; fi

head "Track 4: Elasticsearch app (docker compose, $URL)"
H="$(curl -fs -m 60 "$URL/healthz?deep=true")"
if [[ -z "$H" ]]; then
  fail "App not reachable at $URL: run ./start.sh"
else
  pass "App is up (version $(echo "$H" | json "d['version']"))"
  [[ "$(echo "$H" | json "d['elasticsearch']")" == "True" ]] && pass "Elasticsearch reachable" || fail "Elasticsearch not reachable"
  EMB="$(curl -fs "$URL/api/facets" | json "d['embedder']")"
  [[ "$EMB" == "fastembed" ]] && pass "Embeddings: fastembed (real meaning-based search)" \
    || warn "Embeddings: ${EMB:-unknown} (should be fastembed; check ./start.sh logs)"
  if [[ "$(echo "$H" | json "d['llm']['ok']")" == "True" ]]; then pass "AI on: $(echo "$H" | json "d['llm']['model']")"
  elif [[ "$(echo "$H" | json "d['llm']['configured']")" == "False" ]]; then warn "AI off: no LLM_API_KEY in .env (app still works, rule-based)"
  else warn "AI problem: $(echo "$H" | json "d['llm'].get('error')") | Fix: $(echo "$H" | json "d['llm'].get('hint')")"; fi
  R="$(curl -fs -m 90 -X POST "$URL/api/plan" -H 'content-type: application/json' -d '{"profile":"SRE into OpenTelemetry and eBPF"}')"
  if [[ -n "$R" ]]; then
    N="$(echo "$R" | json "len(d['agenda'])")"
    CLASH="$(echo "$R" | json "sum(1 for i,a in enumerate(d['agenda']) for b in d['agenda'][i+1:] if a['start']<b['end'] and b['start']<a['end'])")"
    [[ "${N:-0}" -ge 3 ]] && pass "Plan request: $N talks in $(echo "$R" | json "d['timings']['total']") ms" || fail "Plan returned ${N:-0} talks"
    [[ "$CLASH" == "0" ]] && pass "Agenda has no time clashes" || fail "Agenda has $CLASH clashes"
    [[ "$(echo "$R" | json "d['ai']['used']")" == "True" ]] && pass "AI wrote the reasons" \
      || warn "Reasons are rule-based: $(echo "$R" | json "d['ai']['notice']")"
  else fail "Plan request failed (try ./start.sh logs)"; fi
  W1="$(curl -fs -m 90 -X POST "$URL/api/plan" -H 'content-type: application/json' -d '{"profile":"How can we save money and help the planet?"}')"
  if [[ -n "$W1" ]]; then
    HITS="$(echo "$W1" | json "sum(1 for t in d['agenda'] if t['track']=='Cost + Sustainability')")"
    ONLY="$(echo "$W1" | json "sum(1 for t in d['agenda'] if all(m.startswith('semantic') for m in t.get('matched_by',[])))")"
    [[ "${HITS:-0}" -ge 2 ]] && pass "Meaning-only demo: $HITS of $(echo "$W1" | json "len(d['agenda'])") talks are cost/sustainability ($ONLY found by meaning only)" \
      || warn "Meaning-only demo found ${HITS:-0} cost/sustainability talks (check embeddings are fastembed)"
  fi
fi

head "Track 2: Observability (Dash0)"
if env_set DASH0_AUTH_TOKEN && env_set DASH0_OTLP_ENDPOINT; then
  pass "Dash0 endpoint and token set in .env"
  T="$(echo "$H" | json "d.get('telemetry')")"
  [[ "$T" == "dash0" ]] && pass "App is sending traces, metrics and logs to Dash0" \
    || fail "App isn't exporting to Dash0 (telemetry=$T): run ./start.sh to pick up .env"
else
  warn "Dash0 not configured: add DASH0_OTLP_ENDPOINT and DASH0_AUTH_TOKEN to .env, then ./start.sh"
fi
C="$(curl -fs "$URL/api/chaos")"
[[ "$(echo "$C" | json "d['runtime_toggle']")" == "True" ]] && pass "Fault injection ready (scripts/chaos.sh)" \
  || warn "Fault injection off: set CHAOS_ENABLED=true in .env, then ./start.sh"
[[ "$(echo "$C" | json "any([d['slow_search_ms'], d['llm_outage'], d['bad_data_rate']])")" == "True" ]] \
  && warn "A fault is switched on right now: scripts/chaos.sh off"

head "Track 3: Kubernetes + Radar"
if ! command -v kubectl >/dev/null; then fail "kubectl not found (comes with Docker Desktop)"
elif ! kubectl cluster-info >/dev/null 2>&1; then fail "No Kubernetes cluster: Docker Desktop > Settings > Kubernetes > Enable"
else
  pass "Kubernetes reachable (context $(kubectl config current-context))"
  if ! kubectl get ns "$NS" >/dev/null 2>&1; then fail "ConfPilot not deployed: scripts/k8s.sh up"
  else
    ESR="$(kubectl -n $NS get statefulset elasticsearch -o jsonpath='{.status.readyReplicas}' 2>/dev/null)"
    [[ "${ESR:-0}" -ge 1 ]] && pass "Elasticsearch pod ready" || fail "Elasticsearch pod not ready"
    JOB="$(kubectl -n $NS get job confpilot-ingest -o jsonpath='{.status.succeeded}' 2>/dev/null)"
    if [[ "$JOB" == "1" ]]; then pass "Talks loaded (ingest job succeeded)"
    elif kubectl -n $NS get job confpilot-ingest >/dev/null 2>&1; then fail "Ingest job hasn't succeeded: scripts/k8s.sh status"
    else pass "Ingest job finished earlier (cleaned up)"; fi
    READY="$(kubectl -n $NS get deploy confpilot -o jsonpath='{.status.readyReplicas}' 2>/dev/null)"
    WANT="$(kubectl -n $NS get deploy confpilot -o jsonpath='{.spec.replicas}' 2>/dev/null)"
    [[ "${READY:-0}" == "${WANT:-x}" ]] && pass "App pods ready ($READY/$WANT)" || fail "App pods ready ${READY:-0}/${WANT:-?}: scripts/k8s.sh status"
    BAD="$(kubectl -n $NS get pods -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.containerStatuses[*].state.waiting.reason}{"\n"}{end}' 2>/dev/null | awk 'NF>1')"
    [[ -z "$BAD" ]] && pass "No pods stuck (ImagePull / CrashLoop)" || fail "Stuck pods: $(echo $BAD)"
    KP="$(kubectl -n $NS exec deploy/confpilot -c app -- python -c "import json,urllib.request as u; r=u.urlopen(u.Request('http://localhost:8000/api/plan', data=json.dumps({'profile':'GitOps beginner'}).encode(), headers={'Content-Type':'application/json'}), timeout=90); print(len(json.load(r)['agenda']))" 2>/dev/null)"
    [[ "${KP:-0}" -ge 3 ]] && pass "Plan request inside the cluster: $KP talks" || fail "Plan request inside the cluster failed"
    CHG="$(kubectl -n $NS get deploy confpilot -o jsonpath='{.spec.template.spec.containers[0].env[*].name}' | tr ' ' '\n' | grep -E '^(ES_URL|CHAOS_)' | tr '\n' ' ')"
    [[ -z "$CHG" ]] || warn "A breakage is active ($CHG): scripts/k8s.sh fix"
  fi
fi
if command -v kubectl-radar >/dev/null || command -v radar >/dev/null; then pass "Radar installed (run: kubectl radar)"
else warn "Radar not found: brew install kubectl-radar"; fi

head "Track 1: AI code review (Gitar)"
N="$(ls .gitar/rules/*.md 2>/dev/null | wc -l | tr -d ' ')"
[[ "$N" -ge 1 ]] && pass "$N Gitar review rules in .gitar/rules" || fail "No Gitar rules found"
[[ -f .github/workflows/ci.yml ]] && pass "CI workflow present (results: GitHub > Actions)" || fail "CI workflow missing"
warn "Can't check from here whether the Gitar GitHub App is installed: github.com/apps search 'Gitar'"

printf "\n\033[1mResult:\033[0m %d passed, %d warnings, %d failed\n" "$P" "$W" "$F"
[[ $F -eq 0 ]]
