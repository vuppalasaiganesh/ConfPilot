import logging
import time
from pathlib import Path

from elastic_transport import TransportError
from elasticsearch import ApiError, NotFoundError
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import chat, config, llm, planner, search, telemetry
from .telemetry import step

logging.basicConfig(level=logging.INFO)
STATIC = Path(__file__).parent / "static"
VERSION = "2026.11.09-7"  # bump on each release; shown by /healthz so you can tell which code is running

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
           "tracing": TRACING}
    if deep:
        out["llm"] = llm.check()
    return out


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
    llm.start_request()
    timings, start = {}, time.perf_counter()
    with step("understand", timings, llm=llm.enabled()):
        intent = llm.understand(req.profile)
    levels = req.levels or intent["levels"]
    with step("hybrid_search", timings):
        ranked = search.hybrid_search_talks(intent["search_query"], size=60, levels=levels, days=req.days)
    with step("plan", timings):
        agenda = planner.build_agenda(ranked, max_talks=req.max_talks)
    with step("explain", timings, llm=llm.enabled()):
        explanation = llm.explain_agenda(req.profile, agenda)
    with step("people", timings):
        people = search.similar_people(req.profile, size=4)
        openers = llm.icebreakers(req.profile, people)
    timings["total"] = round((time.perf_counter() - start) * 1000)
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


@app.post("/api/chat")
def chat_turn(req: ChatRequest):
    llm.start_request()
    start = time.perf_counter()
    history = [{"role": h.role, "content": h.content} for h in req.history]
    out = chat.handle(req.message, req.profile, req.agenda_ids, history)
    out["timings"]["total"] = round((time.perf_counter() - start) * 1000)
    return {**out, "ai": _ai_status()}


@app.post("/api/agenda.ics")
def agenda_ics(req: IcsRequest):
    talks = sorted(search.get_talks(req.talk_ids), key=lambda t: t["start"])
    return Response(planner.to_ics(talks), media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="confpilot-agenda.ics"'})


app.mount("/static", StaticFiles(directory=STATIC), name="static")
