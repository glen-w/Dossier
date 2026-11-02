"""Passage vectors in evidence.db. Ollama embeds. No second store."""

from __future__ import annotations

import math
import struct
from collections.abc import Callable
from typing import Protocol

import httpx

from dossier.llm.validate import LlmConfigError, validate_ollama_url
from dossier.store import Corpus

BATCH = 16


class EmbedError(Exception):
    """The embedder could not return vectors."""


class Embedder(Protocol):
    model: str

    def check(self) -> tuple[bool, str]: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbedder:
    """POST /api/embed on the Ollama root. This is not a completion."""

    def __init__(self, base_url: str, allow_remote: bool, model: str) -> None:
        self.base_url = base_url.rstrip("/").removesuffix("/v1")
        self.allow_remote = allow_remote
        self.model = model

    def check(self) -> tuple[bool, str]:
        try:
            validate_ollama_url(self.base_url, self.allow_remote)
        except LlmConfigError as exc:
            return False, str(exc)
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            return False, f"Ollama unreachable: {exc}"
        names = [item.get("name", "") for item in (data.get("models") or [])]
        model = self.model
        if not any(model in name or name.startswith(f"{model}:") for name in names):
            return False, f"model {model!r} not in Ollama tags ({len(names)} installed)"
        return True, "ok"

    def embed(self, texts: list[str]) -> list[list[float]]:
        validate_ollama_url(self.base_url, self.allow_remote)
        if not texts:
            return []
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": self.model, "input": texts},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise EmbedError(f"Ollama embed failed: {exc}") from exc
        rows = data.get("embeddings")
        if rows is None and data.get("embedding") is not None:
            rows = [data["embedding"]]
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise EmbedError("Ollama embed returned the wrong number of vectors")
        out: list[list[float]] = []
        for row in rows:
            if not isinstance(row, list) or not row:
                raise EmbedError("Ollama embed returned an empty vector")
            out.append([float(value) for value in row])
        return out


PAGE = BATCH * 8


class HashEmbedder:
    """Deterministic bag-of-words vectors. No model and no network.

    For tests and the retrieval eval, so CI never needs Ollama. Words hash into
    `dim` buckets, so texts that share words are close and texts that do not are not.
    """

    def __init__(self, model: str = "hash-bow", dim: int = 64) -> None:
        self.model = model
        self.dim = dim

    def check(self) -> tuple[bool, str]:
        return True, "ok"

    def embed(self, texts: list[str]) -> list[list[float]]:
        import hashlib
        import re

        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for word in re.findall(r"[a-z0-9]{3,}", text.lower()):
                digest = hashlib.sha256(word.encode()).digest()
                bucket = int.from_bytes(digest[:4], "little") % self.dim
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vec[bucket] += sign
            if not any(vec):
                vec[0] = 1.0
            out.append(vec)
        return out


def index_passages(
    corpus: Corpus,
    embedder: Embedder,
    *,
    on_batch: Callable[[int, int], None] | None = None,
    sources: tuple[str, ...] = (),
    limit: int | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> int:
    """Store vectors for passages missing this model. Returns how many exist.

    Each page is committed, so a stop or a crash keeps what was embedded and the
    next run resumes with what is still missing. `sources` and `limit` narrow a run.
    A model that now returns a different vector size is refused, never mixed in.
    """
    model = embedder.model
    corpus.drop_other_vectors(model)
    total = corpus.count_missing_vectors(model, sources=sources)
    if limit is not None:
        total = min(total, max(0, int(limit)))
    done = 0
    if on_batch is not None:
        on_batch(done, total)
    dim = corpus.vector_dim(model)
    while done < total:
        if should_stop is not None and should_stop():
            break
        page = corpus.passages_missing_vector(model, limit=min(PAGE, total - done), sources=sources)
        if not page:
            break
        with corpus.batch():
            for start in range(0, len(page), BATCH):
                chunk = page[start : start + BATCH]
                vectors = embedder.embed([text for _uri, _ordinal, text in chunk])
                for (uri, ordinal, _text), vector in zip(chunk, vectors, strict=True):
                    if dim and len(vector) != dim:
                        raise EmbedError(
                            f"{model} returned {len(vector)} numbers, the locker holds {dim}; "
                            "the model changed. Run `dossier index` after dropping its vectors."
                        )
                    dim = dim or len(vector)
                    corpus.upsert_vector(uri, ordinal, model, vector)
                done += len(chunk)
                if on_batch is not None:
                    on_batch(done, total)
    return corpus.vector_count(model)


def pack_vector(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *[float(value) for value in values])


def unpack_vector(blob: bytes) -> list[float]:
    count = len(blob) // 4
    if count < 1 or len(blob) != count * 4:
        return []
    return list(struct.unpack(f"<{count}f", blob))


def cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right, strict=True):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))
