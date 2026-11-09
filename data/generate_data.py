"""Generate a realistic, deterministic set of cloud-native conference talks and attendees.

Run:  python data/generate_data.py
Writes data/talks.json and data/attendees.json. Replace them with a real schedule any time:
each talk needs id, title, abstract, speakers, track, level, tags, room, start, end.
"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)
OUT = Path(__file__).parent

TOPICS = {
    "Security": [
        ("eBPF", "runtime threat detection with eBPF probes that watch syscalls without kernel modules"),
        ("Supply Chain", "signing container images with Sigstore and enforcing provenance with SLSA attestations"),
        ("Policy", "admission control with Kyverno and OPA Gatekeeper to stop misconfigurations before they ship"),
        ("Zero Trust", "workload identity with SPIFFE/SPIRE and mTLS everywhere across clusters"),
        ("Secrets", "rotating secrets automatically with External Secrets Operator and Vault"),
    ],
    "Observability": [
        ("OpenTelemetry", "instrumenting services with OpenTelemetry and shipping traces, metrics and logs through the Collector"),
        ("Prometheus", "scaling Prometheus with remote write, sharding and long-term storage"),
        ("eBPF", "zero-code observability with eBPF auto-instrumentation"),
        ("Logging", "cutting logging costs by sampling, routing and dropping noisy logs at the edge"),
        ("SLOs", "defining SLOs and error budgets that engineers actually use for alerting"),
    ],
    "AI + ML": [
        ("AI Agents", "running autonomous AI agents on Kubernetes with tool calling, sandboxes and guardrails"),
        ("LLM Inference", "serving LLMs on GPUs with vLLM, autoscaling and KV-cache aware routing"),
        ("GPUs", "sharing and scheduling GPUs efficiently with DRA, MIG and time-slicing"),
        ("MLOps", "building reproducible ML pipelines with Kubeflow and model registries"),
        ("RAG", "production retrieval-augmented generation with vector search and evaluation"),
    ],
    "Platform Engineering": [
        ("Internal Developer Platform", "building an internal developer platform with Backstage golden paths"),
        ("GitOps", "managing hundreds of clusters declaratively with Argo CD and Flux"),
        ("Multi-tenancy", "safe multi-tenancy with namespaces, vCluster and hierarchical quotas"),
        ("Crossplane", "provisioning cloud infrastructure from Kubernetes with Crossplane compositions"),
        ("Developer Experience", "reducing developer cognitive load with paved roads and self-service"),
    ],
    "Networking": [
        ("Service Mesh", "sidecar-less service mesh with Istio ambient mode and Cilium"),
        ("Gateway API", "migrating from Ingress to the Gateway API for traffic management"),
        ("eBPF", "replacing kube-proxy with eBPF-based networking for lower latency"),
        ("Multi-cluster", "connecting clusters across regions with multi-cluster services"),
    ],
    "Cost + Sustainability": [
        ("FinOps", "measuring and cutting Kubernetes spend with OpenCost and right-sizing"),
        ("Autoscaling", "scaling to zero and bin-packing nodes with Karpenter and KEDA"),
        ("Green Software", "measuring the carbon footprint of workloads with Kepler"),
    ],
    "Storage + Data": [
        ("Databases on Kubernetes", "running stateful Postgres on Kubernetes with operators and backups"),
        ("Storage", "persistent storage with CSI drivers, snapshots and disaster recovery"),
        ("Streaming", "event streaming with Kafka on Kubernetes using Strimzi"),
    ],
    "Runtime + WebAssembly": [
        ("WebAssembly", "running WebAssembly workloads next to containers with SpinKube"),
        ("Containers", "faster, smaller and safer containers with distroless images and rootless runtimes"),
        ("Edge", "running lightweight Kubernetes at the edge with K3s and KubeEdge"),
    ],
}

TITLE_PATTERNS = [
    "{topic} in Production: Lessons from {n} Clusters",
    "A Beginner's Guide to {topic}",
    "{topic} Deep Dive: What We Got Wrong",
    "From Zero to {topic} in 30 Minutes",
    "Scaling {topic} at {company}",
    "{topic} Anti-Patterns and How to Avoid Them",
    "Hands-on: {topic} for Platform Teams",
    "The Future of {topic}",
    "Debugging {topic} When Everything Is on Fire",
    "How {company} Cut Incidents in Half with {topic}",
]
LEVEL_FOR_PATTERN = ["Advanced", "Beginner", "Advanced", "Beginner", "Intermediate",
                     "Intermediate", "Intermediate", "Beginner", "Advanced", "Intermediate"]
COMPANIES = ["Northwind Bank", "Acme Retail", "Globex", "Initech", "Umbrella Health", "Stark Logistics",
             "Wayne Media", "Hooli", "Pied Piper", "Vandelay Shipping", "Soylent Foods", "Cyberdyne Cloud"]
FIRST = ["Aisha", "Ben", "Chen", "Diego", "Elena", "Farah", "Gabriel", "Hana", "Ivan", "Jia", "Kofi",
         "Lena", "Mateo", "Nadia", "Omar", "Priya", "Quinn", "Rahul", "Sofia", "Tariq", "Uma", "Viktor",
         "Wei", "Ximena", "Yusuf", "Zara", "Arjun", "Maya", "Lucas", "Ines"]
LAST = ["Okafor", "Lindqvist", "Wang", "Hernandez", "Petrova", "Rahman", "Silva", "Tanaka", "Novak",
        "Liu", "Mensah", "Fischer", "Rossi", "Haddad", "Patel", "Kim", "Reddy", "Costa", "Ali", "Moreau"]
EXTRA = [
    "We share dashboards, configs and the mistakes we made along the way.",
    "Expect a live demo and a reference repo you can clone afterwards.",
    "No prior experience required; we start from first principles.",
    "We cover benchmarks, failure modes and the trade-offs we would make again.",
    "You will leave with a checklist you can apply on Monday.",
    "Includes a case study from a large-scale production rollout.",
]
ROOMS = ["Hall A", "Hall B", "Room 101", "Room 102", "Room 201", "Room 202", "Room 301", "Room 302"]
DAYS = [datetime(2027, 3, 23), datetime(2027, 3, 24), datetime(2027, 3, 25)]
SLOT_STARTS = ["10:00", "11:00", "11:45", "14:00", "14:45", "15:45", "16:30"]


def person():
    return f"{random.choice(FIRST)} {random.choice(LAST)}"


def make_talks():
    pool = []
    for track, items in TOPICS.items():
        for topic, desc in items:
            for i in random.sample(range(len(TITLE_PATTERNS)), 5):
                pool.append((track, topic, desc, i))
    random.shuffle(pool)

    slots = [(d, s, r) for d in DAYS for s in SLOT_STARTS for r in ROOMS]
    random.shuffle(slots)
    talks = []
    for n, ((track, topic, desc, pi), (day, start, room)) in enumerate(zip(pool, slots), 1):
        company = random.choice(COMPANIES)
        title = TITLE_PATTERNS[pi].format(topic=topic, company=company, n=random.choice([12, 40, 150, 600]))
        level = LEVEL_FOR_PATTERN[pi]
        h, m = map(int, start.split(":"))
        begin = day.replace(hour=h, minute=m)
        end = begin + timedelta(minutes=35)
        speakers = [f"{person()} ({company})"] + ([f"{person()} ({random.choice(COMPANIES)})"] if random.random() < 0.35 else [])
        abstract = (f"This {level.lower()} session covers {desc}. "
                    f"The speakers explain how the team at {company} approached it, what broke, and what worked. "
                    f"{random.choice(EXTRA)}")
        tags = sorted({topic, track} | ({"eBPF"} if "eBPF" in desc else set()) | ({"Kubernetes"} if "Kubernetes" in desc else set()))
        talks.append({
            "id": f"T{n:03d}",
            "title": title,
            "abstract": abstract,
            "speakers": speakers,
            "track": track,
            "level": level,
            "tags": tags,
            "room": room,
            "start": begin.isoformat(),
            "end": end.isoformat(),
        })
    talks.sort(key=lambda t: (t["start"], t["room"]))
    return talks


ROLES = ["SRE", "Platform Engineer", "Backend Developer", "Security Engineer", "ML Engineer",
         "Engineering Manager", "DevOps Engineer", "Data Engineer", "Student", "Cloud Architect"]


def make_attendees():
    all_topics = [(track, topic, desc) for track, items in TOPICS.items() for topic, desc in items]
    people = []
    for i in range(1, 61):
        picks = random.sample(all_topics, 2)
        role = random.choice(ROLES)
        company = random.choice(COMPANIES)
        working_on = (f"{role} at {company}. Currently working on {picks[0][2]}. "
                      f"Also curious about {picks[1][1]}.")
        people.append({
            "id": f"A{i:03d}",
            "name": person(),
            "role": role,
            "company": company,
            "working_on": working_on,
            "interests": [picks[0][1], picks[1][1]],
        })
    return people


if __name__ == "__main__":
    talks = make_talks()
    people = make_attendees()
    (OUT / "talks.json").write_text(json.dumps(talks, indent=2))
    (OUT / "attendees.json").write_text(json.dumps(people, indent=2))
    print(f"Wrote {len(talks)} talks and {len(people)} attendees to {OUT}")
