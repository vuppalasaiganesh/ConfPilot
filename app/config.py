import os

from dotenv import load_dotenv

load_dotenv()

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_INDEX_TALKS = os.getenv("ES_INDEX_TALKS", "talks")
ES_INDEX_PEOPLE = os.getenv("ES_INDEX_PEOPLE", "attendees")

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.x.ai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "grok-4")

EMBEDDINGS = os.getenv("EMBEDDINGS", "fastembed").lower()
FASTEMBED_MODEL = os.getenv("FASTEMBED_MODEL", "BAAI/bge-small-en-v1.5")
OPENAI_EMBED_API_KEY = os.getenv("OPENAI_EMBED_API_KEY", "")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
