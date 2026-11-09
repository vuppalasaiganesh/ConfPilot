"""Fault injection for the observability / AI SRE demos.

Three realistic faults, each leaving a different trail in traces, metrics and logs:
  slow_search_ms  the query-embedding step becomes slow (latency spike in the embed_query span)
  llm_outage      every AI call times out (fallbacks, error logs, confpilot.ai.fallbacks metric)
  bad_data_rate   a share of searches return a talk record with no start time, which crashes the
                  planner with a KeyError (HTTP 500s with stack traces)

Set them at startup with env vars (CHAOS_SLOW_SEARCH_MS, CHAOS_LLM_OUTAGE, CHAOS_BAD_DATA_RATE),
or at runtime with scripts/chaos.sh when CHAOS_ENABLED=true. Off by default.
"""
import logging
import os
import random
import time

log = logging.getLogger(__name__)
ENABLED = os.getenv("CHAOS_ENABLED", "").lower() in ("1", "true", "yes")


def _float(name):
    try:
        return float(os.getenv(name, "0") or 0)
    except ValueError:
        return 0.0


state = {
    "slow_search_ms": _float("CHAOS_SLOW_SEARCH_MS"),
    "llm_outage": os.getenv("CHAOS_LLM_OUTAGE", "").lower() in ("1", "true", "yes"),
    "bad_data_rate": min(max(_float("CHAOS_BAD_DATA_RATE"), 0.0), 1.0),
}
if any(state.values()):
    log.warning("Fault injection active at startup: %s", state)


def update(**changes):
    for k, v in changes.items():
        if k in state and v is not None:
            state[k] = type(state[k])(v)
    state["bad_data_rate"] = min(max(state["bad_data_rate"], 0.0), 1.0)
    log.warning("Fault injection changed: %s", state)
    return dict(state)


def reset():
    return update(slow_search_ms=0.0, llm_outage=False, bad_data_rate=0.0)


def slow_search():
    if state["slow_search_ms"] > 0:
        time.sleep(state["slow_search_ms"] / 1000)


def llm_call():
    """Raise a timeout like a real provider outage would."""
    if state["llm_outage"]:
        import httpx
        from openai import APITimeoutError

        raise APITimeoutError(request=httpx.Request("POST", "https://llm.invalid/v1/chat/completions"))


def corrupt(results):
    """Drop the start time from one result, the way a bad record in the index would look."""
    if results and state["bad_data_rate"] > 0 and random.random() < state["bad_data_rate"]:
        victim = dict(results[0])
        victim.pop("start", None)
        return [victim, *results[1:]]
    return results
