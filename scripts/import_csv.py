"""Import a real conference schedule from a CSV file into data/talks.json.

Usage (from the project folder):
    python3 scripts/import_csv.py my_schedule.csv
then restart with ./start.sh so the new talks are loaded into Elasticsearch.

Required columns: title, abstract, start, end
Optional columns: speakers, track, level, tags, room, id
  - speakers and tags: separate several with ";"
  - start/end: "2027-03-23 10:00" or "2027-03-23T10:00:00"
  - level: Beginner, Intermediate or Advanced (anything else becomes Intermediate)
See data/talks_template.csv for an example. Spreadsheets (Excel, Google Sheets, Sched exports)
can be saved as CSV.
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "talks.json"
LEVELS = {"beginner", "intermediate", "advanced"}
TIME_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S",
                "%m/%d/%Y %H:%M", "%d/%m/%Y %H:%M")


def parse_time(value, row_no, field):
    value = (value or "").strip()
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(value, fmt).isoformat()
        except ValueError:
            pass
    sys.exit(f"Row {row_no}: can't read {field} time {value!r}. Use e.g. 2027-03-23 10:00")


def split(value):
    return [p.strip() for p in (value or "").split(";") if p.strip()]


def convert(rows):
    talks = []
    for n, row in enumerate(rows, start=2):  # row 1 is the header
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        if not row.get("title"):
            continue
        for col in ("abstract", "start", "end"):
            if not row.get(col):
                sys.exit(f"Row {n} ({row['title'][:40]}): missing '{col}'")
        level = row.get("level", "").capitalize()
        track = row.get("track") or "General"
        talk = {
            "id": row.get("id") or f"T{len(talks) + 1:03d}",
            "title": row["title"],
            "abstract": row["abstract"],
            "speakers": split(row.get("speakers")) or ["TBA"],
            "track": track,
            "level": level if level.lower() in LEVELS else "Intermediate",
            "tags": sorted(set(split(row.get("tags"))) | {track}),
            "room": row.get("room") or "TBA",
            "start": parse_time(row["start"], n, "start"),
            "end": parse_time(row["end"], n, "end"),
        }
        if talk["end"] <= talk["start"]:
            sys.exit(f"Row {n} ({talk['title'][:40]}): end is not after start")
        talks.append(talk)
    if not talks:
        sys.exit("No talks found. Check that the first row has the column names.")
    ids = [t["id"] for t in talks]
    if len(ids) != len(set(ids)):
        sys.exit("Duplicate ids in the CSV. Leave the id column empty to number talks automatically.")
    return sorted(talks, key=lambda t: (t["start"], t["room"]))


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    with open(sys.argv[1], newline="", encoding="utf-8-sig") as f:
        talks = convert(csv.DictReader(f))
    OUT.write_text(json.dumps(talks, indent=2))
    print(f"Imported {len(talks)} talks into {OUT}. Now run ./start.sh to load them.")


if __name__ == "__main__":
    main()
