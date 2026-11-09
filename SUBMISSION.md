# ConfPilot: hackathon submission

Copy each section into the matching field of the submission form.

---

## Project name
ConfPilot

## Tagline (one line)
Turn a 300-talk conference schedule into your personal, clash-free plan in seconds. Just describe yourself.

## Links
- **Code:** https://github.com/vuppalasaiganesh/ConfPilot
- **Gitar live demo (do not merge):** https://github.com/vuppalasaiganesh/ConfPilot/pull/3
- **Completed Gitar review:** https://github.com/vuppalasaiganesh/ConfPilot/pull/2
- **CI runs:** https://github.com/vuppalasaiganesh/ConfPilot/actions

## Tracks entered
1. AI Code Review (Gitar)
2. Observability (Dash0)
3. Kubernetes UI / AI SRE (Radar)
4. Search & Vector Database (Elasticsearch)

---

## Short description (about 50 words)

ConfPilot is an AI conference planner. Describe yourself in one sentence and it builds a clash-free agenda,
explains every pick, finds people worth meeting, and lets you refine it by chat. It's powered by Elasticsearch
hybrid search, observed end to end in Dash0, runs on Kubernetes with Radar, and is guarded by Gitar code review.

---

## The problem

Big cloud-native conferences have hundreds of talks, many at the same time in different rooms. Attendees spend
hours reading schedules, still miss the talks that matter to them, double-book themselves, and leave without
meeting the right people.

## What it does

You type one sentence, such as *"SRE at a bank, getting serious about OpenTelemetry, curious about eBPF."*
In a few seconds ConfPilot returns:

- **A personal agenda** with the best talk for you in each time slot, and never two at once.
- **A reason for every talk**, written by AI for your profile.
- **A backup talk per slot**, one click to swap.
- **A chat to refine it:** "swap anything on day 2 for AI talks", "add a beginner GPU talk", "who's speaking
  about service mesh?". Every change goes through the same search and clash check.
- **People worth meeting**, with an AI-written conversation opener.
- **One-click calendar export.**

If the AI provider is down, slow or out of quota, ConfPilot keeps working with rule-based answers and says why.

## How we built it

- **Elasticsearch 8** holds talks and attendees with 384-dimension embeddings from **fastembed**
  (bge-small, running locally on CPU, no API cost).
- **Hybrid search:** the AI turns the request into keywords for BM25, the person's own sentence goes to vector
  (kNN) search, and the two rankings are fused with Reciprocal Rank Fusion. This runs on Elasticsearch's free license.
- A **planner** picks the best talk per time slot with no overlaps, and keeps the runner-up as a backup.
- **AI** through any OpenAI-compatible API. We use Google Gemini's free tier, with a backup model for when the
  main one is busy, automatic switching when a model is retired, and rule-based fallbacks for everything.
- **OpenTelemetry** traces, metrics and logs go to **Dash0**.
- **Docker Compose** for one-command local runs, a **Kubernetes** manifest and script for clusters, and
  **GitHub Actions** CI with **Gitar** review rules.
- Python, FastAPI, and a plain HTML/JS front end. 34 unit tests, plus an integration test against a real Elasticsearch.

---

## Track 4: Search & Vector Database (Elasticsearch)

Elasticsearch is the core of every request, not an add-on:
- **Hybrid search** (BM25 + kNN + Reciprocal Rank Fusion) ranks talks for each profile.
- **Vector search over attendees** powers the "people worth meeting" matchmaker.
- Each talk card shows its **Keyword** rank and **Meaning** rank, so you can see how the two searches combine.
- **Try it:** ask *"How can we save money and help the planet?"*. None of those words appear in any talk, yet
  the agenda is all FinOps, autoscaling and carbon-footprint talks.

## Track 2: Observability (Dash0)

- Every request is a full trace in Dash0: AI understanding → hybrid search (with query embedding and the
  Elasticsearch calls inside) → planning → AI explanation, with people matching running in parallel.
- Custom metrics: search latency and result counts, AI calls by model and outcome (ok, busy, retired,
  rejected), AI latency, and fallbacks. Logs are linked to traces.
- **Built-in incidents for Dash0's AI agent to diagnose:** a slow embedding step, an AI-provider outage, and a
  corrupt data record that crashes 40% of requests. Each leaves a different trail across traces, metrics and logs.

## Track 3: Kubernetes UI / AI SRE (Radar)

- One command (`scripts/k8s.sh up`) deploys Elasticsearch, a data-loading job and two app replicas, with
  readiness checks that fail when Elasticsearch is unreachable, memory limits, and pod identity on all telemetry.
- **Six scripted incidents for Radar's AI SRE:** OOM-killed pods, Elasticsearch down, a bad config change, a
  missing image tag, an AI outage, and corrupt data. Radar shows what broke, why, and what changed;
  `scripts/k8s.sh fix` restores everything.

## Track 1: AI Code Review (Gitar)

- **CI on every pull request:** lint, unit tests, config validation, and an integration job that starts a real
  Elasticsearch, loads the data, and fails if the agenda ever contains a clash.
- **Five project-specific Gitar rules:** every AI call needs a fallback, the agenda must stay clash-free, only
  free-license Elasticsearch features, telemetry conventions (low-cardinality metric labels), and no secrets.
- **Demo pull request** looks like a normal feature but breaks three rules and fails CI. Gitar blocked it with
  four findings (one we didn't plant: a missing 404), quoted our own rule files, pinpointed the CI failure, and
  offered one-click fixes.

---

## Challenges we ran into

- **Free AI tiers move fast.** Models were retired or overloaded mid-build, so the app now follows the
  provider's suggested replacement, falls back to a backup model, and degrades to rules instead of failing.
- **Hybrid search tuning.** Sending AI keywords to BM25 and the original sentence to vector search gave each
  engine the input it handles best.
- **Local Kubernetes images.** Docker Desktop's newer Kubernetes keeps images per node, so the deploy script
  loads the image into each node automatically.
- **Live-demo safety.** Every external dependency has a fallback, and a single `validate.sh` checks all four
  tracks before going on stage.

## Accomplishments we're proud of

- One project that fits all four tracks naturally: search is the product, observability and Kubernetes run it,
  and code review protects it.
- Everything runs on **free tiers**, starts with one command, and checks itself with one command.
- It never double-books, which is enforced by unit tests, an integration test, and a Gitar rule.

## What we learned

Hybrid search beats either search alone, and a good fallback design matters as much as the AI itself.
OpenTelemetry plus a few deliberate failure modes makes observability tooling easy to demonstrate.

## What's next

- Load real conference schedules (a CSV importer is already built) and run it for a live event.
- Personal "hallway track" matching with opt-in attendee profiles.
- Room-capacity awareness, so backups kick in automatically when a talk fills up.

---

## Elevator pitch (30 seconds, out loud)

> "KubeCon has hundreds of talks at the same time, and picking is painful. With ConfPilot you describe yourself
> in one sentence, and in seconds you get a clash-free agenda with a reason for every talk and people worth
> meeting. Then you just chat to change it. Elasticsearch hybrid search finds talks by meaning, not just keywords.
> Dash0 sees every request, Radar watches it on Kubernetes, and Gitar reviews every change against our rules.
> One project, four tracks, all on free tiers."
