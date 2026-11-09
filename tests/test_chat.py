from app import chat

DAYS = ["2027-03-23", "2027-03-24", "2027-03-25"]  # Tue, Wed, Thu


def t(id_, day, hh, title="Talk", track="Security", tags=("Policy",)):
    return {"id": id_, "title": title, "track": track, "tags": list(tags), "level": "Beginner", "room": "R1",
            "start": f"{day}T{hh}:00:00", "end": f"{day}T{hh}:35:00", "speakers": ["A"], "abstract": "x"}


def test_rules_parse_replace_with_day():
    i = chat._intent_rules("Swap anything on day 2 for AI talks", [], DAYS)
    assert i["mode"] == "replace" and i["days"] == ["2027-03-24"] and "ai" in i["search_query"].lower()


def test_rules_parse_weekday_and_level():
    i = chat._intent_rules("add a beginner GPU talk on Thursday", [], DAYS)
    assert i["mode"] == "add" and i["days"] == ["2027-03-25"] and "Beginner" in i["levels"]
    assert i["search_query"].lower() == "gpu"


def test_rules_remove_matches_agenda_only():
    agenda = [t("a", DAYS[0], "10", title="The Future of Policy"), t("b", DAYS[0], "11", title="eBPF", tags=("eBPF",))]
    assert chat._intent_rules("drop the policy talks", agenda, DAYS)["remove_ids"] == ["a"]
    assert chat._intent_rules("remove", agenda, DAYS)["remove_ids"] == []  # never wipe everything by accident


def test_rules_question_is_answer():
    assert chat._intent_rules("Who is speaking about service mesh?", [], DAYS)["mode"] == "answer"


def test_apply_replace_day(monkeypatch):
    agenda = [t("a", DAYS[0], "10"), t("b", DAYS[1], "10"), t("c", DAYS[1], "11")]
    found = [{**t("x", DAYS[1], "14", title="AI Agents"), "score": 1}, {**t("y", DAYS[1], "10"), "score": 0.9}]
    monkeypatch.setattr(chat.search, "hybrid_search_talks", lambda *a, **k: found)
    intent = {"mode": "replace", "search_query": "ai", "days": [DAYS[1]], "levels": [], "remove_ids": [], "count": 3}
    new, added, removed, _ = chat.apply(intent, agenda)
    assert [x["id"] for x in new] == ["a", "y", "x"]
    assert sorted(removed) == ["b", "c"] and [x["id"] for x in added] == ["x", "y"]


def test_apply_add_skips_clashes(monkeypatch):
    agenda = [t("a", DAYS[0], "10")]
    found = [{**t("x", DAYS[0], "10"), "score": 1}, {**t("y", DAYS[0], "11"), "score": 0.9}]
    monkeypatch.setattr(chat.search, "hybrid_search_talks", lambda *a, **k: found)
    intent = {"mode": "add", "search_query": "q", "days": [], "levels": [], "remove_ids": [], "count": 3}
    new, added, removed, _ = chat.apply(intent, agenda)
    assert [x["id"] for x in added] == ["y"] and removed == []


def test_apply_replace_day_keeps_good_existing_talk(monkeypatch):
    agenda = [t("b", DAYS[1], "10", title="AI Agents")]
    found = [{**t("b", DAYS[1], "10", title="AI Agents"), "score": 1}, {**t("x", DAYS[1], "14"), "score": 0.9}]
    monkeypatch.setattr(chat.search, "hybrid_search_talks", lambda *a, **k: found)
    intent = {"mode": "replace", "search_query": "ai", "days": [DAYS[1]], "levels": [], "remove_ids": [], "count": 2}
    new, added, removed, _ = chat.apply(intent, agenda)
    assert [x["id"] for x in new] == ["b", "x"] and removed == [] and [x["id"] for x in added] == ["x"]


def test_apply_replace_never_double_books(monkeypatch):
    found = [{**t("x", DAYS[1], "16"), "score": 1}, {**t("y", DAYS[1], "16"), "score": 0.9}]
    monkeypatch.setattr(chat.search, "hybrid_search_talks", lambda *a, **k: found)
    intent = {"mode": "replace", "search_query": "ai", "days": [DAYS[1]], "levels": [], "remove_ids": [], "count": 3}
    new, added, _, _ = chat.apply(intent, [t("a", DAYS[1], "10")])
    assert [x["id"] for x in added] == ["x"]
    assert not any(chat._overlaps(p, q) for i, p in enumerate(new) for q in new[i + 1:])
