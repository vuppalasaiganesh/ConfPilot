# ConfPilot demo guide

Judges review this project from a link, so this guide has two parts:

- **Part A: for judges.** A 2-minute path through the evidence, nothing to install.
- **Part B: for us.** The script for recording the demo video, plus the screenshots to take.

---

## Part A: for judges (2 minutes, nothing to install)

| Step | Look at | What it shows |
|---|---|---|
| 1 | **Demo video:** _link added after recording_ | The whole project working across all four tracks, in about 4 minutes |
| 2 | [README → What ConfPilot does](README.md#what-confpilot-does) | The problem and the product |
| 3 | [Pull request #3](https://github.com/vuppalasaiganesh/ConfPilot/pull/3) | **Gitar** blocking a pull request that breaks our rules, diagnosing the failing CI, and fixing it |
| 4 | [CI runs](https://github.com/vuppalasaiganesh/ConfPilot/actions) | Lint, 34 unit tests, and an integration test against a real Elasticsearch on every push |
| 5 | [Screenshots](#screenshots) | Dash0 traces and metrics, Radar diagnosing an incident, the app |
| 6 | [SUBMISSION.md](SUBMISSION.md) | How it's built and how each track is used |

**Want to run it?** Install Docker Desktop, then:
```bash
git clone https://github.com/vuppalasaiganesh/ConfPilot.git && cd ConfPilot && ./start.sh
```
It works with no API keys: answers are rule-based without an AI key. Add a free Gemini key to `.env` for AI
answers. Full steps are in the [README quick start](README.md#quick-start-10-minutes).

---

## Part B: recording the demo video (about 4 minutes)

### Before you record (10 minutes)

- [ ] `scripts/validate.sh` shows **0 failed**
- [ ] `python3 scripts/load.py` has been running for at least 5 minutes, so Dash0 has history
- [ ] Every fault is off: `scripts/chaos.sh off` and `scripts/k8s.sh fix`
- [ ] Browser tabs, in this order: the app (http://localhost:8000), Dash0, Radar (`kubectl radar`), pull request #3
- [ ] Close other tabs and notifications; zoom the browser to 110–125% so text is readable
- [ ] Never show `.env`; it contains your keys

**How to record on a Mac:** press **Cmd+Shift+5**, choose **Record Selected Portion** or **Record Entire Screen**,
turn on the microphone under **Options**, and click **Record**. Stop from the menu bar. Upload to YouTube
(Unlisted), Loom or Google Drive (anyone with the link can view), then paste the link into Part A and
`SUBMISSION.md`.

### The script

Times are a guide. Say the lines in your own words.

**0:00–0:20 · The problem** (app tab, empty page)
> "Conferences like KubeCon have hundreds of talks at the same time. Picking is painful. You miss the good ones,
> double-book yourself, and never meet the right people. This is ConfPilot."

**0:20–1:00 · The product** (app tab)
1. Click the **ML engineer** example, then **Plan my conference**.
2. Scroll the agenda slowly. Point at the day headings, a **Why** box, and a **Swap for backup** link.
> "One sentence in. A clash-free agenda out, with a reason for every talk written by AI, and a backup for every slot."
3. In the chat, click **"Swap anything on day 2 for AI talks"**. Point at the **New** badges.
> "And you refine it in plain English. It still never double-books."

**1:00–1:40 · Track 4: Elasticsearch** (app tab)
1. Click **✨ Meaning-only demo**, then **Plan my conference**.
> "'How can we save money and help the planet?' None of those words appear in any talk, yet every result is FinOps,
> autoscaling or carbon footprint."
2. Point at the **Keyword #** and **Meaning #** badges and the "Searched for" line.
> "That's Elasticsearch hybrid search: AI keywords go to BM25, your own sentence goes to vector search, and the two
> rankings are fused. The people matching is vector search too."

**1:40–2:30 · Track 2: Dash0** (Terminal, then Dash0 tab)
1. In Terminal: `scripts/chaos.sh slow`
> "Let's break it. Every search now takes three extra seconds."
2. Click **Plan my conference** once in the app so there's a slow request.
3. In Dash0, open a recent trace for service **confpilot**. Point at `hybrid_search` → `embed_query`.
> "Every request is a trace in Dash0, with metrics and logs linked. The time is all in the embedding step."
4. Ask Dash0's AI agent: *"Why are confpilot requests slow?"* Show its answer.
5. In Terminal: `scripts/chaos.sh off`

**2:30–3:20 · Track 3: Kubernetes + Radar** (Terminal, then Radar tab)
1. In Terminal: `scripts/k8s.sh break oom`
> "The same app runs on Kubernetes. Now a bad deploy cuts its memory limit."
2. Wait about 20 seconds. In Radar, show the confpilot pods restarting with **OOMKilled**, and the change in the timeline.
3. Use Radar's AI SRE (or ask a coding agent through Radar's MCP server): *"Why are the confpilot pods crashing?"*
> "Radar shows what broke, why, and what changed: the memory limit."
4. In Terminal: `scripts/k8s.sh fix`

**3:20–4:00 · Track 1: Gitar** (pull request #3 tab)
1. Scroll Gitar's summary: **Blocked**, four findings, three of our rules failed.
> "Here's a pull request that looks harmless, but quietly breaks our rules. Gitar blocked it: an AI call with no
> fallback, a metric that would explode our storage, and a planner change that lets clashes through. It even found a
> bug we didn't plant."
2. Point at the CI diagnosis, then at Gitar's fix commit and the green check.
> "It diagnosed the failing build and fixed it."

**4:00–4:15 · Close**
> "One project, four tracks, all on free tiers. Search is the product, Dash0 and Radar run it, and Gitar protects it."

---

## Screenshots

Take these while recording or right after. Paste them into the chat with Claude (or save them in
`docs/screenshots/` with these names) and they get linked here and in the README.

| File name | What to capture |
|---|---|
| `app-agenda.png` | An agenda with Why boxes and Keyword/Meaning badges |
| `app-meaning-demo.png` | The ✨ meaning demo results, including the "Searched for" line |
| `app-chat.png` | The chat after "swap day 2 for AI talks", with New badges |
| `dash0-trace.png` | A confpilot trace showing the `hybrid_search` / `embed_query` spans |
| `dash0-agent.png` | Dash0's AI agent explaining the slow requests |
| `radar-oom.png` | Radar showing OOMKilled pods and the change that caused it |
| `gitar-review.png` | Gitar's Blocked review on pull request #3 |
| `validate.png` | `scripts/validate.sh` showing 24 passed, 0 failed |
