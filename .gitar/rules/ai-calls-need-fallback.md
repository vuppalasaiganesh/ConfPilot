---
title: Every AI call needs a fallback
description: The app must keep working when the LLM is down, slow, rate limited or misconfigured
when: PR adds or changes code that calls an LLM (openai client, chat.completions, llm._chat_json, llm._complete)
actions: Flag any LLM call without a rule-based fallback; suggest the fix using the existing pattern
---

ConfPilot is demoed live, so an AI outage must never break a request.

1. LLM calls go through `llm._chat_json` / `llm._complete` only. Flag direct `OpenAI(...)` or
   `chat.completions.create` calls anywhere else.
2. Every caller wraps the call in `try/except Exception` and, on failure, calls `llm._note_failure(where, exc)`
   and returns a rule-based result (see `llm.understand`, `llm.explain_agenda`, `chat.understand`).
3. Output from the model is untrusted: ids, modes and levels must be checked against known values before use
   (see how `_intent_llm` filters `remove_ids`, `days` and `levels`).
4. Never put an API key, model name or base URL in code. They come from `app/config.py` (environment).
