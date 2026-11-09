import csv
import io

import pytest

from app import chat, config, llm
from scripts import import_csv


@pytest.mark.parametrize("msg", ["hi", "Hello!", "thanks", "ok", "???", "  ", "help", "what can you do"])
def test_small_talk_gets_canned_reply(msg):
    assert chat.small_talk(msg)


@pytest.mark.parametrize("msg", ["add a GPU talk", "who is talking about eBPF?", "hi, add a GPU talk"])
def test_real_requests_are_not_small_talk(msg):
    assert chat.small_talk(msg) is None


def test_handle_small_talk_skips_search(monkeypatch):
    monkeypatch.setattr(chat.search, "get_talks", lambda *a: pytest.fail("should not search"))
    out = chat.handle("thanks!", "profile", ["T001"], [])
    assert out["changed"] is False and out["agenda_ids"] == ["T001"] and "welcome" in out["reply"]


def test_vague_add_uses_profile_as_topic(monkeypatch):
    seen = {}
    monkeypatch.setattr(chat.search, "get_talks", lambda ids: [])
    monkeypatch.setattr(chat.search, "facets", lambda: {"days": ["2027-03-23"]})
    monkeypatch.setattr(config, "LLM_API_KEY", "")

    def fake_search(q, **kw):
        seen["q"] = q
        return []
    monkeypatch.setattr(chat.search, "hybrid_search_talks", fake_search)
    chat.handle("add more", "SRE interested in OpenTelemetry", [], [])
    assert "OpenTelemetry" in seen["q"]


@pytest.mark.parametrize("error,expected", [
    ("Error code: 401 - invalid api key", "rejected"),
    ("Error code: 429 - rate limit", "rate limiting"),
    ("Request timed out.", "timed out"),
])
def test_llm_failure_falls_back_and_explains(monkeypatch, error, expected):
    monkeypatch.setattr(config, "LLM_API_KEY", "x")

    def boom(*a, **k):
        raise RuntimeError(error)
    monkeypatch.setattr(llm, "_chat_json", boom)
    llm.start_request()
    out = llm.understand("Beginner, eBPF security please")
    assert out["levels"] == ["Beginner", "Intermediate"] and "eBPF" in out["search_query"]
    assert expected in llm.fallback_reason()


def _rows(text):
    return csv.DictReader(io.StringIO(text))


def test_import_csv_converts_rows():
    talks = import_csv.convert(_rows(
        "title,abstract,speakers,track,level,tags,room,start,end\n"
        'B talk,About B,"A (X); B (Y)",Security,expert,eBPF;Policy,R1,2027-03-23 11:00,2027-03-23 11:30\n'
        "A talk,About A,,,,,,2027-03-23T10:00:00,2027-03-23T10:30:00\n"))
    assert [t["title"] for t in talks] == ["A talk", "B talk"]  # sorted by time
    a, b = talks
    assert a["speakers"] == ["TBA"] and a["track"] == "General" and a["level"] == "Intermediate"
    assert b["speakers"] == ["A (X)", "B (Y)"] and b["level"] == "Intermediate" and "Security" in b["tags"]


def test_import_csv_rejects_bad_times():
    with pytest.raises(SystemExit):
        import_csv.convert(_rows("title,abstract,start,end\nX,Y,tomorrow,later\n"))


def test_suggested_model_from_google_error():
    err = ("404: [{'error': {'code': 404, 'message': 'This model models/gemini-2.5-flash is no longer available to new "
           "users. Please update your code to use models/gemini-3.8-flash for the latest features and improvements.")
    assert llm._suggested_model(err) == "gemini-3.8-flash"
    assert llm._suggested_model("401: Incorrect API key provided") is None


def test_model_list_filters_and_sorts_newest_first(monkeypatch):
    names = ["models/aqa", "models/gemini-2.5-flash", "models/gemini-2.5-flash-preview-tts", "models/gemini-3.8-flash",
             "models/gemini-2.5-flash-image", "models/gemini-3.8-flash-lite", "models/deep-research-preview-04-2026"]

    class M:
        def __init__(self, i):
            self.id = i

    class Client:
        class models:
            @staticmethod
            def list():
                return type("R", (), {"data": [M(n) for n in names]})

    monkeypatch.setattr(llm, "_get_client", lambda: Client)
    assert llm._available_models() == ["gemini-3.8-flash", "gemini-3.8-flash-lite", "gemini-2.5-flash"]
