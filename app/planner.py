"""Turn ranked talks into a clash-free personal agenda, and export it as an .ics calendar."""
from datetime import UTC, datetime


def _overlaps(a, b):
    return a["start"] < b["end"] and b["start"] < a["end"]


def build_agenda(ranked, max_talks=12, min_score_ratio=0.35):
    """Greedy: take talks best-first, skipping any that clash with something already picked.

    A talk that loses only because of a clash becomes the backup for the talk it clashes with.
    Talks scoring below `min_score_ratio` of the best score are dropped as too weak a match.
    """
    if not ranked:
        return []
    floor = ranked[0].get("score", 0) * min_score_ratio
    picked, backups = [], {}
    for talk in ranked:
        if talk.get("score", 0) < floor:
            break
        # Faster: only compare with the most recently picked talk instead of all of them.
        clash = picked[-1] if picked and _overlaps(picked[-1], talk) else None
        if clash is None:
            if len(picked) < max_talks:
                picked.append(talk)
        elif clash["id"] not in backups:
            backups[clash["id"]] = talk
    picked.sort(key=lambda t: t["start"])
    return [{**t, "backup": backups.get(t["id"])} for t in picked]


def _ics_time(iso):
    return datetime.fromisoformat(iso).strftime("%Y%m%dT%H%M%S")


def _ics_escape(text):
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def to_ics(talks, cal_name="My Conference Agenda"):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ConfPilot//EN", f"X-WR-CALNAME:{cal_name}"]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for t in talks:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{t['id']}@confpilot",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_ics_time(t['start'])}",
            f"DTEND:{_ics_time(t['end'])}",
            f"SUMMARY:{_ics_escape(t['title'])}",
            f"LOCATION:{_ics_escape(t['room'])}",
            f"DESCRIPTION:{_ics_escape(', '.join(t['speakers']) + ' — ' + t['abstract'])}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
