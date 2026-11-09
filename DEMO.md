# ConfPilot demo guide

- **Part A: for judges.** A 2-minute path through the evidence, nothing to install.
- **Part B: run every demo yourself.** Step-by-step, with what you should see at each step.

---

## Part A: for judges (2 minutes, nothing to install)

| Step | Look at | What it shows |
|---|---|---|
| 1 | [README → What ConfPilot does](README.md#what-confpilot-does) | The problem and the product |
| 2 | **[TRACKS.md](TRACKS.md)** | How each tool is used, why, where in the code, with diagrams |
| 3 | [Pull request #3](https://github.com/vuppalasaiganesh/ConfPilot/pull/3) | **Gitar** blocking a pull request that breaks our rules, diagnosing the failing CI, and fixing it |
| 4 | [CI runs](https://github.com/vuppalasaiganesh/ConfPilot/actions) | Lint, 34 unit tests, and an integration test against a real Elasticsearch on every push |
| 5 | [`scripts/validate.sh`](scripts/validate.sh) | The one command that checks all four tracks end to end |
| 6 | [SUBMISSION.md](SUBMISSION.md) | How it's built and how each track is used |

**Want to run it?** Install Docker Desktop, then:
```bash
git clone https://github.com/vuppalasaiganesh/ConfPilot.git && cd ConfPilot && ./start.sh
```
It works with no API keys: answers are rule-based without an AI key. Add a free Gemini key to `.env` for AI
answers. Full steps are in the [README quick start](README.md#quick-start-10-minutes).

---

## Part B: run every demo yourself (about 15 minutes)

### Before you start

- [ ] Follow the [README quick start](README.md#quick-start-10-minutes), then run `scripts/validate.sh` and check it shows **0 failed**
- [ ] For Dash0: add your Dash0 endpoint and token to `.env` (see [TRACKS.md](TRACKS.md#2-dash0-observability-track-2)) and run `python3 scripts/load.py` for a few minutes
- [ ] For Radar: `scripts/k8s.sh up`, then `kubectl radar`
- [ ] Every fault is off: `scripts/chaos.sh off` and `scripts/k8s.sh fix`

### The walkthrough

**1. The product** (app at http://localhost:8000)

| Do | You should see |
|---|---|
| Click the **ML engineer** example, then **Plan my conference** | Loading steps tick through, then an agenda grouped by day with no two talks at the same time |
| Look at any talk card | A **Why** box written by AI, **Keyword #** / **Meaning #** badges, a score, and **Swap for backup** |
| In the chat, click **"Swap anything on day 2 for AI talks"** | Day 2 now has AI talks marked **New**, still with no clashes |
| Scroll to **People worth meeting** | Four attendees, each with a conversation opener |
| Click **Add to calendar (.ics)** | A calendar file with the whole agenda |

**2. Track 4: Elasticsearch** (app)

| Do | You should see |
|---|---|
| Click **✨ Meaning-only demo**, then **Plan my conference** | FinOps, autoscaling and carbon-footprint talks, although no talk contains "save", "money" or "planet" |
| Read the "Searched for" line | The keywords the AI produced for BM25; the original sentence went to vector search |

**3. Track 2: Dash0** (Terminal, then Dash0)

| Do | You should see |
|---|---|
| `scripts/chaos.sh slow`, then plan once in the app | The plan takes about 3 seconds longer |
| In Dash0, open a recent trace for service **confpilot** | The `hybrid_search` → `embed_query` span holds the extra time; a "Slow request" log is linked |
| Ask Dash0's AI agent *"Why are confpilot requests slow?"* | It points at the embedding step |
| `scripts/chaos.sh ai`, then plan once | A yellow notice in the app; in Dash0, `confpilot.ai.fallbacks` rises and AI calls show `busy` |
| `scripts/chaos.sh off` | Back to normal |

**4. Track 3: Kubernetes + Radar** (Terminal, then Radar)

| Do | You should see |
|---|---|
| `scripts/k8s.sh break oom` and wait about 20 seconds | In Radar, new confpilot pods **OOMKilled** and restarting, the rollout stalled, old pods still serving, and the memory-limit change in the timeline |
| Ask Radar's AI SRE (or a coding agent via Radar's MCP server) *"Why are the confpilot pods crashing?"* | It names the memory limit change |
| `scripts/k8s.sh fix` | All pods healthy again |

**5. Track 1: Gitar** ([pull request #3](https://github.com/vuppalasaiganesh/ConfPilot/pull/3))

| Look at | You should see |
|---|---|
| Gitar's summary comment | **Blocked**, 4 findings, 3 of our 5 rules failed, and a diagnosis of the failing CI |
| The inline comments | Each finding on the exact lines, with a suggested fix |
| The commits and checks | Gitar's fix commit, then every check green |
