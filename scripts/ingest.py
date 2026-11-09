"""Create the Elasticsearch indices and load talks + attendees with embeddings.

Run from the confpilot folder:  python -m scripts.ingest
Waits for Elasticsearch to come up (useful in docker compose / Kubernetes Jobs).
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import search  # noqa: E402


def main():
    es = search.es_client()
    for _ in range(60):
        try:
            if es.ping():
                break
        except Exception:
            pass
        print("Waiting for Elasticsearch...")
        time.sleep(3)
    else:
        sys.exit("Elasticsearch did not become reachable")
    print("Ingested:", search.ingest(es))


if __name__ == "__main__":
    main()
