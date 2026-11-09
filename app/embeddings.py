"""Text embeddings. Default: fastembed (local ONNX model, no API key, no GPU).

EMBEDDINGS=openai uses an OpenAI-compatible embeddings API.
EMBEDDINGS=hash is an offline fallback (feature hashing) used when no model can be loaded.
It keeps the app runnable, but semantic quality is much lower.
"""
import hashlib
import logging
import math
import re
from functools import lru_cache

from . import config

log = logging.getLogger(__name__)
HASH_DIMS = 384


class HashEmbedder:
    name = "hash"
    dims = HASH_DIMS

    def embed(self, texts):
        return [self._one(t) for t in texts]

    def _one(self, text):
        words = re.findall(r"[a-z0-9]+", text.lower())
        feats = words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
        vec = [0.0] * HASH_DIMS
        for f in feats:
            h = int(hashlib.md5(f.encode()).hexdigest(), 16)
            vec[h % HASH_DIMS] += 1.0 if (h >> 8) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class FastEmbedder:
    name = "fastembed"

    def __init__(self, model_name):
        from fastembed import TextEmbedding

        self.model = TextEmbedding(model_name=model_name)
        self.dims = len(next(iter(self.model.embed(["probe"]))))

    def embed(self, texts):
        return [v.tolist() for v in self.model.embed(list(texts))]


class OpenAIEmbedder:
    name = "openai"

    def __init__(self):
        from openai import OpenAI

        self.client = OpenAI(api_key=config.OPENAI_EMBED_API_KEY)
        self.model = config.OPENAI_EMBED_MODEL
        self.dims = len(self.embed(["probe"])[0])

    def embed(self, texts):
        resp = self.client.embeddings.create(model=self.model, input=list(texts))
        return [d.embedding for d in resp.data]


@lru_cache(maxsize=1)
def get_embedder():
    choice = config.EMBEDDINGS
    try:
        if choice == "openai":
            return OpenAIEmbedder()
        if choice == "fastembed":
            return FastEmbedder(config.FASTEMBED_MODEL)
    except Exception as exc:  # model download blocked, package missing, bad key...
        log.warning("Embeddings provider %r unavailable (%s); falling back to hash embeddings", choice, exc)
    return HashEmbedder()
