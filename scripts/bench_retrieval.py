"""Time indexing and ask on a generated locker. Synthetic text only; run it by hand.

    uv run python scripts/bench_retrieval.py --records 20000 --dim 256

Reports build, index, full-text ask, and vector search times for the active vector
backend (`DOSSIER_VEC=python` forces the pure-Python floor).
"""

from __future__ import annotations

import argparse
import random
import tempfile
import time
from pathlib import Path

from dossier.ask import collect_hits
from dossier.embed import HashEmbedder, index_passages
from dossier.eval import ExactConfig
from dossier.store import Corpus, Record
from dossier.vecindex import backend

SYLLABLES = ["bar", "kel", "mor", "tin", "vex", "lum", "dor", "pax", "ryn", "sul"]


def _word(rng: random.Random) -> str:
    return "".join(rng.choice(SYLLABLES) for _ in range(3))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=5000)
    parser.add_argument("--dim", type=int, default=128)
    parser.add_argument("--queries", type=int, default=30)
    args = parser.parse_args()
    rng = random.Random(1)
    with tempfile.TemporaryDirectory() as tmp:
        corpus = Corpus(Path(tmp) / "bench.db")
        try:
            started = time.perf_counter()
            with corpus.batch():
                for index in range(args.records):
                    words = " ".join(_word(rng) for _ in range(30))
                    corpus.upsert_record(
                        Record(
                            id=f"b{index}",
                            source="slack",
                            uri=f"bench://{index}",
                            title=f"Note {index}",
                            text=f"Quinn wrote about {words}. Entry {index} closes here.",
                        )
                    )
            build = time.perf_counter() - started
            embedder = HashEmbedder(dim=args.dim)
            started = time.perf_counter()
            count = index_passages(corpus, embedder)
            index = time.perf_counter() - started
            cfg = ExactConfig()
            questions = [f"{_word(rng)} {_word(rng)} entry" for _ in range(args.queries)]
            started = time.perf_counter()
            for question in questions:
                collect_hits(corpus, question, cfg, limit=5)
            ask = (time.perf_counter() - started) / args.queries
            vectors = [embedder.embed([q])[0] for q in questions]
            started = time.perf_counter()
            for vector in vectors:
                corpus.nearest_passages(vector, embedder.model, limit=5)
            near = (time.perf_counter() - started) / args.queries
        finally:
            corpus.close()
    print(f"backend: {backend().name}")
    print(f"records: {args.records}  vectors: {count}  dim: {args.dim}")
    print(f"build:   {build:.2f}s")
    print(f"index:   {index:.2f}s")
    print(f"ask:     {ask * 1000:.1f} ms/query (full text)")
    print(f"vector:  {near * 1000:.1f} ms/query ({backend().name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
