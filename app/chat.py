"""Follow-up chat: answer questions about the conference and edit the agenda.

Flow per message:
  1. Work out the intent (LLM, or rules as fallback):
     mode = answer | add | replace | remove, plus search_query, days, levels, remove_ids.
  2. Apply it with Elasticsearch hybrid search and the clash checker.
  3. Write the reply (LLM, or a template as fallback).

Examples it handles:
  "swap anything on day 2 for AI talks"      -> replace, days=[day 2], query "AI"
  "add a beginner GPU talk"                  -> add, levels=[Beginner], query "GPU"
  "drop the policy talks"                    -> remove (talks matching "policy")
  "who is speaking about service mesh?"      -> answer, list matches with Add buttons
"""
import json
import logging
import re
from datetime import datetime

from . import llm, search
from .planner import _overlaps
from .telemetry import step

log = logging.getLogger(__name__)
MODES = ("answer", "add", "replace", "remove")
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# ---------- 1. intent ----------

def _intent_llm(message, history, agenda, days):
    out = llm._chat_json(
        "You are the intent parser for ConfPilot, a conference agenda assistant. The user has an agenda and sends "
        "a follow-up message. Reply with JSON only:\n"
        '{"mode": "answer" | "add" | "replace" | "remove",\n'
        ' "search_query": "<keywords to search talks, with synonyms; empty if not needed>",\n'
        ' "days": ["YYYY-MM-DD" ...]  (only from the conference days given; empty = any day),\n'
        ' "levels": [subset of "Beginner","Intermediate","Advanced"],\n'
        ' "remove_ids": ["<agenda talk ids to drop>"],\n'
        ' "count": <how many talks to add or replace, default 3>}\n'
        "mode meanings: answer = a question, do not change the agenda; add = add talks into free slots; "
        "replace = swap existing agenda talks (on the given days) for better matches; remove = only drop talks.",
        json.dumps({
            "conference_days": days,
            "agenda": [{"id": t["id"], "title": t["title"], "when": t["start"][:16], "track": t["track"]} for t in agenda],
            "recent_chat": history[-6:],
            "message": message,
        }), max_tokens=300)
    agenda_ids = {t["id"] for t in agenda}
    return {
        "mode": out.get("mode") if out.get("mode") in MODES else "answer",
        "search_query": (out.get("search_query") or "").strip(),
        "days": [d for d in out.get("days") or [] if d in days],
        "levels": [lv for lv in out.get("levels") or [] if lv in ("Beginner", "Intermediate", "Advanced")],
        "remove_ids": [i for i in out.get("remove_ids") or [] if i in agenda_ids],
        "count": max(1, min(int(out.get("count") or 3), 8)),
    }


def _days_from_text(text, days):
    t = text.lower()
    picked = set()
    for m in re.finditer(r"\bday\s*(\d)\b", t):
        n = int(m.group(1))
        if 1 <= n <= len(days):
            picked.add(days[n - 1])
    for d in days:
        wd = WEEKDAYS[datetime.fromisoformat(d).weekday()]
        if wd in t or wd[:3] + " " in t:
            picked.add(d)
    if "tomorrow" in t and len(days) > 1:
        picked.add(days[1])
    return sorted(picked)


_CHAT_FILLER = set("""swap replace instead change remove drop delete add include more another find show any anything
everything all talks talk session sessions on day days for with from the a an my me i to of in please can you could
some something what which who is are there about speaking speaker give monday tuesday wednesday thursday friday
saturday sunday tomorrow ones one""".split())


def _intent_rules(message, agenda, days):
    t = message.lower()
    if re.search(r"\b(swap|replace|instead|change)\b", t):
        mode = "replace"
    elif re.search(r"\b(remove|drop|delete|cancel|skip)\b", t):
        mode = "remove"
    elif re.search(r"\b(add|include|more|another)\b", t):
        mode = "add"
    else:
        mode = "answer"
    words = [w for w in re.findall(r"[a-z0-9+#.-]+", t) if w not in _CHAT_FILLER and not re.fullmatch(r"\d", w)]
    query = llm._keywords(" ".join(words))
    sel_days = _days_from_text(message, days)
    remove_ids = []
    if mode == "remove" and (query or sel_days):
        terms = set(query.lower().split())
        for talk in agenda:
            hay = set(re.findall(r"[a-z0-9+#.-]+", f"{talk['title']} {talk['track']} {' '.join(talk['tags'])}".lower()))
            on_day = not sel_days or talk["start"][:10] in sel_days
            if on_day and (not terms or terms & hay):
                remove_ids.append(talk["id"])
    return {"mode": mode, "search_query": query, "days": sel_days,
            "levels": llm._levels_from_text(message), "remove_ids": remove_ids, "count": 3}


def understand(message, history, agenda, days):
    if llm.enabled():
        try:
            return _intent_llm(message, history, agenda, days)
        except Exception as exc:
            llm._note_failure("chat intent", exc)
    return _intent_rules(message, agenda, days)


# ---------- 2. apply ----------

def apply(intent, agenda):
    agenda = [t for t in agenda if t["id"] not in set(intent["remove_ids"])]
    removed = list(intent["remove_ids"])
    added, suggestions = [], []
    q = intent["search_query"]
    if not q or intent["mode"] == "remove":
        return agenda, added, removed, suggestions

    original_ids = {t["id"] for t in agenda}
    if intent["mode"] == "replace" and intent["days"]:
        # Clear the requested days first, so the best matches can take any slot on them.
        # Cleared talks stay eligible, so a talk that already fits well is kept.
        cleared = [t for t in agenda if t["start"][:10] in intent["days"]]
        agenda = [t for t in agenda if t["start"][:10] not in intent["days"]]
        removed += [t["id"] for t in cleared]
        count = max(intent["count"], len(cleared))
    else:
        count = intent["count"]

    ranked = search.hybrid_search_talks(q, size=30, levels=intent["levels"], days=intent["days"])
    in_agenda = {t["id"] for t in agenda}
    candidates = [t for t in ranked if t["id"] not in in_agenda]

    if intent["mode"] == "answer":
        return agenda, added, removed, candidates[:5]

    for cand in candidates:
        if len(added) >= count:
            break
        clashes = [t for t in agenda if _overlaps(t, cand)]
        if any(c in added for c in clashes):
            continue  # never displace a better match picked earlier in this same turn
        if clashes and intent["mode"] == "replace":
            agenda = [t for t in agenda if t not in clashes]
            removed += [t["id"] for t in clashes]
            clashes = []
        if not clashes:
            agenda.append(cand)
            added.append(cand)
    # A talk that was removed and then re-added is neither.
    added_ids = {t["id"] for t in added}
    removed = [i for i in dict.fromkeys(removed) if i not in added_ids]
    added = [t for t in added if t["id"] not in original_ids]
    agenda.sort(key=lambda t: t["start"])
    return agenda, added, removed, suggestions


# ---------- 3. reply ----------

def _when(t):
    d = datetime.fromisoformat(t["start"])
    return f"{d.strftime('%a')} {t['start'][11:16]}, {t['room']}"


def _reply_rules(intent, added, removed_talks, suggestions):
    lines = []
    if added:
        lines.append("Added: " + "; ".join(f"{t['title']} ({_when(t)})" for t in added) + ".")
    if removed_talks:
        lines.append("Removed: " + "; ".join(t["title"] for t in removed_talks) + ".")
    if suggestions:
        lines.append("Here are the best matches. Tap Add to put one in your agenda.")
    if not lines and intent["mode"] in ("add", "replace") and intent["search_query"]:
        lines.append("Your agenda already has the best matches for that, or there's no free slot for them. Nothing changed.")
    if not lines:
        lines.append("I couldn't find anything to change for that. Try naming a topic, for example "
                     "\"add a beginner GPU talk\" or \"swap day 2 for AI talks\".")
    return " ".join(lines)


def reply(message, profile, intent, agenda, added, removed_talks, suggestions):
    fallback_reasons = llm._fallback_reasons(f"{profile} {message}", added)
    if llm.enabled():
        try:
            out = llm._chat_json(
                "You are ConfPilot, a friendly cloud-native conference guide. Write a short reply (max 4 sentences) "
                "to the user's follow-up message, based ONLY on the facts given: talks added, removed, or suggested. "
                "Never invent talks. Reply JSON: "
                '{"reply": "<text>", "reasons": {"<added talk id>": "<one sentence why it fits this person>"}}',
                json.dumps({
                    "attendee": profile, "message": message, "mode": intent["mode"],
                    "added": [llm._brief(t) for t in added],
                    "removed": [t["title"] for t in removed_talks],
                    "suggestions": [llm._brief(t) for t in suggestions],
                    "agenda_size": len(agenda),
                }), max_tokens=500)
            ids = {t["id"] for t in added}
            reasons = {k: v for k, v in (out.get("reasons") or {}).items() if k in ids}
            text = out.get("reply") or _reply_rules(intent, added, removed_talks, suggestions)
            return text, {**fallback_reasons, **reasons}
        except Exception as exc:
            llm._note_failure("chat reply", exc)
    return _reply_rules(intent, added, removed_talks, suggestions), fallback_reasons


HELP = ("I can change your agenda or answer questions about talks. Try: \"swap anything on day 2 for AI talks\", "
        "\"add a beginner GPU talk\", \"drop the policy talks\" or \"who is speaking about service mesh?\"")
_SMALL_TALK = re.compile(r"^(hi+|hello|hey|yo|thanks?|thank you|thx|ok(ay)?|cool|great|nice|awesome|perfect|"
                         r"good|got it|help|what can you do)\b[\s!.?]*$", re.I)


def small_talk(message):
    """Canned reply for greetings, thanks, help and messages with no content. None otherwise."""
    m = message.strip()
    if not re.search(r"[a-z0-9]", m, re.I):
        return HELP
    if _SMALL_TALK.match(m):
        if re.match(r"^(thanks?|thank you|thx)", m, re.I):
            return "You're welcome! Ask me anything else about the talks, or tell me what to change."
        return HELP
    return None


def handle(message, profile, agenda_ids, history):
    timings = {}
    base = {"intent": None, "agenda_ids": list(agenda_ids), "added": [], "removed_ids": [],
            "suggestions": [], "changed": False, "timings": timings}
    canned = small_talk(message)
    if canned:
        return {**base, "reply": canned}

    with step("load_agenda", timings):
        agenda = sorted(search.get_talks(agenda_ids), key=lambda t: t["start"]) if agenda_ids else []
        days = search.facets()["days"]
    with step("understand", timings, llm=llm.enabled()):
        intent = understand(message, history, agenda, days)
    # Vague edits like "add more" or "replace day 2" with no topic: use the attendee's profile as the topic.
    if intent["mode"] in ("add", "replace") and not intent["search_query"] and profile:
        intent["search_query"] = llm._keywords(profile)
    before = {t["id"]: t for t in agenda}
    with step("search_and_edit", timings):
        new_agenda, added, removed, suggestions = apply(intent, agenda)
    removed_talks = [before[i] for i in removed if i in before]
    with step("reply", timings, llm=llm.enabled()):
        text, reasons = reply(message, profile, intent, new_agenda, added, removed_talks, suggestions)
    return {
        **base,
        "reply": text,
        "intent": intent,
        "agenda_ids": [t["id"] for t in new_agenda],
        "added": [{**t, "reason": reasons.get(t["id"], ""), "backup": None} for t in added],
        "removed_ids": [t["id"] for t in removed_talks],
        "suggestions": suggestions,
        "changed": bool(added or removed_talks),
    }
