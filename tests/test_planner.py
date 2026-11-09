from app.planner import build_agenda, to_ics
from app.search import rrf


def talk(id_, start, end, score):
    return {"id": id_, "title": f"Talk {id_}", "start": start, "end": end, "score": score, "room": "R1",
            "speakers": ["A"], "abstract": "x"}


def test_agenda_has_no_clashes_and_keeps_backup():
    ranked = [
        talk("a", "2027-03-23T10:00:00", "2027-03-23T10:35:00", 1.0),
        talk("b", "2027-03-23T10:00:00", "2027-03-23T10:35:00", 0.9),  # clashes with a
        talk("c", "2027-03-23T11:00:00", "2027-03-23T11:35:00", 0.8),
        talk("d", "2027-03-23T10:20:00", "2027-03-23T10:55:00", 0.7),  # partial overlap with a
    ]
    agenda = build_agenda(ranked)
    assert [t["id"] for t in agenda] == ["a", "c"]
    assert agenda[0]["backup"]["id"] == "b"
    assert agenda[1]["backup"] is None


def test_weak_matches_and_max_talks():
    ranked = [talk(str(i), f"2027-03-23T{10 + i:02d}:00:00", f"2027-03-23T{10 + i:02d}:30:00", 1 - i * 0.2)
              for i in range(5)]
    assert len(build_agenda(ranked, max_talks=2)) == 2
    assert [t["id"] for t in build_agenda(ranked, min_score_ratio=0.5)] == ["0", "1", "2"]


def test_rrf_rewards_docs_found_by_both():
    hit = lambda i: {"_id": i, "_source": {"id": i}}
    fused = rrf(("keyword", [hit("x"), hit("y")]), ("semantic", [hit("y"), hit("z")]))
    assert fused[0]["id"] == "y"
    assert fused[0]["matched_by"] == ["keyword#2", "semantic#1"]


def test_ics_export():
    ics = to_ics([talk("a", "2027-03-23T10:00:00", "2027-03-23T10:35:00", 1)])
    assert "DTSTART:20270323T100000" in ics and ics.count("BEGIN:VEVENT") == 1
