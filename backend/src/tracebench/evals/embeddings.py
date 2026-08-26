import asyncio
import hashlib
from collections.abc import Sequence
from itertools import pairwise
from typing import TYPE_CHECKING, Protocol

import numpy as np

from tracebench.config import EmbeddingsBackend, Settings
from tracebench.evals.text import tokens
from tracebench.logging import get_logger

if TYPE_CHECKING:
    # fastembed is an optional extra, so it is only imported when the model is loaded.
    from fastembed import TextEmbedding

log = get_logger(__name__)


class Embedder(Protocol):
    @property
    def name(self) -> str: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    va, vb = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(va @ vb) / denom if denom else 0.0


class HashingEmbedder:
    """Deterministic, dependency-free embeddings via signed feature hashing.

    Word unigrams, bigrams and character trigrams are hashed into a fixed-size vector.
    It captures lexical rather than semantic similarity, which is enough for offline
    tests and CI without downloading a model.
    """

    def __init__(self, dimensions: int = 512) -> None:
        self._dimensions = dimensions

    @property
    def name(self) -> str:
        return f"hash-{self._dimensions}"

    def _vector(self, text: str) -> list[float]:
        vec = np.zeros(self._dimensions, dtype=np.float64)
        words = tokens(text)
        features = [*words, *(f"{a} {b}" for a, b in pairwise(words))]
        for word in words:
            padded = f"#{word}#"
            features.extend(padded[i : i + 3] for i in range(len(padded) - 2))
        for feature in features:
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self._dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[bucket] += sign
        norm = np.linalg.norm(vec)
        result: list[float] = (vec / norm if norm else vec).tolist()
        return result

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


class EmbedderUnavailableError(RuntimeError):
    pass


class FastEmbedEmbedder:
    def __init__(self, model_name: str, cache_dir: str | None = None) -> None:
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._model: TextEmbedding | None = None
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return f"fastembed:{self._model_name}"

    async def load(self) -> "TextEmbedding":
        async with self._lock:
            if self._model is None:
                try:
                    from fastembed import TextEmbedding

                    model = await asyncio.to_thread(
                        TextEmbedding, model_name=self._model_name, cache_dir=self._cache_dir
                    )
                except Exception as exc:
                    raise EmbedderUnavailableError(f"cannot load {self.name}: {exc}") from exc
                self._model = model
            return self._model

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        model = await self.load()

        def run() -> list[list[float]]:
            return [vector.tolist() for vector in model.embed(list(texts))]

        return await asyncio.to_thread(run)


class FallbackEmbedder:
    """Uses fastembed, switching to the fallback for good if the model cannot be loaded.

    Only a load failure triggers the switch. Inference errors propagate so a single run
    never mixes vectors from two embedders against one threshold.
    """

    def __init__(self, primary: FastEmbedEmbedder, fallback: Embedder) -> None:
        self._primary = primary
        self._fallback = fallback
        self._active: Embedder | None = None
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return (self._active or self._primary).name

    async def _resolve(self) -> Embedder:
        async with self._lock:
            if self._active is None:
                try:
                    await self._primary.load()
                    self._active = self._primary
                except EmbedderUnavailableError as exc:
                    log.warning("primary embedder unavailable, using fallback", error=str(exc))
                    self._active = self._fallback
            return self._active

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return await (await self._resolve()).embed(texts)


def build_embedder(settings: Settings) -> Embedder:
    if settings.embeddings_backend is EmbeddingsBackend.HASH:
        return HashingEmbedder()
    return FallbackEmbedder(
        FastEmbedEmbedder(settings.embeddings_model, settings.embeddings_cache_dir),
        HashingEmbedder(),
    )
