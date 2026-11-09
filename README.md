# ConfPilot: AI conference planner

**Cloud Native Hackathon, Track 4: Search & Vector Database ("Find the Right Talk")**

Describe yourself in plain English, for example *"backend dev moving into platform engineering, curious about
eBPF security, fairly new to Kubernetes"*. ConfPilot gives you back:

1. **A clash-free personal agenda.** Talks are found with Elasticsearch **hybrid search** (BM25 keyword +
   dense-vector kNN, fused with Reciprocal Rank Fusion). The planner then picks the best talk for each time slot.
2. **A reason for every talk.** An LLM (Grok by default; any OpenAI-compatible API works) explains why
   each talk fits *you*, and adds a summary and a few tips.
3. **A backup for each slot.** If a talk you want clashes with a better match, it becomes a one-click swap.
4. **A hallway matchmaker.** Attendees' "what I'm working on" notes are also vectors in Elasticsearch, so you
   get the 4 most relevant people to meet, each with an AI-written conversation opener.
5. **Follow-up chat.** Ask questions or change the agenda in plain English: *"swap anything on day 2 for AI
   talks"*, *"add a beginner GPU talk on Thursday"*, *"drop the policy talks"*, *"who is speaking about service
   mesh?"*. Each change goes through the same hybrid search and clash checker, so the agenda never double-books.
   Answers come with **Add** buttons.
6. **Calendar export.** Download the agenda as an `.ics` file.

The app works **without an LLM key**: it falls back to rule-based reasons, so a live demo can't break because of a
rate limit.

## Hackathon tracks

One project, four tracks. Each section is what to show the judges.

**Check everything at once:** `scripts/validate.sh` prints PASS / WARN / FAIL for every track (app, AI,
embeddings, meaning-only demo, Dash0, Kubernetes pods, Radar, Gitar files). Run it before the demo.

### Track 4: Search & Vector Database (Elasticsearch)
Elasticsearch is the core. Every request runs **hybrid search**: BM25 keyword search plus dense-vector kNN
(fastembed `bge-small` embeddings), fused with Reciprocal Rank Fusion. Attendee matchmaking is kNN over a second
index. On the page, the **Keyword #** / **Meaning #** badges show which search found each talk, and the
**✨ Meaning-only demo** finds talks with no words in common with the query.

### Track 2: Observability (Dash0)
The app sends **traces, metrics and logs** to Dash0 over OTLP. Each request is a trace: AI understanding →
`hybrid_search` (with the Elasticsearch calls and `embed_query` inside) → planning → AI explanation. Custom
metrics: `confpilot.search.duration`, `confpilot.llm.calls` (by model and outcome), `confpilot.llm.duration`,
`confpilot.ai.fallbacks`. Logs are linked to their traces.

1. Create a Dash0 account (free trial). Copy the **OTLP gRPC endpoint** and an **auth token**.
2. Add them to `.env`, then run `./start.sh`:
   ```
   DASH0_OTLP_ENDPOINT=https://ingress.<region>.aws.dash0.com:4317
   DASH0_AUTH_TOKEN=auth_...
   ```
3. Generate traffic: `python3 scripts/load.py`
4. Break something, then ask Dash0's AI agent what's wrong:
   - `scripts/chaos.sh slow`: searches take 3 s. The trace shows the time is in `embed_query`.
   - `scripts/chaos.sh ai`: the AI provider times out. Fallback metric jumps; error logs explain why.
   - `scripts/chaos.sh baddata`: 40% of plans fail with HTTP 500. The stack trace points at a talk record
     with no start time.
   - `scripts/chaos.sh off`: back to normal.

### Track 3: Kubernetes UI / AI SRE (Radar)
The app runs on Kubernetes with proper probes (`/readyz` fails when Elasticsearch is unreachable), resource
limits and pod identity on every trace.

1. Docker Desktop: **Settings → Kubernetes → Enable Kubernetes**, wait for "running".
2. Deploy: `scripts/k8s.sh up`, then open it: `scripts/k8s.sh open` (http://localhost:8080)
3. Install and run Radar: `brew install kubectl-radar`, then `kubectl radar`
4. Break the cluster and let Radar (or a coding agent through Radar's MCP server) find the root cause:

   | Command | What happens |
   |---|---|
   | `scripts/k8s.sh break es-down` | Elasticsearch scaled to 0; app pods go NotReady |
   | `scripts/k8s.sh break bad-config` | A "config change" points the app at a host that doesn't exist |
   | `scripts/k8s.sh break oom` | Memory limit cut; pods are OOMKilled and crash-loop |
   | `scripts/k8s.sh break bad-image` | A deploy references an image tag that doesn't exist |
   | `scripts/k8s.sh break ai-outage` | AI provider times out; the app degrades but stays up |
   | `scripts/k8s.sh break bad-data` | A corrupt record crashes 40% of plan requests |
   | `scripts/k8s.sh fix` | Undo everything |

   With Dash0 configured in `.env`, the same incidents show up in Dash0 with the pod name attached.

### Track 1: AI Code Review (Gitar)
- **CI** (`.github/workflows/ci.yml`): lint (ruff), 30+ unit tests, config validation, and an integration job
  that starts a real Elasticsearch, loads the data and smoke-tests the API, including a check that the agenda
  has no clashes.
- **Review rules** in `.gitar/rules/`: every AI call needs a fallback, the agenda must stay clash-free, only
  free-license Elasticsearch features, telemetry conventions, and no secrets.

1. Install the Gitar GitHub App on this repository (from gitar.ai).
2. Open a pull request that breaks a rule, for example an LLM call without a fallback, or a planner change
   that allows overlaps. Gitar reviews it against `.gitar/rules`, suggests fixes, and diagnoses the failing CI.

## Architecture

```
 Browser ──► FastAPI (app/main.py)
               │ 1. LLM: profile ──► search query + level filter      (app/llm.py)
               │ 2. Elasticsearch: BM25 query  ┐                       (app/search.py)
               │                  kNN query    ┴► RRF fusion ──► ranked talks
               │ 3. Planner: greedy clash-free agenda + backups        (app/planner.py)
               │ 4. LLM: summary + per-talk reasons + tips
               │ 5. Elasticsearch kNN over attendees ──► LLM openers
               ▼
           JSON ──► agenda UI, swap/remove, .ics download

 Chat ──► /api/chat (app/chat.py)
               1. intent: answer | add | replace | remove + query/days/levels   (LLM, or rules as fallback)
               2. hybrid search + clash checker edit the agenda
               3. LLM writes the reply and the reasons for new talks
```

- **Embeddings:** [fastembed](https://github.com/qdrant/fastembed) with `BAAI/bge-small-en-v1.5` runs locally
  (ONNX on CPU, 384 dims, no API key). You can switch to OpenAI embeddings with `EMBEDDINGS=openai`.
- **RRF in Python:** fusion happens in the app, so this works on the **free Basic license** of any Elasticsearch 8.x.
- **Data:** `data/talks.json` has 165 talks over 3 days in 8 rooms. `data/attendees.json` has 60 attendees.
  Both were generated by `data/generate_data.py`, and you can swap in a real schedule with the same fields.

## Run it (one command)

You need **Docker Desktop**, installed and open: https://www.docker.com/products/docker-desktop/

```bash
git clone https://github.com/vuppalasaiganesh/Elastic-_Search.git
```

```bash
cd Elastic-_Search
```

```bash
./start.sh
```

On a Mac you can also just double-click **`Start ConfPilot.command`**.

The script:
1. checks that Docker is installed and running, and opens Docker Desktop on a Mac if it isn't;
2. asks once for your Grok API key and saves it in `.env`, which is git-ignored and stays on your computer. Press Enter to skip;
3. builds the app and starts Elasticsearch, loads the talks, then starts the web app;
4. opens http://localhost:8000 when everything is ready.

The first run downloads about 1–2 GB and takes 5–10 minutes. Later runs take seconds.

| Command | What it does |
|---|---|
| `./start.sh` | Start, or restart after changes |
| `./start.sh stop` | Stop everything |
| `./start.sh logs` | Follow the app logs |
| `./start.sh reset` | Delete all data and start fresh |
| `./start.sh tracing` | Start with OpenTelemetry tracing. Jaeger UI at http://localhost:16686 |

**Troubleshooting**
- *"permission denied: ./start.sh"*: run `chmod +x start.sh` once.
- *Elasticsearch keeps restarting*: give Docker Desktop at least 4 GB of memory (Settings → Resources).
- *Port 8000 or 9200 already in use*: stop the other program, or change the left-hand port in `docker-compose.yml`.
- *Changed your API key*: edit `.env`, then run `./start.sh` again.

## Run it locally (for development)

```bash
docker run -d --name es -p 9200:9200 -e discovery.type=single-node \
  -e xpack.security.enabled=false -e ES_JAVA_OPTS="-Xms1g -Xmx1g" elasticsearch:8.15.3
```

```bash
python -m venv .venv && source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env
```

```bash
python -m scripts.ingest
```

```bash
uvicorn app.main:app --reload
```

Tests: `pip install pytest && pytest -q`

## Run on Kubernetes (kind / minikube)

```bash
docker build -t confpilot:latest .
```

```bash
kind load docker-image confpilot:latest
```

```bash
kubectl apply -f k8s/confpilot.yaml
```

```bash
kubectl -n confpilot create secret generic confpilot-llm --from-literal=LLM_API_KEY=your-key
```

```bash
kubectl -n confpilot port-forward svc/confpilot 8000:80
```

The manifest has an Elasticsearch StatefulSet, an ingest Job, the app Deployment (2 replicas) and its Services.
The LLM secret is optional.

## Configuration (`.env`)

| Variable | Default | Notes |
|---|---|---|
| `LLM_API_KEY` | empty | Empty means rule-based mode |
| `LLM_BASE_URL` | `https://api.x.ai/v1` | Grok. Use `https://api.openai.com/v1` for OpenAI |
| `LLM_MODEL` | `grok-4` | Use any chat model your provider offers |
| `ES_URL` | `http://localhost:9200` | |
| `EMBEDDINGS` | `fastembed` | `fastembed`, `openai` or `hash` (offline fallback, low quality) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset | When set, FastAPI and Elasticsearch calls are traced with OpenTelemetry |

## API

- `POST /api/plan` with `{"profile": "...", "days": ["2027-03-23"], "levels": [], "max_talks": 10}` returns the agenda, reasons, tips and people
- `POST /api/search` with `{"query": "ebpf security", "size": 10}` returns the raw hybrid search results (each shows `matched_by`)
- `POST /api/chat` with `{"message": "swap day 2 for AI talks", "profile": "...", "agenda_ids": [...], "history": []}` returns the reply, the new `agenda_ids`, the `added` talks and the `suggestions`
- `POST /api/agenda.ics` with `{"talk_ids": ["T001", "T014"]}` returns a calendar file
- `GET /api/facets` lists days, tracks, levels and the active embedder
- `GET /healthz` reports Elasticsearch and LLM status

## Use a real conference schedule

Put the schedule in a spreadsheet with these columns and save it as CSV. `data/talks_template.csv` is an example.

`title, abstract, speakers, track, level, tags, room, start, end`

Separate several speakers or tags with `;`, and write times like `2027-03-23 10:00`. Only title, abstract,
start and end are required.

```bash
python3 scripts/import_csv.py my_schedule.csv
```

```bash
./start.sh
```

## Tracing and reliability

- `./start.sh tracing` sends OpenTelemetry traces to Jaeger. Open http://localhost:16686, pick service
  `confpilot`, and each request shows its steps: AI understanding → hybrid search (with the Elasticsearch calls
  inside) → planning → AI explanation → people matching.
- Every response includes step timings, and the page shows them under the summary.
- `GET /healthz?deep=true` checks Elasticsearch and makes a tiny real call to the AI to verify your key. The
  page shows the result: *AI on*, *AI off*, or *AI key problem: …*.
- If the AI fails mid-demo (bad key, rate limit, timeout), the request still works with rule-based answers,
  and the page says why in a yellow notice. AI calls time out after 20 seconds with one retry.
- If Elasticsearch is down or still loading, the page says so in plain words instead of failing silently.

## 3-minute demo script

Before the demo: run `./start.sh`, check that the status line says **embeddings: fastembed** and **AI on**,
and run every step below once.

1. **The problem (20 s).** "KubeCon has hundreds of talks at the same time. Picking is painful."
2. **Plan (40 s).** Click the *ML engineer* example, then **Plan my conference**. Point out the agenda grouped
   by day with no clashes, the reason under each talk, and the timing line (search takes milliseconds).
3. **The wow (40 s).** Click **✨ Meaning-only demo: "How can we save money and help the planet?"**, then
   **Plan my conference**. None of those words appear in any talk, yet the agenda is FinOps, autoscaling and
   carbon-footprint talks. Point at the "Searched for" line: the AI turned the question into keywords, and
   meaning search used the original sentence. The **Keyword #** / **Meaning #** badges show both searches
   agreeing. (With AI off, some talks also get the purple **Found by meaning only** badge.)
4. **Chat (40 s).** Type *"swap anything on day 2 for AI talks"*. Talks marked **New** appear. Then ask
   *"who is speaking about service mesh?"* and click **Add**.
5. **Wrap up (40 s).** Click **Swap for backup** on a talk, scroll to **People worth meeting**, then click
   **Add to calendar**. If you started with `./start.sh tracing`, show one trace in Jaeger.
