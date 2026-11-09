---
title: No secrets in the repository
description: API keys and tokens live only in .env, which is git-ignored
when: PR touches any file
actions: Flag anything that looks like a real API key or token; flag changes that stop ignoring .env
---

- Flag strings that look like real keys (`xai-`, `gsk_`, `sk-`, `AIza`, `auth_` followed by 20+ characters),
  in code, docs, tests or `.env.example`. Placeholders such as `xai-...` or `your-key` are fine.
- `.gitignore` must keep ignoring `.env` and `.env.k8s`.
