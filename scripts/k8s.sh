#!/usr/bin/env bash
# ConfPilot on Kubernetes (Docker Desktop's built-in cluster, or kind), plus breakage scenarios
# for Radar's AI SRE and Dash0's AI agent to diagnose.
#
#   scripts/k8s.sh up              build the image, deploy everything, wait until ready
#   scripts/k8s.sh open            open the app at http://localhost:8080 (port-forward; Ctrl+C to stop)
#   scripts/k8s.sh status          pods, services and recent events
#   scripts/k8s.sh break <what>    break something on purpose (see list below)
#   scripts/k8s.sh fix             undo every breakage
#   scripts/k8s.sh down            delete everything
#
# Breakages (each looks like a real incident):
#   es-down     Elasticsearch scaled to 0: app pods go NotReady, requests fail
#   bad-config  a "config change" points the app at the wrong Elasticsearch host
#   oom         memory limit cut to 160Mi: app pods are OOMKilled and crash-loop
#   bad-image   a deploy references an image tag that doesn't exist
#   ai-outage   the AI provider times out: app degrades to rule-based answers
#   bad-data    a corrupt talk record crashes 40% of plan requests (HTTP 500)
set -euo pipefail
cd "$(dirname "$0")/.."

NS=confpilot
K="kubectl -n $NS"
say()  { printf "\033[1;34m==>\033[0m %s\n" "$*"; }
fail() { printf "\033[1;31mError:\033[0m %s\n" "$*" >&2; exit 1; }

need_cluster() {
  command -v kubectl >/dev/null 2>&1 || fail "kubectl not found. It comes with Docker Desktop: Settings > Kubernetes > Enable Kubernetes."
  kubectl cluster-info >/dev/null 2>&1 || fail "No Kubernetes cluster is reachable.
  In Docker Desktop: Settings > Kubernetes > Enable Kubernetes > Apply, wait for the green 'Kubernetes running', then try again.
  Current context: $(kubectl config current-context 2>/dev/null || echo none)"
}

build_image() {
  say "Building the app image (confpilot:local)..."
  if docker compose version >/dev/null 2>&1; then docker compose build ingest; else docker build -t confpilot:local .; fi
  load_image
}

# Make the local image visible to the cluster. Docker Desktop's newer Kubernetes (kind-based) and kind
# clusters run each node in its own container with its own image store, so copy the image into every node.
load_image() {
  local ctx nodes node arch loaded=0
  ctx="$(kubectl config current-context)"
  if [[ "$ctx" == kind-* ]] && command -v kind >/dev/null 2>&1; then
    say "Loading the image into kind cluster ${ctx#kind-}..."
    kind load docker-image confpilot:local --name "${ctx#kind-}"
    return
  fi
  nodes="$(kubectl get nodes -o jsonpath='{.items[*].metadata.name}')"
  for node in $nodes; do
    if docker inspect "$node" >/dev/null 2>&1; then
      arch="$(docker exec "$node" uname -m | sed 's/x86_64/amd64/; s/aarch64/arm64/')"
      say "Copying the image into Kubernetes node $node ($arch)..."
      if ! docker save --platform "linux/$arch" confpilot:local 2>/dev/null \
           | docker exec -i "$node" ctr -n k8s.io images import - >/dev/null; then
        docker save confpilot:local | docker exec -i "$node" ctr -n k8s.io images import --all-platforms - >/dev/null
      fi
      loaded=1
    fi
  done
  if [[ $loaded == 0 ]]; then
    say "Kubernetes nodes aren't containers here; assuming the cluster shares Docker's images."
  fi
}

apply_secret() {
  # Every KEY=value line from .env (LLM key, Dash0 token, ...) becomes the confpilot-env Secret.
  if [[ -f .env ]]; then
    kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
    grep -E '^[A-Za-z_][A-Za-z0-9_]*=' .env | grep -vE '^(ES_URL|OTEL_EXPORTER_OTLP_ENDPOINT)=' > .env.k8s || true
    kubectl -n "$NS" create secret generic confpilot-env --from-env-file=.env.k8s --dry-run=client -o yaml | kubectl apply -f - >/dev/null
    rm -f .env.k8s
    say "Secret confpilot-env updated from .env"
  else
    say "No .env file: running without an AI key or Dash0 (rule-based answers, no telemetry export)."
  fi
}

wait_ready() {
  say "Waiting for Elasticsearch..."
  $K rollout status statefulset/elasticsearch --timeout=300s
  say "Loading talks (ingest job, about a minute)..."
  local i
  for i in $(seq 1 120); do
    if [[ "$($K get job confpilot-ingest -o jsonpath='{.status.succeeded}' 2>/dev/null)" == "1" ]]; then break; fi
    if $K get pods -l app.kubernetes.io/name=confpilot-ingest \
         -o jsonpath='{.items[*].status.containerStatuses[*].state.waiting.reason}' 2>/dev/null | grep -q ErrImageNeverPull; then
      image_hint; fail "The cluster can't see the confpilot:local image."
    fi
    sleep 5
  done
  if [[ "$($K get job confpilot-ingest -o jsonpath='{.status.succeeded}' 2>/dev/null)" != "1" ]]; then
    $K logs job/confpilot-ingest --tail=30 || true
    fail "The ingest job did not finish in 10 minutes (logs above)."
  fi
  say "Waiting for the app..."
  $K rollout status deployment/confpilot --timeout=300s
}

image_hint() {
  if $K get pods -o jsonpath='{.items[*].status.containerStatuses[*].state.waiting.reason}' 2>/dev/null | grep -q ErrImageNeverPull; then
    echo "Pods still can't see the local image (ErrImageNeverPull)."
    echo "Nodes: $(kubectl get nodes -o jsonpath='{.items[*].metadata.name}')   Context: $(kubectl config current-context)"
    echo "Paste this output to get help, or in Docker Desktop try Settings > General > untick"
    echo "'Use containerd for pulling and storing images', Apply, then run: $0 up"
  fi
}

case "${1:-}" in
  up)
    need_cluster
    build_image
    apply_secret
    $K delete job confpilot-ingest --ignore-not-found >/dev/null 2>&1 || true
    say "Applying k8s/confpilot.yaml..."
    kubectl apply -f k8s/confpilot.yaml
    # Replace app pods from an earlier attempt (e.g. stuck on ErrImageNeverPull) so they use the fresh image.
    $K delete pods -l app.kubernetes.io/name=confpilot --ignore-not-found --wait=false >/dev/null 2>&1 || true
    wait_ready || { image_hint; exit 1; }
    say "ConfPilot is running on Kubernetes. Open it with: scripts/k8s.sh open"
    ;;
  load)
    need_cluster
    load_image
    ;;
  open)
    need_cluster
    say "ConfPilot on http://localhost:8080 (Ctrl+C to stop)"
    (sleep 2; command -v open >/dev/null && open http://localhost:8080) &
    $K port-forward svc/confpilot 8080:80
    ;;
  status)
    need_cluster
    $K get pods,svc,jobs -o wide
    echo; say "Recent events"
    $K get events --sort-by=.lastTimestamp | tail -15
    image_hint
    ;;
  break)
    need_cluster
    case "${2:-}" in
      es-down)    $K scale statefulset/elasticsearch --replicas=0 ;;
      bad-config) $K set env deployment/confpilot ES_URL=http://elasticsearch-primary:9200 ;;
      oom)        $K set resources deployment/confpilot -c app --limits=memory=160Mi --requests=memory=128Mi ;;
      bad-image)  $K set image deployment/confpilot app=confpilot:v2-missing ;;
      ai-outage)  $K set env deployment/confpilot CHAOS_LLM_OUTAGE=true ;;
      bad-data)   $K set env deployment/confpilot CHAOS_BAD_DATA_RATE=0.4 ;;
      *) fail "Usage: $0 break es-down|bad-config|oom|bad-image|ai-outage|bad-data" ;;
    esac
    say "Broken: ${2}. Watch it in Radar (kubectl radar) or Dash0; undo with: $0 fix"
    ;;
  fix)
    need_cluster
    say "Undoing all breakages..."
    # set env leaves extra variables that 'apply' does not remove, so clear them explicitly.
    $K set env deployment/confpilot ES_URL- CHAOS_LLM_OUTAGE- CHAOS_BAD_DATA_RATE- >/dev/null 2>&1 || true
    kubectl apply -f k8s/confpilot.yaml >/dev/null
    $K rollout status statefulset/elasticsearch --timeout=300s
    $K rollout status deployment/confpilot --timeout=300s
    say "Back to normal."
    ;;
  down)
    need_cluster
    kubectl delete namespace "$NS" --ignore-not-found
    ;;
  *)
    sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
