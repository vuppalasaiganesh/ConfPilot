"""Send realistic traffic so dashboards, traces and AI agents have something to look at.

Usage:  python3 scripts/load.py                 # 2 requests/second until Ctrl+C
        python3 scripts/load.py --rps 5 --minutes 3 --url http://localhost:8000
Standard library only, so it runs anywhere.
"""
import argparse
import json
import random
import threading
import time
import urllib.error
import urllib.request

PROFILES = [
    "SRE at a bank, serious about OpenTelemetry, SLOs and eBPF",
    "ML engineer deploying LLMs, GPU scheduling and AI agents on Kubernetes",
    "Student new to cloud native, beginner talks on networking and GitOps",
    "Platform lead: internal developer platforms, multi-tenancy, cutting cloud costs",
    "Security engineer: supply chain, policy as code, zero trust",
    "How can we save money and help the planet?",
]
CHATS = ["Swap anything on day 2 for AI talks", "Add a beginner GPU talk", "Who is speaking about service mesh?",
         "Drop the policy talks", "thanks!"]
stats = {"ok": 0, "error": 0, "lock": threading.Lock()}


def post(url, path, body):
    req = urllib.request.Request(url + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read() or b"{}")
            ok = True
    except (urllib.error.URLError, TimeoutError, ValueError):
        data, ok = {}, False
    with stats["lock"]:
        stats["ok" if ok else "error"] += 1
    return data


def one_user(url):
    profile = random.choice(PROFILES)
    plan = post(url, "/api/plan", {"profile": profile})
    ids = [t["id"] for t in plan.get("agenda", [])]
    if ids and random.random() < 0.6:
        post(url, "/api/chat", {"message": random.choice(CHATS), "profile": profile, "agenda_ids": ids})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--rps", type=float, default=2.0)
    ap.add_argument("--minutes", type=float, default=0, help="0 = run until Ctrl+C")
    a = ap.parse_args()
    end = time.time() + a.minutes * 60 if a.minutes else float("inf")
    print(f"Sending ~{a.rps}/s to {a.url}. Ctrl+C to stop.")
    last = time.time()
    try:
        while time.time() < end:
            threading.Thread(target=one_user, args=(a.url,), daemon=True).start()
            time.sleep(1 / a.rps)
            if time.time() - last > 10:
                print(f"  ok={stats['ok']} errors={stats['error']}")
                last = time.time()
    except KeyboardInterrupt:
        pass
    print(f"Done: ok={stats['ok']} errors={stats['error']}")


if __name__ == "__main__":
    main()
