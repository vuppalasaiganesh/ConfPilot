"""LLM layer (Grok by default, any OpenAI-compatible API works).

Every function has a rule-based fallback, so the app still works with no API key
or when the LLM call fails during a live demo.
"""
import json
import logging
import re

from . import config

log = logging.getLogger(__name__)
_client = None


def enabled():
    return bool(config.LLM_API_KEY)


def _chat_json(system, user, max_tokens=1500):
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL, timeout=45)
    resp = _client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.3,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    text = resp.choices[0].message.content or "{}"
    match = re.search(r"\{.*\}", text, re.S)  # tolerate code fences or preamble
    return json.loads(match.group(0) if match else text)


def _brief(t):
    return {"id": t["id"], "title": t["title"], "level": t["level"], "track": t["track"],
            "when": f"{t['start'][:16]}-{t['end'][11:16]}", "abstract": t["abstract"][:300]}


# ---------- 1. Understand the request ----------

def understand(profile):
    """Profile text -> {"search_query", "levels"}."""
    fallback = {"search_query": _keywords(profile), "levels": _levels_from_text(profile)}
    if not enabled():
        return fallback
    try:
        out = _chat_json(
            "You turn a conference attendee's description into a search request. Reply with JSON: "
            '{"search_query": "<keywords and short phrases, max 25 words, include synonyms>", '
            '"levels": [subset of "Beginner","Intermediate","Advanced"; empty list if not implied]}',
            profile, max_tokens=200)
        levels = [lv for lv in out.get("levels", []) if lv in ("Beginner", "Intermediate", "Advanced")]
        return {"search_query": out.get("search_query") or profile, "levels": levels}
    except Exception as exc:
        log.warning("LLM understand failed: %s", exc)
        return fallback


_FILLER = set("""a an and the i im i'm me my we our to of for in on at with about into is am are be please want
need talks talk session sessions something some stuff learn learning interested interest curious new
beginner beginners intermediate advanced expert level levels fairly very really also more get getting
like would love looking any good best""".split())


def _keywords(text):
    words = re.findall(r"[A-Za-z0-9+#.'-]+", text)
    kept = [w.strip(".'") for w in words if w.lower().strip(".'") not in _FILLER]
    return " ".join(kept) or text


def _levels_from_text(text):
    t = text.lower()
    if re.search(r"\b(beginner|new to|newbie|getting (into|started)|intro|first time|junior|student)\b", t):
        return ["Beginner", "Intermediate"]
    if re.search(r"\b(advanced|expert|deep dive|senior|internals)\b", t):
        return ["Intermediate", "Advanced"]
    return []


# ---------- 2. Explain the agenda ----------

def explain_agenda(profile, agenda):
    """Return {"summary": str, "reasons": {talk_id: str}, "tips": [str]}."""
    if not agenda:
        return {"summary": "No matching talks found. Try a broader description.", "reasons": {}, "tips": []}
    if enabled():
        try:
            out = _chat_json(
                "You are ConfPilot, a friendly cloud-native conference guide. Given an attendee profile and the "
                "talks already chosen for their clash-free agenda, write JSON: "
                '{"summary": "<2-3 sentences: the theme of this agenda and how it fits the attendee>", '
                '"reasons": {"<talk id>": "<one sentence, why THIS person should attend, concrete>"}, '
                '"tips": ["<up to 3 short practical tips, e.g. which talk to prioritise or what to ask>"]} '
                "Only use the talk ids given. Never invent talks.",
                json.dumps({"attendee": profile, "agenda": [_brief(t) for t in agenda]}))
            ids = {t["id"] for t in agenda}
            reasons = {k: v for k, v in (out.get("reasons") or {}).items() if k in ids}
            fb = _fallback_reasons(profile, agenda)
            return {"summary": out.get("summary", ""), "reasons": {**fb, **reasons},
                    "tips": list(out.get("tips") or [])[:3]}
        except Exception as exc:
            log.warning("LLM explain failed: %s", exc)
    return {
        "summary": f"{len(agenda)} talks with no time clashes, ranked by hybrid keyword + semantic match "
                   f"to your interests. Add an LLM API key for personalised explanations.",
        "reasons": _fallback_reasons(profile, agenda),
        "tips": [],
    }


def _fallback_reasons(profile, agenda):
    words = set(re.findall(r"[a-z0-9]+", profile.lower()))
    out = {}
    for t in agenda:
        hits = [tag for tag in t["tags"] if set(re.findall(r"[a-z0-9]+", tag.lower())) & words]
        why = f"Matches your interest in {', '.join(hits)}" if hits else f"Semantically close to what you described ({t['track']})"
        out[t["id"]] = f"{why}; {t['level'].lower()} level."
    return out


# ---------- 3. Hallway matchmaker ----------

def icebreakers(profile, people):
    """Return {person_id: one-line conversation starter}."""
    fallback = {p["id"]: f"Ask {p['name'].split()[0]} how their work on {p['interests'][0]} is going "
                         f"and share what you're exploring." for p in people}
    if not enabled() or not people:
        return fallback
    try:
        out = _chat_json(
            "You help conference attendees network. For each person, write one friendly, specific "
            "conversation opener connecting the attendee's interests with that person's work. "
            'Reply JSON: {"<person id>": "<opener>"}',
            json.dumps({"attendee": profile,
                        "people": [{k: p[k] for k in ("id", "name", "role", "working_on")} for p in people]}),
            max_tokens=600)
        return {**fallback, **{k: v for k, v in out.items() if k in fallback}}
    except Exception as exc:
        log.warning("LLM icebreakers failed: %s", exc)
        return fallback
