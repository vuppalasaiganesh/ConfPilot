---
title: Elasticsearch features must work on the free Basic license
description: Keep search runnable on a stock single-node Elasticsearch 8.x with security off
when: PR modifies app/search.py, index mappings, docker-compose.yml or k8s manifests for Elasticsearch
actions: Flag paid-only features and suggest the Basic-license alternative
---

- Hybrid search fuses BM25 and kNN results with Reciprocal Rank Fusion in Python (`search.rrf`). Flag the
  `rrf` retriever, ELSER, `semantic_text` with Elastic inference endpoints, or other Platinum/Enterprise
  features unless they are optional and fall back cleanly.
- Mapping changes must also update `search.ingest` and keep the `embedding` dims taken from the embedder.
- Queries must exclude the `embedding` field from `_source` in responses.
