import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import chat, config, llm, planner, search

logging.basicConfig(level=logging.INFO)
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="ConfPilot", description="AI conference planner on Elasticsearch hybrid search")

if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
    try:
        from opentelemetry.instrumentation.elasticsearch import ElasticsearchInstrumentor
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        ElasticsearchInstrumentor().instrument()
        FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        logging.warning("OpenTelemetry packages not installed; tracing disabled")


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


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/healthz")
def healthz():
    try:
        ok = search.es_client().ping()
    except Exception:
        ok = False
    return {"elasticsearch": ok, "llm": llm.enabled(), "llm_model": config.LLM_MODEL if llm.enabled() else None}


@app.get("/api/facets")
def get_facets():
    try:
        return {**search.facets(), "llm": llm.enabled()}
    except Exception as exc:
        raise HTTPException(503, f"Elasticsearch not ready or not ingested: {exc}")


@app.post("/api/search")
def do_search(req: SearchRequest):
    return {"results": search.hybrid_search_talks(req.query, size=req.size, levels=req.levels,
                                                  days=req.days, tracks=req.tracks)}


@app.post("/api/plan")
def plan(req: PlanRequest):
    intent = llm.understand(req.profile)
    levels = req.levels or intent["levels"]
    ranked = search.hybrid_search_talks(intent["search_query"], size=60, levels=levels, days=req.days)
    agenda = planner.build_agenda(ranked, max_talks=req.max_talks)
    explanation = llm.explain_agenda(req.profile, agenda)
    people = search.similar_people(req.profile, size=4)
    openers = llm.icebreakers(req.profile, people)
    return {
        "understood": {"search_query": intent["search_query"], "levels": levels, "days": req.days},
        "summary": explanation["summary"],
        "tips": explanation["tips"],
        "agenda": [{**t, "reason": explanation["reasons"].get(t["id"], "")} for t in agenda],
        "people": [{**p, "opener": openers.get(p["id"], "")} for p in people],
        "llm": llm.enabled(),
    }


@app.post("/api/chat")
def chat_turn(req: ChatRequest):
    history = [{"role": h.role, "content": h.content} for h in req.history]
    return chat.handle(req.message, req.profile, req.agenda_ids, history)


@app.post("/api/agenda.ics")
def agenda_ics(req: IcsRequest):
    talks = sorted(search.get_talks(req.talk_ids), key=lambda t: t["start"])
    return Response(planner.to_ics(talks), media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="confpilot-agenda.ics"'})


app.mount("/static", StaticFiles(directory=STATIC), name="static")
