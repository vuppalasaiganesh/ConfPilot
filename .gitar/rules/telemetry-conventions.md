---
title: Telemetry conventions
description: Keep traces, metrics and logs useful for Dash0 and cheap to store
when: PR adds request handling steps, metrics, spans or log lines
actions: Check new steps are traced, metric labels are low-cardinality, and logs carry no secrets or user text
---

- New steps inside a request are wrapped in `telemetry.step("name", timings)` so they show as spans and in UI timings.
- Metric attributes must be low-cardinality (model, outcome, reason). Flag user ids, talk ids, query text or
  free-form error messages used as metric attributes.
- Logs must never include API keys, tokens or full user profile text. Error messages from providers are fine.
- Names: spans are snake_case verbs (`hybrid_search`, `embed_query`); metrics are `confpilot.<area>.<thing>`.
