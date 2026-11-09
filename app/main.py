import contextvars
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from elastic_transport import TransportError
from elasticsearch import ApiError, NotFoundError
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import chaos, chat, config, llm, planner, search, telemetry
from .telemetry import step

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("confpilot")
SLOW_REQUEST_MS = 3000
STATIC = Path(__file__).parent / "static"
VERSION = telemetry.VERSION  # shown by /healthz so you can tell which code is running

app = FastAPI(title="ConfPilot", description="AI conference planner on Elasticsearch hybrid search")
TRACING = telemetry.setup(app)


# ---------- clear errors instead of a bare 500 ----------

@app.exception_handler(NotFoundError)
def es_missing_index(request: Request, exc: NotFoundError):
    return JSONResponse(status_code=503, content={
        "detail": "The talk data isn't loaded yet. Wait a minute, or run ./start.sh again."})


@app.exception_handler(TransportError)
@app.exception_handler(ApiError)
def es_down(request: Request, exc: Exception):
    logging.warning("Elasticsearch error: %s", exc)
    return JSONResponse(status_code=503, content={
        "detail": "Search is unavailable: Elasticsearch is not reachable. Check Docker, then run ./start.sh."})


def _ai_status():
    """What the UI should say about the AI for this request."""
    if not llm.enabled():
        return {"used": False, "notice": None}
    reason = llm.fallback_reason()
    if reason:
        return {"used": False, "notice": f"AI answers are off for this request because {reason}. "
                                          "Showing rule-based results instead."}
    return {"used": True, "notice": None}


# ---------- models ----------

@app.exception_handler(Exception)
def unexpected_error(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={
        "detail": f"Something broke on the server ({type(exc).__name__}). Run ./start.sh logs to see why."})


def _log_if_slow(route, timings):
    if timings.get("total", 0) > SLOW_REQUEST_MS:
        log.warning("Slow request %s took %d ms: %s", route, timings["total"], timings)


class ChaosRequest(BaseModel):
    slow_search_ms: float | None = Field(None, ge=0, le=30000)
    llm_outage: bool | None = None
    bad_data_rate: float | None = Field(None, ge=0, le=1)
    reset: bool = False


class PlanRequest(BaseModel):
    profile: str = Field(..., min_length=3, max_length=2000)
    days: list[str] = []
    levels: list[str] = []
    max_talks: int = Field(10, ge=1, le=30)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    days: list[str] = []
    levels: list[str] = []
    tracks: list[str] = []
    size: int = Field(10, ge=1, le=50)


class ChatTurn(BaseModel):
    role: str
    content: str = Field(..., max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    profile: str = Field("", max_length=2000)
    agenda_ids: list[str] = Field([], max_length=50)
    history: list[ChatTurn] = Field([], max_length=20)


class IcsRequest(BaseModel):
    talk_ids: list[str] = Field(..., min_length=1, max_length=50)


# ---------- routes ----------

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/healthz")
def healthz(deep: bool = False):
    """deep=true also makes a tiny real LLM call to verify the key (cached 5 minutes)."""
    start = time.perf_counter()
    try:
        es_ok = search.es_client().ping()
    except Exception:
        es_ok = False
    out = {"version": VERSION, "elasticsearch": es_ok, "es_ms": round((time.perf_counter() - start) * 1000),
           "llm": {"configured": llm.enabled(), "model": config.LLM_MODEL if llm.enabled() else None},
           "tracing": TRACING, "telemetry": telemetry.DESTINATION,
           "chaos": {"runtime_toggle": chaos.ENABLED, **chaos.state}}
    if deep:
        out["llm"] = llm.check()
    return out


@app.get("/readyz")
def readyz():
    """Kubernetes readiness: only take traffic when Elasticsearch answers and the data is loaded."""
    try:
        es = search.es_client()
        if es.ping() and es.indices.exists(index=config.ES_INDEX_TALKS):
            return {"ready": True}
        reason = "talk index missing" if es.ping() else "Elasticsearch unreachable"
    except Exception as exc:
        reason = f"Elasticsearch error: {exc}"
    log.warning("Not ready: %s (ES_URL=%s)", reason, config.ES_URL)
    return JSONResponse(status_code=503, content={"ready": False, "reason": reason})


@app.get("/api/facets")
def get_facets():
    return {**search.facets(), "llm": llm.enabled(), "tracing": TRACING}


@app.post("/api/search")
def do_search(req: SearchRequest):
    timings = {}
    with step("hybrid_search", timings):
        results = search.hybrid_search_talks(req.query, size=req.size, levels=req.levels,
                                             days=req.days, tracks=req.tracks)
    return {"results": results, "timings": timings}


@app.post("/api/plan")
def plan(req: PlanRequest):
    """Understand -> hybrid search -> clash-free plan -> explain, with people matching in parallel.

    People matching only needs the profile, so it (and its AI openers) runs in a background thread while
    the main path waits on the AI. That hides one AI call and cuts the response time.
    """
    llm.start_request()
    timings, start = {}, time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as pool:
        people_job = pool.submit(contextvars.copy_context().run, _people_with_openers, req.profile, timings)
        with step("understand", timings, llm=llm.enabled()):
            intent = llm.understand(req.profile)
        levels = req.levels or intent["levels"]
        with step("hybrid_search", timings):
            ranked = search.hybrid_search_talks(intent["search_query"], size=60, levels=levels, days=req.days,
                                                semantic_query=req.profile)
        with step("plan", timings):
            agenda = planner.build_agenda(ranked, max_talks=req.max_talks)
        with step("explain", timings, llm=llm.enabled()):
            explanation = llm.explain_agenda(req.profile, agenda)
        people, openers = people_job.result()
    timings["total"] = round((time.perf_counter() - start) * 1000)
    _log_if_slow("/api/plan", timings)
    log.info("Planned agenda: %d talks from %d candidates in %d ms (ai=%s)",
             len(agenda), len(ranked), timings["total"], _ai_status()["used"])
    return {
        "understood": {"search_query": intent["search_query"], "levels": levels, "days": req.days},
        "summary": explanation["summary"],
        "tips": explanation["tips"],
        "agenda": [{**t, "reason": explanation["reasons"].get(t["id"], "")} for t in agenda],
        "people": [{**p, "opener": openers.get(p["id"], "")} for p in people],
        "candidates": len(ranked),
        "ai": _ai_status(),
        "timings": timings,
    }


def _people_with_openers(profile, timings):
    with step("people", timings):
        people = search.similar_people(profile, size=4)
        return people, llm.icebreakers(profile, people)


@app.post("/api/chat")
def chat_turn(req: ChatRequest):
    llm.start_request()
    start = time.perf_counter()
    history = [{"role": h.role, "content": h.content} for h in req.history]
    out = chat.handle(req.message, req.profile, req.agenda_ids, history)
    out["timings"]["total"] = round((time.perf_counter() - start) * 1000)
    _log_if_slow("/api/chat", out["timings"])
    return {**out, "ai": _ai_status()}


@app.get("/api/talks/{talk_id}/summary")
def talk_summary(talk_id: str):
    started = time.perf_counter()
    talk = search.get_talks([talk_id])[0]
    summary = llm.summarize_talk(talk)
    telemetry.record_summary(talk_id, time.perf_counter() - started)
    return {"id": talk_id, "summary": summary}


@app.get("/api/chaos")
def get_chaos():
    return {"runtime_toggle": chaos.ENABLED, **chaos.state}


@app.post("/api/chaos")
def set_chaos(req: ChaosRequest):
    if not chaos.ENABLED:
        return JSONResponse(status_code=403, content={"detail": "Fault injection is off. Set CHAOS_ENABLED=true in .env."})
    if req.reset:
        return chaos.reset()
    return chaos.update(slow_search_ms=req.slow_search_ms, llm_outage=req.llm_outage, bad_data_rate=req.bad_data_rate)


@app.post("/api/agenda.ics")
def agenda_ics(req: IcsRequest):
    talks = sorted(search.get_talks(req.talk_ids), key=lambda t: t["start"])
    return Response(planner.to_ics(talks), media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="confpilot-agenda.ics"'})


app.mount("/static", StaticFiles(directory=STATIC), name="static")
