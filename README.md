# ConfPilot

**Your personal conference planner.** Describe yourself in one sentence and get a clash-free agenda,
a reason for every talk, and the people worth meeting, then refine it by chatting.

[![CI](https://github.com/vuppalasaiganesh/ConfPilot/actions/workflows/ci.yml/badge.svg)](https://github.com/vuppalasaiganesh/ConfPilot/actions/workflows/ci.yml)

**Built by Sai Ganesh Vuppala** for the **Cloud Native Hackathon**, entered in all four tracks:
**Elasticsearch** · **Dash0** · **Radar** · **Gitar**. The submission text is in [SUBMISSION.md](SUBMISSION.md).

---

## For judges

**Start here:** 📘 **[TRACKS.md: how we use Elasticsearch, Dash0, Radar and Gitar](TRACKS.md)**. It explains each
tool's job, why we chose it, where it is in the code, and how to check it, with diagrams. No setup needed.

- 📊 **Slides:** [view in browser (PDF)](docs/ConfPilot_Project_Overview.pdf) · [download PowerPoint](docs/ConfPilot_Project_Overview.pptx)
- 🤖 **Gitar review:** [pull request #3](https://github.com/vuppalasaiganesh/ConfPilot/pull/3), blocked with 4 findings, then fixed by Gitar
- 🧭 **Two-minute path:** [DEMO.md](DEMO.md#part-a-for-judges-2-minutes-nothing-to-install)
- ✅ **CI:** [GitHub Actions](https://github.com/vuppalasaiganesh/ConfPilot/actions)
- 📄 **Submission write-up:** [SUBMISSION.md](SUBMISSION.md)

---

## Contents

1. [The problem](#the-problem)
2. [What ConfPilot does](#what-confpilot-does)
3. [Hackathon tracks at a glance](#hackathon-tracks-at-a-glance)
4. [Quick start (10 minutes)](#quick-start-10-minutes)
5. [How it works](#how-it-works)
6. [Track details and how to demo each one](#track-details-and-how-to-demo-each-one)
7. [The demo script](#the-demo-script)
8. [Commands cheat sheet](#commands-cheat-sheet)
9. [Configuration (.env)](#configuration-env)
10. [Troubleshooting](#troubleshooting)
11. [Project structure](#project-structure)
12. [API](#api)
13. [Use a real conference schedule](#use-a-real-conference-schedule)

---

## The problem

Conferences like KubeCon have hundreds of talks, many running at the same time in different rooms.
People spend hours reading the schedule, still miss the talks that matter to them, double-book themselves,
and leave without meeting the right people.

## What ConfPilot does

You type one sentence, for example *"SRE at a bank, getting serious about OpenTelemetry, curious about eBPF."*
In a few seconds you get:

| | |
|---|---|
| 🗓️ **A personal schedule** | The best talks for you, grouped by day, with **no time clashes** |
| 💡 **A reason for each talk** | Written by AI, so you know why it's worth your time |
| 🔁 **A backup per slot** | One click to swap if a room is full |
| 💬 **A chat to change things** | *"Swap anything on day 2 for AI talks"*, *"Who's speaking about GPUs?"* |
| 🤝 **People to meet** | Attendees working on similar things, with a conversation opener |
| 📅 **Calendar export** | One click to add the whole agenda to your calendar |

It keeps working if the AI is down: answers fall back to simple rules and the page says why.

---

## Hackathon tracks at a glance

| Track | What we built | Show the judges |
|---|---|---|
| **4. Search & Vector DB (Elasticsearch)** | Hybrid search (keywords + meaning) is the core of every request; people matching is vector search | The ✨ meaning demo and the Keyword/Meaning badges |
| **2. Observability (Dash0)** | Traces, metrics and logs sent to Dash0; switches that break the app on purpose | Break the app, then ask Dash0's AI agent what went wrong |
| **3. Kubernetes UI / AI SRE (Radar)** | One command deploys to Kubernetes; six scripted incidents | Break the cluster, then let Radar find the root cause |
| **1. AI Code Review (Gitar)** | CI with a real Elasticsearch, plus five project-specific review rules | [Pull request #3](https://github.com/vuppalasaiganesh/ConfPilot/pull/3), where Gitar catches three rule violations and a failing build |

---

## Quick start (10 minutes)

**You need:** a Mac, Windows or Linux computer with **Docker Desktop** installed and open
([download](https://www.docker.com/products/docker-desktop/)). Give Docker at least 4 GB of memory
(Settings → Resources).

**1. Get the code**
```bash
git clone https://github.com/vuppalasaiganesh/ConfPilot.git
```
```bash
cd ConfPilot
```

**2. Add a free AI key (optional, 2 minutes)**

Get a free Google Gemini key at https://aistudio.google.com/apikey, then:
```bash
cp .env.example .env
```
Open `.env` and paste your key after `LLM_API_KEY=`. Without a key the app still works, with simpler answers.

**3. Start everything**
```bash
./start.sh
```
The first run downloads about 1–2 GB and takes 5–10 minutes. Your browser opens **http://localhost:8000** when
it's ready. On a Mac you can also double-click **`Start ConfPilot.command`**.

**4. Check everything**
```bash
scripts/validate.sh
```
This prints PASS / WARN / FAIL for every part of every track and tells you how to fix anything that isn't green.

---

## How it works

```
                        ┌───────────────────────── ConfPilot (FastAPI) ─────────────────────────┐
 "SRE into eBPF..." ──► │ 1. AI understands the request ──► keywords + level                    │
                        │ 2. Elasticsearch hybrid search                                        │
                        │      keywords ──► BM25 search  ─┐                                     │
                        │      your words ─► vector search ┴─► Reciprocal Rank Fusion ─► ranked │
                        │ 3. Planner picks the best talk per time slot (never two at once)      │
                        │ 4. AI writes a reason for each talk          ┐ in parallel:           │
                        │ 5. Vector search over attendees + AI openers ┘ people to meet         │
                        └───────────────┬───────────────────────────────────────────────────────┘
                                        │ traces, metrics, logs (OpenTelemetry)
                                        ▼
                                      Dash0
```

- **Elasticsearch 8** stores 165 talks and 60 attendees with 384-dimension embeddings.
- **Embeddings** come from [fastembed](https://github.com/qdrant/fastembed) (`BAAI/bge-small-en-v1.5`), which runs
  locally on the CPU. No API key and no cost.
- **Hybrid search:** keyword search gets the AI's keywords, and meaning search gets your original sentence, so
  each search gets the input it's best at. Results are combined with Reciprocal Rank Fusion in Python, which
  works on Elasticsearch's **free license**.
- **AI:** any OpenAI-compatible API, such as Google Gemini (free), Groq (free), xAI Grok or OpenAI. If the main
  model is busy, a **backup model** answers. If a model is retired, the app follows the provider's suggested
  replacement. If every AI call fails, the app falls back to rules.
- **Chat:** the AI works out what you want (answer, add, replace or remove), and every change goes through the
  same search and clash check.

---

## Track details and how to demo each one

### Track 4: Search & Vector Database (Elasticsearch)

**What's built**
- Every request runs **hybrid search**: BM25 keyword search plus kNN vector search, fused with Reciprocal Rank Fusion.
- **People matching** is kNN search over a second index of attendees' "what I'm working on" notes.
- Each talk card shows **Keyword #** and **Meaning #** badges with its rank in each search, plus the fused score.

**Demo**
1. Click an example profile, then **Plan my conference**.
2. Click **✨ Meaning-only demo: "How can we save money and help the planet?"**, then **Plan my conference**.
   None of those words appear in any talk, yet the agenda is FinOps, autoscaling and carbon-footprint talks.
3. Point at the badges and the "Searched for" line, which shows the keywords the AI produced while meaning
   search used the original sentence.

### Track 2: Observability (Dash0)

**What's built**
- The app sends **traces, metrics and logs** to Dash0 over OpenTelemetry (OTLP gRPC).
- Every request is a trace: `understand` → `hybrid_search` (with `embed_query` and the Elasticsearch calls
  inside) → `plan` → `explain`, plus `people` in parallel.
- **Custom metrics:** `confpilot.search.duration`, `confpilot.search.results`, `confpilot.llm.calls` (by model and
  outcome: ok / busy / retired / rejected), `confpilot.llm.duration`, `confpilot.ai.fallbacks`.
- **Logs** are linked to their traces. Slow requests and crashes are logged with the step timings or the stack trace.
- **Fault injection** (`scripts/chaos.sh`) creates realistic incidents, each leaving a different trail.

**Setup**
1. Create a Dash0 account (free trial).
2. In Dash0, open **Settings → Endpoints** and copy the **OTLP via gRPC** address. Then open
   **Settings → Auth Tokens** and copy a token.
3. Add them to `.env`, then run `./start.sh`:
   ```
   DASH0_OTLP_ENDPOINT=https://ingress.us-east-1.aws.dash0.com:4317
   DASH0_AUTH_TOKEN=auth_your-token
   CHAOS_ENABLED=true
   ```

**Demo**
1. Send traffic: `python3 scripts/load.py --minutes 5`
2. Break something, then ask **Dash0's AI agent** what's wrong:

   | Command | What breaks | What Dash0 shows |
   |---|---|---|
   | `scripts/chaos.sh slow` | Searches take 3 extra seconds | The `embed_query` span is the slow part; "Slow request" warnings |
   | `scripts/chaos.sh ai` | The AI provider times out | `confpilot.ai.fallbacks` jumps; LLM calls marked "busy"; error logs |
   | `scripts/chaos.sh baddata` | 40% of plans fail with HTTP 500 | KeyError stack traces pointing at a talk record with no start time |
   | `scripts/chaos.sh off` | Back to normal | |

### Track 3: Kubernetes UI / AI SRE (Radar)

**What's built**
- `scripts/k8s.sh up` builds the image, loads it into the cluster, creates a Secret from your `.env`, deploys
  Elasticsearch, loads the data and starts two app pods.
- Proper health checks: `/readyz` fails when Elasticsearch is unreachable, so Kubernetes stops sending traffic.
  Memory limits are set, and each pod's name is attached to its telemetry.
- `scripts/k8s.sh break …` creates six realistic incidents for [Radar](https://github.com/skyhook-io/radar)'s
  AI SRE to diagnose.

**Setup**
1. Docker Desktop: **Settings → Kubernetes → Enable Kubernetes → Apply**, then wait for "running".
2. Deploy: `scripts/k8s.sh up`
3. Open the app: `scripts/k8s.sh open` → http://localhost:8080
4. Install and start Radar: `brew install kubectl-radar`, then `kubectl radar`

**Demo:** break the cluster, then let Radar, or a coding agent through Radar's MCP server, find the root cause.

| Command | What happens |
|---|---|
| `scripts/k8s.sh break oom` | Memory limit cut; new pods are OOMKilled and the rollout stalls |
| `scripts/k8s.sh break es-down` | Elasticsearch scaled to 0; app pods go NotReady |
| `scripts/k8s.sh break bad-config` | A "config change" points the app at a host that doesn't exist |
| `scripts/k8s.sh break bad-image` | A deploy references an image tag that doesn't exist; new pods can't start |
| `scripts/k8s.sh break ai-outage` | AI provider times out; the app degrades but stays up |
| `scripts/k8s.sh break bad-data` | A corrupt record crashes 40% of plan requests |
| `scripts/k8s.sh fix` | Undo everything |

With Dash0 configured, the same incidents also appear in Dash0, tagged with the pod name.

### Track 1: AI Code Review (Gitar)

**What's built**
- **CI** ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs on every push and pull request:
  - lint (ruff), 34 unit tests and config validation;
  - an **integration job** that starts a real Elasticsearch, loads the data, calls the API, and fails if the
    agenda contains a clash.
- **Five review rules** in [.gitar/rules/](.gitar/rules/), specific to this project:

  | Rule | What Gitar checks |
  |---|---|
  | `ai-calls-need-fallback` | Every AI call has a rule-based fallback; AI output is validated |
  | `agenda-stays-clash-free` | Code that edits the agenda checks for overlaps and has a test |
  | `elasticsearch-basic-license` | Only free-license Elasticsearch features |
  | `telemetry-conventions` | New steps are traced; metric labels stay low-cardinality; no secrets in logs |
  | `no-secrets` | No API keys or tokens committed |

**Demo:** [Pull request #3](https://github.com/vuppalasaiganesh/ConfPilot/pull/3) looks like a normal feature
(AI talk summaries plus a planner speed-up) but breaks three rules: an AI call with no fallback, a metric
labelled with talk IDs, and a planner change that lets clashes through, which also makes CI fail. Show Gitar's
review comments next to the rules, and its diagnosis of the failing build.

A completed Gitar review (Blocked, 4 findings, 3 of 5 rules failed, CI diagnosis) is also visible on
[pull request #2](https://github.com/vuppalasaiganesh/ConfPilot/pull/2).

**Protect `main`:** Settings → Branches → add a rule for `main` with *Require status checks to pass before
merging* (`lint-and-test`, `integration`). GitHub then blocks merging any pull request with failing checks.

> ⚠️ **Never merge the demo pull request.** It contains deliberate bugs. If it gets merged by accident, revert
> it on `main` (GitHub's **Revert** button on the merged pull request) and open a new one from the same changes.

---

## The demo script

**Before you present (10 minutes early)**
- [ ] `./start.sh` and `scripts/k8s.sh up` are running
- [ ] `scripts/validate.sh` shows **0 failed**
- [ ] `python3 scripts/load.py` is sending traffic, so Dash0 has live data
- [ ] Browser tabs open: the app, Dash0, Radar (`kubectl radar`), pull request #3
- [ ] Every fault is off: `scripts/chaos.sh off` and `scripts/k8s.sh fix`

**5 minutes, all four tracks**

| Time | What to do | What to say |
|---|---|---|
| 0:00 | Show the empty page | "KubeCon has hundreds of talks at once. Picking is painful." |
| 0:20 | Example profile → **Plan my conference** | "One sentence in, a clash-free agenda out, with a reason for every talk." |
| 1:00 | ✨ meaning demo | "No shared words, yet every talk fits. Elasticsearch hybrid search: keywords plus meaning." *(Track 4)* |
| 1:40 | Chat: *"swap anything on day 2 for AI talks"* | "Refine it in plain English. It still never double-books." |
| 2:10 | `scripts/chaos.sh slow` → ask Dash0's AI agent | "Traces, metrics and logs in Dash0. Its agent finds the slow step." *(Track 2)* |
| 3:00 | `scripts/k8s.sh break oom` → Radar | "Same app on Kubernetes. Radar's AI SRE spots the OOM kills and the change that caused them." *(Track 3)* |
| 3:50 | Pull request #2 | "Gitar reviews pull requests against our own rules and explains the failing build." *(Track 1)* |
| 4:30 | `scripts/chaos.sh off`, `scripts/k8s.sh fix` | "One project, four tracks, all on free tiers." |

**If something fails live:** if the AI is down, the app keeps working with rule-based answers and a yellow
notice. Say "it degrades gracefully, and Dash0 shows why" and carry on.

---

## Commands cheat sheet

Run these from the project folder.

| Command | What it does |
|---|---|
| `./start.sh` | Start or restart everything (Docker), then open the browser |
| `./start.sh stop` | Stop everything |
| `./start.sh logs` | Follow the app logs |
| `./start.sh reset` | Delete all data and start fresh |
| `./start.sh tracing` | Start with a local Jaeger trace viewer at http://localhost:16686 (no Dash0 needed) |
| `scripts/validate.sh` | Check all four tracks: PASS / WARN / FAIL |
| `scripts/load.py` | Send realistic traffic (`--rps 2 --minutes 5`) |
| `scripts/chaos.sh slow\|ai\|baddata\|off\|status` | Break or restore the Docker app |
| `scripts/k8s.sh up\|open\|status\|fix\|down` | Kubernetes deploy and management |
| `scripts/k8s.sh break <incident>` | Kubernetes incidents for Radar (see Track 3) |
| `python3 scripts/import_csv.py file.csv` | Load a real schedule (see below) |

---

## Configuration (.env)

Copy `.env.example` to `.env`. Everything is optional. `.env` is git-ignored, so your keys never leave your computer.

| Setting | Example | What it's for |
|---|---|---|
| `LLM_API_KEY` | `AIza...` | AI key. Empty means rule-based answers |
| `LLM_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` | The AI provider's OpenAI-compatible address |
| `LLM_MODEL` | `gemini-3.5-flash-lite` | Main model |
| `LLM_FALLBACK_MODELS` | `gemini-3.8-flash` | Backups when the main model is busy, comma separated |
| `LLM_TIMEOUT` | `45` | Seconds before an AI call gives up |
| `DASH0_OTLP_ENDPOINT` | `https://ingress.us-east-1.aws.dash0.com:4317` | Dash0 "OTLP via gRPC" address |
| `DASH0_AUTH_TOKEN` | `auth_...` | Dash0 auth token (just the token, no "Bearer") |
| `DASH0_DATASET` | | Optional Dash0 dataset |
| `CHAOS_ENABLED` | `true` | Allow `scripts/chaos.sh` to break things (demos only) |
| `EMBEDDINGS` | `fastembed` | `fastembed` (default), `openai`, or `hash` (offline, low quality) |

**Free AI options**

| Provider | Get a key | `LLM_BASE_URL` | `LLM_MODEL` |
|---|---|---|---|
| Google Gemini | aistudio.google.com/apikey | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-3.5-flash-lite` |
| Groq | console.groq.com | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |

Model names change often. If yours is wrong, the page's status line and `scripts/validate.sh` list the models
your key can use.

---

## Troubleshooting

| What you see | Fix |
|---|---|
| `Docker is not installed` / `Docker Compose is missing` | Install Docker Desktop and **open it once**, then run `./start.sh` again |
| `permission denied: ./start.sh` | `chmod +x start.sh scripts/*.sh` |
| Elasticsearch keeps restarting | Give Docker Desktop at least 4 GB of memory (Settings → Resources) |
| Port 8000 or 9200 already in use | Stop the other program, or change the left-hand port in `docker-compose.yml` |
| Status line: **embeddings: hash** | The embedding model didn't download. Check your internet connection, then `./start.sh` |
| **AI problem: 400/401/403** | Wrong key or wrong provider. Check that `LLM_API_KEY` and `LLM_BASE_URL` are from the same provider |
| **AI problem: 403 … no credits** | That provider needs payment. Use a free one (Gemini or Groq, above) |
| **AI problem: 404 … no longer available** | Set `LLM_MODEL` to the model named in the **Fix:** line |
| **AI problem: 503 / 429 / timed out** | Provider busy. Set a backup in `LLM_FALLBACK_MODELS` |
| Dash0 shows nothing | Use the **OTLP via gRPC** address ending in `:4317`, and put only the token in `DASH0_AUTH_TOKEN`. Then `./start.sh` and `scripts/k8s.sh up` |
| `k8s.sh up`: `ErrImageNeverPull` | Run `scripts/k8s.sh up` again (it copies the image into the cluster). If it persists: Docker Desktop → Settings → General → untick "Use containerd for pulling and storing images" |
| Changed `.env` but nothing changed | Restart: `./start.sh`, and `scripts/k8s.sh up` for Kubernetes |
| Anything else | `scripts/validate.sh` names the problem; `./start.sh logs` shows the details |

---

## Project structure

```
app/
  main.py          API routes, health checks, error handling
  search.py        Elasticsearch: indices, ingest, hybrid search (BM25 + kNN + RRF)
  planner.py       Clash-free agenda builder and .ics calendar export
  chat.py          Follow-up chat: intent → search → agenda edit → reply
  llm.py           AI calls: fallbacks, backup models, retired-model handling, key checks
  embeddings.py    fastembed (default), OpenAI, or offline hash embeddings
  telemetry.py     OpenTelemetry traces, metrics and logs (Dash0 / any OTLP)
  chaos.py         Fault injection for the observability demos
  static/index.html  The web page
data/              165 talks, 60 attendees, generator script, CSV template
scripts/           start helpers: ingest, validate, load, chaos, k8s, CSV import
k8s/confpilot.yaml Kubernetes manifest (Elasticsearch, ingest job, app, services)
.gitar/rules/      Gitar code review rules
.github/workflows/ CI: lint, tests, integration test with real Elasticsearch
tests/             34 unit tests
```

**Tech stack:** Python 3.12, FastAPI, Elasticsearch 8.15, fastembed (ONNX), OpenAI-compatible LLM client,
OpenTelemetry, Docker Compose, Kubernetes, GitHub Actions, vanilla HTML/JS.

---

## API

| Method | Path | What it does |
|---|---|---|
| `POST` | `/api/plan` | `{"profile": "...", "days": [], "levels": [], "max_talks": 10}` → agenda, reasons, people, timings |
| `POST` | `/api/chat` | `{"message": "...", "profile": "...", "agenda_ids": [...]}` → reply, new agenda, suggestions |
| `POST` | `/api/search` | `{"query": "...", "size": 10}` → raw hybrid search results |
| `POST` | `/api/agenda.ics` | `{"talk_ids": [...]}` → calendar file |
| `GET` | `/api/facets` | Days, tracks, levels, active embedder |
| `GET` | `/healthz?deep=true` | Version, Elasticsearch, AI key check, telemetry, fault state |
| `GET` | `/readyz` | 200 only when Elasticsearch is reachable and the data is loaded |
| `GET/POST` | `/api/chaos` | Read or change fault injection (needs `CHAOS_ENABLED=true`) |

---

## Use a real conference schedule

Save the schedule from a spreadsheet as CSV with these columns. See `data/talks_template.csv` for an example.

`title, abstract, speakers, track, level, tags, room, start, end`

Only `title`, `abstract`, `start` and `end` are required. Separate several speakers or tags with `;`, and
write times like `2027-03-23 10:00`.

```bash
python3 scripts/import_csv.py my_schedule.csv
```
```bash
./start.sh
```
