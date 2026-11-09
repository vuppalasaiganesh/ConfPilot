"""LLM layer (Grok by default, any OpenAI-compatible API works).

Every function has a rule-based fallback, so the app still works with no API key
or when the LLM call fails during a live demo.
"""
import json
import logging
import re
import time
from contextvars import ContextVar

from . import config

log = logging.getLogger(__name__)
_client = None
# Set when any LLM call in the current request failed and a fallback was used.
# Holds {"reason": ...} for the current request. A mutable dict, so AI calls made in worker threads
# (which run in a copy of the request's context) can still report a failure back to the request.
_fallback_used = ContextVar("llm_fallback_used", default=None)
_check_cache = {"at": 0.0, "result": None}


def enabled():
    return bool(config.LLM_API_KEY)


def start_request():
    _fallback_used.set({"reason": None})


def fallback_reason():
    """Why the AI was skipped in this request (None if it worked or is not configured)."""
    state = _fallback_used.get()
    return state["reason"] if state else None


def _note_failure(where, exc):
    msg = _error_text(exc)
    log.warning("LLM %s failed: %s", where, msg)
    if "401" in msg or "403" in msg or ("key" in msg.lower() and ("invalid" in msg.lower() or "incorrect" in msg.lower())):
        reason = "the API key was rejected"
    elif "429" in msg or "rate" in msg.lower():
        reason = "the AI provider is rate limiting"
    elif "timed out" in msg.lower() or "timeout" in msg.lower():
        reason = "the AI provider timed out"
    else:
        reason = "the AI call failed"
    state = _fallback_used.get()
    if state is None:
        state = {"reason": None}
        _fallback_used.set(state)
    state["reason"] = reason
    from . import telemetry

    telemetry.record_fallback(reason)


def _error_text(exc):
    """Readable error: status code plus the provider's own message, not just 'Error code: 400'."""
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    msg = ""
    if isinstance(body, dict):
        err = body.get("error", body)
        msg = err.get("message") or err.get("error") or json.dumps(err) if isinstance(err, dict) else str(err)
    elif body:
        msg = str(body)
    msg = (msg or str(exc)).strip()
    return f"{status}: {msg}"[:300] if status else msg[:300]


_NOT_CHAT = re.compile(r"tts|audio|image|embed|aqa|computer-use|deep-research|veo|imagen|whisper|guard|moderation", re.I)


def _model_sort_key(name):
    # Newest versions first: compare the numbers in the name, e.g. gemini-3.8-flash before gemini-2.5-flash.
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", name)[:2]]
    return [-n for n in nums] + [len(name)]


def _available_models():
    """Chat models the key can use, newest first, without Google's 'models/' prefix."""
    try:
        ids = [m.id.removeprefix("models/") for m in _get_client().models.list().data]
    except Exception:
        return []
    chat = [i for i in ids if not _NOT_CHAT.search(i)]
    return sorted(chat, key=_model_sort_key)[:12]


def _suggested_model(error_text):
    """Some providers name a replacement in the error, e.g. 'use models/gemini-3.8-flash'."""
    m = re.search(r"\buse (?:models/)?([A-Za-z0-9][\w.-]*\d[\w.-]*)", error_text)
    return m.group(1).rstrip(".") if m else None


def check():
    """Tiny real call to verify the key and model. Cached for 5 minutes."""
    if not enabled():
        return {"ok": False, "configured": False, "error": None}
    if time.time() - _check_cache["at"] < 300 and _check_cache["result"]:
        return _check_cache["result"]
    try:
        _complete('Reply with JSON {"ok": true}', "ping", max_tokens=300)
        used = active_model()
        result = {"ok": True, "configured": True, "model": used, "error": None}
        notes = [f"{old} is retired; using {new}. Update LLM_MODEL / LLM_FALLBACK_MODELS in .env to match."
                 for old, new in _replacements.items()]
        if used != _replacements.get(config.LLM_MODEL, config.LLM_MODEL):
            notes.append(f"{config.LLM_MODEL} is busy right now, so the backup model {used} is answering.")
        if notes:
            result["note"] = " ".join(notes)
    except Exception as exc:
        result = {"ok": False, "configured": True, "model": config.LLM_MODEL, "error": _error_text(exc)}
        models = _available_models()
        suggested = _suggested_model(result["error"])
        current = config.LLM_MODEL.removeprefix("models/")
        if suggested and suggested != current:
            result["hint"] = f"The provider recommends a different model. Set LLM_MODEL={suggested} in .env and run ./start.sh."
        elif models and current not in models:
            result["hint"] = (f"Your account doesn't offer '{current}'. Set LLM_MODEL in .env to one of: "
                              f"{', '.join(models[:6])}")
        if models:
            result["available_models"] = models
        if "hint" not in result and _is_transient(exc) and getattr(exc, "status_code", None) in (429, 500, 502, 503, 504):
            backup = next((m for m in models if "lite" in m and m != current), None)
            result["hint"] = ("The AI provider is busy or rate limiting right now (usually temporary). "
                              + (f"Add a backup: LLM_FALLBACK_MODELS={backup} in .env and run ./start.sh."
                                 if backup and not config.LLM_FALLBACK_MODELS else "Try again in a minute."))
        if "hint" not in result and "timed out" in result["error"].lower():
            result["hint"] = ("The model answered too slowly. Try a faster model"
                              + (f" such as {next((m for m in models if 'lite' in m), models[0])}" if models else "")
                              + ", or raise LLM_TIMEOUT in .env (seconds).")
        if "hint" not in result and getattr(exc, "status_code", None) in (400, 401, 403):
            result["hint"] = ("Check LLM_API_KEY in .env (xAI keys start with 'xai-') and that LLM_BASE_URL "
                              "matches the provider the key is from.")
    _check_cache.update(at=time.time(), result=result)
    return result


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL, timeout=config.LLM_TIMEOUT, max_retries=1)
    return _client


# Optional request settings, dropped one by one if the provider/model rejects them (HTTP 400),
# e.g. models that don't support JSON mode or a custom temperature. What works is remembered.
_OPTIONAL = ["reasoning_effort", "response_format", "temperature", "max_tokens"]
_dropped = set()


_TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}
_sticky = {"model": None, "until": 0.0}  # a backup that worked recently is tried first for 5 minutes


def _is_transient(exc):
    from openai import APIConnectionError, APIStatusError, APITimeoutError

    if isinstance(exc, (APITimeoutError, APIConnectionError)):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code in _TRANSIENT_STATUS


def active_model():
    if _sticky["model"] and time.time() < _sticky["until"]:
        return _sticky["model"]
    return config.LLM_MODEL


_replacements = {}  # retired model -> the replacement the provider named, e.g. gemini-2.5-flash-lite -> gemini-3.5-flash-lite


def _complete(system, user, max_tokens):
    """Try the main model, then each backup model when one is busy, rate limited or too slow.

    If a provider says a model is retired and names a replacement ("use models/X"), switch to it.
    """
    from openai import NotFoundError

    def resolve(m):
        return _replacements.get(m, m)

    models = list(dict.fromkeys(resolve(m) for m in [active_model(), config.LLM_MODEL, *config.LLM_FALLBACK_MODELS]))
    errors = []
    i = 0
    while i < len(models):
        model = models[i]
        i += 1
        try:
            text = _complete_one(model, system, user, max_tokens)
            if model != resolve(config.LLM_MODEL):
                _sticky.update(model=model, until=time.time() + 300)
            elif _sticky["model"]:
                _sticky.update(model=None, until=0.0)
            return text
        except NotFoundError as exc:
            replacement = _suggested_model(_error_text(exc))
            if replacement and replacement != model and replacement not in models:
                log.warning("LLM model %s is retired; switching to the suggested %s", model, replacement)
                _replacements[model] = replacement
                models.insert(i, replacement)
            errors.append((model, exc))
        except Exception as exc:
            if not _is_transient(exc):
                raise
            log.warning("LLM model %s unavailable (%s)", model, _error_text(exc))
            errors.append((model, exc))
    # Report the main model's error: it explains the problem better than a backup's.
    main = resolve(config.LLM_MODEL)
    raise next((e for m, e in errors if m == main), errors[-1][1])


def _complete_one(model, system, user, max_tokens):
    from . import telemetry

    started = time.perf_counter()
    try:
        text = _complete_one_inner(model, system, user, max_tokens)
        telemetry.record_llm_call(model, "ok", time.perf_counter() - started)
        return text
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        outcome = ("retired" if status == 404 else "rejected" if status in (400, 401, 403)
                   else "busy" if _is_transient(exc) else "error")
        telemetry.record_llm_call(model, outcome, time.perf_counter() - started)
        span = telemetry.current_span()
        if span is not None:
            span.add_event("llm.call_failed", {"llm.model": model, "outcome": outcome, "error": _error_text(exc)})
        raise


def _complete_one_inner(model, system, user, max_tokens):
    from openai import BadRequestError

    from . import chaos

    chaos.llm_call()

    optional = {"response_format": {"type": "json_object"}, "temperature": 0.3, "max_tokens": max_tokens}
    if config.LLM_REASONING_EFFORT:
        optional["reasoning_effort"] = config.LLM_REASONING_EFFORT
    while True:
        kwargs = {k: v for k, v in optional.items() if k not in _dropped}
        try:
            resp = _get_client().chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                **kwargs)
            return resp.choices[0].message.content or ""
        except BadRequestError as exc:
            remaining = [k for k in _OPTIONAL if k not in _dropped]
            text = _error_text(exc).lower()
            if "model" in text and ("not found" in text or "does not exist" in text or "invalid" in text):
                raise  # wrong model name: retrying without settings won't help
            if "api key" in text or "apikey" in text or "unauthor" in text:
                raise
            if not remaining:
                raise
            # Drop the setting the error names, otherwise the next one in order.
            named = next((k for k in remaining if k in text or k.replace("_", "") in text), remaining[0])
            log.warning("LLM rejected %r (%s); retrying without it", named, _error_text(exc))
            _dropped.add(named)


def _chat_json(system, user, max_tokens=1500):
    text = _complete(system, user, max_tokens)
    match = re.search(r"\{.*\}", text, re.S)  # tolerate code fences, reasoning text or preamble
    if not match:
        raise ValueError(f"AI reply was not JSON: {text[:120]!r}")
    return json.loads(match.group(0))


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
        _note_failure("understand", exc)
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
            _note_failure("explain", exc)
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
        _note_failure("icebreakers", exc)
        return fallback
