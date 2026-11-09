import os

from dotenv import load_dotenv

load_dotenv()

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_INDEX_TALKS = os.getenv("ES_INDEX_TALKS", "talks")
ES_INDEX_PEOPLE = os.getenv("ES_INDEX_PEOPLE", "attendees")

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.x.ai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "grok-4")
# Backup models tried in order when the main one is busy, rate limited or too slow (comma separated).
LLM_FALLBACK_MODELS = [m.strip() for m in os.getenv("LLM_FALLBACK_MODELS", "").split(",") if m.strip()]
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "45"))
# "low" keeps "thinking" models (e.g. newer Gemini flash) fast. Empty = provider default.
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "low")

EMBEDDINGS = os.getenv("EMBEDDINGS", "fastembed").lower()
FASTEMBED_MODEL = os.getenv("FASTEMBED_MODEL", "BAAI/bge-small-en-v1.5")
OPENAI_EMBED_API_KEY = os.getenv("OPENAI_EMBED_API_KEY", "")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
