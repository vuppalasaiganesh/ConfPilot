---
title: Agenda must stay clash-free
description: Any code that builds or edits an agenda must never produce two overlapping talks
when: PR modifies app/planner.py, app/chat.py, or the agenda logic in app/static/index.html
actions: Check every path that adds talks for an overlap check; require a test for new agenda-editing behaviour
---

"No time clashes" is the product's core promise.

- Adding a talk must check `planner._overlaps` against everything already in the agenda.
- In replace mode, never displace a talk added earlier in the same turn (see `chat.apply`).
- A PR that changes agenda logic must add or update a test in `tests/test_planner.py` or `tests/test_chat.py`
  that asserts no two talks in the result overlap.
