"""Elasticsearch data layer: index setup, ingest and hybrid (BM25 + kNN) search.

Hybrid fusion uses Reciprocal Rank Fusion computed in Python, so it works on the free
Basic license of any Elasticsearch 8.x (no paid retriever/RRF feature needed).
"""
import json
import logging
import time
from pathlib import Path

from elasticsearch import Elasticsearch, helpers

from . import chaos, config, telemetry
from .embeddings import get_embedder

log = logging.getLogger(__name__)
DATA = Path(__file__).resolve().parent.parent / "data"
RRF_K = 60


def es_client():
    return Elasticsearch(config.ES_URL, request_timeout=30)


def talk_text(t):
    return f"{t['title']}. {t['abstract']} Track: {t['track']}. Level: {t['level']}. Tags: {', '.join(t['tags'])}."


def person_text(p):
    return f"{p['role']}. {p['working_on']} Interests: {', '.join(p['interests'])}."


def _create_index(es, name, dims, properties, embedder_name):
    if es.indices.exists(index=name):
        es.indices.delete(index=name)
    es.indices.create(
        index=name,
        mappings={
            "_meta": {"embedder": embedder_name, "dims": dims},
            "properties": {
                **properties,
                "embedding": {"type": "dense_vector", "dims": dims, "index": True, "similarity": "cosine"},
            },
        },
    )


def ingest(es=None):
    es = es or es_client()
    emb = get_embedder()
    talks = json.loads((DATA / "talks.json").read_text())
    people = json.loads((DATA / "attendees.json").read_text())

    _create_index(es, config.ES_INDEX_TALKS, emb.dims, {
        "id": {"type": "keyword"},
        "title": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
        "abstract": {"type": "text"},
        "speakers": {"type": "text"},
        "track": {"type": "keyword"},
        "level": {"type": "keyword"},
        "tags": {"type": "keyword", "fields": {"text": {"type": "text"}}},
        "room": {"type": "keyword"},
        "start": {"type": "date"},
        "end": {"type": "date"},
    }, emb.name)
    _create_index(es, config.ES_INDEX_PEOPLE, emb.dims, {
        "id": {"type": "keyword"},
        "name": {"type": "text"},
        "role": {"type": "keyword"},
        "company": {"type": "keyword"},
        "working_on": {"type": "text"},
        "interests": {"type": "keyword", "fields": {"text": {"type": "text"}}},
    }, emb.name)

    talk_vecs = emb.embed([talk_text(t) for t in talks])
    people_vecs = emb.embed([person_text(p) for p in people])
    helpers.bulk(es, ({"_index": config.ES_INDEX_TALKS, "_id": t["id"], "_source": {**t, "embedding": v}}
                      for t, v in zip(talks, talk_vecs)))
    helpers.bulk(es, ({"_index": config.ES_INDEX_PEOPLE, "_id": p["id"], "_source": {**p, "embedding": v}}
                      for p, v in zip(people, people_vecs)))
    es.indices.refresh(index=[config.ES_INDEX_TALKS, config.ES_INDEX_PEOPLE])
    return {"talks": len(talks), "attendees": len(people), "embedder": emb.name, "dims": emb.dims}


def _filters(levels=None, days=None, tracks=None):
    f = []
    if levels:
        f.append({"terms": {"level": levels}})
    if tracks:
        f.append({"terms": {"track": tracks}})
    if days:
        f.append({"bool": {"should": [
            {"range": {"start": {"gte": f"{d}T00:00:00", "lte": f"{d}T23:59:59"}}} for d in days
        ], "minimum_should_match": 1}})
    return f


def rrf(*ranked_lists, k=RRF_K):
    """Reciprocal Rank Fusion: score(d) = sum over lists of 1 / (k + rank)."""
    scores, docs, sources = {}, {}, {}
    for name, hits in ranked_lists:
        for rank, hit in enumerate(hits, 1):
            _id = hit["_id"]
            scores[_id] = scores.get(_id, 0.0) + 1.0 / (k + rank)
            docs[_id] = hit["_source"]
            sources.setdefault(_id, []).append(f"{name}#{rank}")
    order = sorted(scores, key=scores.get, reverse=True)
    return [{**docs[i], "score": round(scores[i], 5), "matched_by": sources[i]} for i in order]


def hybrid_search_talks(query, size=40, levels=None, days=None, tracks=None, es=None):
    es = es or es_client()
    started = time.perf_counter()
    with telemetry.step("embed_query", embedder=get_embedder().name):
        chaos.slow_search()
        vec = get_embedder().embed([query])[0]
    flt = _filters(levels, days, tracks)
    excludes = {"excludes": ["embedding"]}

    bm25 = es.search(index=config.ES_INDEX_TALKS, size=size, source=excludes, query={
        "bool": {
            "must": [{"multi_match": {
                "query": query,
                "fields": ["title^3", "tags.text^2", "abstract", "speakers"],
                "fuzziness": "AUTO",
            }}],
            "filter": flt,
        }
    })["hits"]["hits"]
    knn = es.search(index=config.ES_INDEX_TALKS, size=size, source=excludes, knn={
        "field": "embedding", "query_vector": vec, "k": size, "num_candidates": max(100, size * 4),
        "filter": flt,
    })["hits"]["hits"]
    results = rrf(("keyword", bm25), ("semantic", knn))[:size]
    telemetry.record_search(time.perf_counter() - started, len(results))
    return chaos.corrupt(results)


def similar_people(text, size=5, es=None):
    es = es or es_client()
    vec = get_embedder().embed([text])[0]
    hits = es.search(index=config.ES_INDEX_PEOPLE, size=size, source={"excludes": ["embedding"]}, knn={
        "field": "embedding", "query_vector": vec, "k": size, "num_candidates": 100,
    })["hits"]["hits"]
    return [{**h["_source"], "score": round(h["_score"], 4)} for h in hits]


def get_talks(ids, es=None):
    es = es or es_client()
    resp = es.mget(index=config.ES_INDEX_TALKS, ids=list(ids), source_excludes=["embedding"])
    return [d["_source"] for d in resp["docs"] if d.get("found")]


def facets(es=None):
    es = es or es_client()
    resp = es.search(index=config.ES_INDEX_TALKS, size=0, aggs={
        "tracks": {"terms": {"field": "track", "size": 50}},
        "levels": {"terms": {"field": "level", "size": 10}},
        "days": {"date_histogram": {"field": "start", "calendar_interval": "day", "format": "yyyy-MM-dd",
                                    "min_doc_count": 1}},
    })
    a = resp["aggregations"]
    return {
        "tracks": [b["key"] for b in a["tracks"]["buckets"]],
        "levels": [b["key"] for b in a["levels"]["buckets"]],
        "days": [b["key_as_string"] for b in a["days"]["buckets"]],
        "embedder": es.indices.get_mapping(index=config.ES_INDEX_TALKS)[config.ES_INDEX_TALKS]["mappings"]
        .get("_meta", {}).get("embedder"),
    }
