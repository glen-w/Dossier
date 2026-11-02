"""Synthetic golden set for ask refusals and citations. No personal corpus.

The bundled set is self-contained: it carries its own records and cards and runs
against a throwaway locker, so `dossier eval` never reads or changes yours.
A custom set may be a bare list of cases; those run against the locker you pass.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dossier.cards import STATUS_APPROVED, ClaimCard, card_id, span_max
from dossier.interview import conduct
from dossier.llm.client import NullLLMClient
from dossier.store import Corpus, Record

BUNDLED = Path(__file__).resolve().parent / "eval_set.json"


@dataclass(frozen=True)
class EvalReport:
    total: int
    passed: int
    failed: tuple[str, ...]
    gaps: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.failed

    def __str__(self) -> str:
        lines = [f"eval: {self.passed}/{self.total}"]
        for item in self.failed:
            lines.append(f"fail {item}")
        for item in self.gaps:
            lines.append(f"known gap {item}")
        return "\n".join(lines)


class ExactConfig:
    """Config for exact-mode ask. No model, no network."""

    ask_mode = "exact"
    ask_limit = 5
    ask_fts = True
    ask_cards_first = True
    ask_passages = True
    ask_hops = 0
    ask_decompose = "auto"
    ask_planner = "off"
    ask_embed = False
    ask_pubs = False
    lexicon = None
    llm_enabled = False
    embed_model = "nomic-embed-text"


def default_set() -> dict[str, Any]:
    """The bundled golden set: records, cards, and cases."""
    if BUNDLED.is_file():
        data = json.loads(BUNDLED.read_text(encoding="utf-8"))
        if isinstance(data, (dict, list)):
            return _normalise(data)
    return _normalise(_builtin())


def _normalise(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        return {"records": [], "cards": [], "cases": data}
    cases = data.get("cases")
    return {
        "records": list(data.get("records") or []),
        "cards": list(data.get("cards") or []),
        "cases": cases if isinstance(cases, list) else [],
    }


def seed_corpus(corpus: Corpus, spec: dict[str, Any] | None = None) -> None:
    """Load the set's records and approved cards (with stored spans) into a locker."""
    spec = spec or _normalise(_builtin())
    for row in spec["records"]:
        corpus.upsert_record(
            Record(
                id=str(row["uri"]),
                source=str(row.get("source") or "slack"),
                uri=str(row["uri"]),
                title=str(row.get("title") or "Note"),
                text=str(row["text"]),
            )
        )
    for row in spec["cards"]:
        claim = str(row["claim"])
        uri = str(row["uri"])
        extras = {"span": str(row["span"]), "span_uri": uri} if row.get("span") else {}
        corpus.put_card(
            ClaimCard(
                id=card_id(claim, [uri]),
                claim=claim,
                citations=[uri],
                source=str(row.get("source") or "slack"),
                status=str(row.get("status") or STATUS_APPROVED),
                extras=extras,
            )
        )


def run_eval(corpus: Corpus, *, path: Path | None = None) -> EvalReport:
    if path:
        spec = _normalise(json.loads(path.read_text(encoding="utf-8")))
    else:
        spec = default_set()
    if spec["records"]:
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Corpus(Path(tmp) / "eval.db")
            try:
                seed_corpus(scratch, spec)
                return _run(scratch, spec["cases"])
            finally:
                scratch.close()
    if not corpus.records():
        seed_corpus(corpus)
    return _run(corpus, spec["cases"])


def _run(corpus: Corpus, cases: list[Any]) -> EvalReport:
    known = {rec.uri for rec in corpus.records()}
    client = NullLLMClient()
    failed: list[str] = []
    gaps: list[str] = []
    passed = 0
    scored = 0
    for case in cases:
        if not isinstance(case, dict):
            continue
        scored += 1
        question = str(case.get("question") or "")
        problem = _check(corpus, case, question, known, client)
        label = f"{question or '(empty)'!r}: {problem}"
        if not problem:
            passed += 1
        elif case.get("known_gap"):
            # Documented leniency: reported every run, never silently dropped.
            gaps.append(label)
            passed += 1
        else:
            failed.append(label)
    return EvalReport(total=scored, passed=passed, failed=tuple(failed), gaps=tuple(gaps))


def _check(
    corpus: Corpus,
    case: dict[str, Any],
    question: str,
    known: set[str],
    client: NullLLMClient,
) -> str:
    """Empty string when the case holds, otherwise what went wrong."""
    try:
        answer = conduct(corpus, question, ExactConfig(), client, mode="exact", limit=5)
    except Exception as exc:  # a crash is a failed case, never an eval abort
        return f"raised {type(exc).__name__}"
    known_uris = known
    if answer.refused and answer.citations:
        # Only a partial compound answer may name records, and only real ones.
        if answer.reason != "incomplete":
            return "refusal carries citations"
        if not set(answer.citations) <= known_uris:
            return "partial answer cites a record outside the corpus"
    if not answer.refused:
        cited = set(answer.citations)
        if not cited:
            return "answer has no citation"
        if not cited <= known:
            return f"citation outside the corpus: {sorted(cited - known)}"
        limit = int(case.get("max_len") or span_max() * 4)
        if len(answer.text) > limit:
            return f"answer is {len(answer.text)} characters"
        banned = set(case.get("forbid_citations") or [])
        if cited & banned:
            return f"cited a forbidden record: {sorted(cited & banned)}"
    expect = case.get("refuse")
    if expect is not None and answer.refused != bool(expect):
        return "answered" if not answer.refused else "refused"
    if not answer.refused:
        expected = set(case.get("citations") or [])
        if expected and not expected <= set(answer.citations):
            return f"missing citations {sorted(expected - set(answer.citations))}"
    return ""


def _builtin() -> dict[str, Any]:
    return {
        "records": [
            {
                "uri": "eval://coastal",
                "text": (
                    "Lens: delivered\nKind: chapter\n"
                    "Quinn wrote a synthetic paper on coastal governance."
                ),
            }
        ],
        "cards": [
            {
                "claim": "synthetic paper on coastal governance",
                "uri": "eval://coastal",
                "span": "Quinn wrote a synthetic paper on coastal governance.",
            }
        ],
        "cases": [
            {
                "question": "synthetic paper on coastal governance",
                "refuse": False,
                "citations": ["eval://coastal"],
            },
            {"question": "", "refuse": True},
            {"question": "commanded a lunar base", "refuse": True},
        ],
    }


@dataclass(frozen=True)
class RetrievalReport:
    """Recall@k and mean reciprocal rank per retrieval route on a synthetic locker."""

    queries: int
    k: int
    recall: dict[str, float]
    mrr: dict[str, float]

    def __str__(self) -> str:
        lines = [f"retrieval: {self.queries} queries, k={self.k}"]
        for route in self.recall:
            lines.append(
                f"{route}: recall@{self.k} {self.recall[route]:.2f}  mrr {self.mrr[route]:.2f}"
            )
        return "\n".join(lines)


def retrieval_metrics(*, n: int = 40, k: int = 3, seed: int = 11) -> RetrievalReport:
    """Measure lexical, vector, and fused retrieval on generated records.

    Each record carries three words no other record has. A query uses two of them
    plus a filler word every record shares. The vector route uses the hash embedder,
    so this runs anywhere with no model. It checks the machinery, not a real model.
    """
    import random

    from dossier.ask import Hit, _fuse, collect_hits
    from dossier.embed import HashEmbedder, index_passages

    rng = random.Random(seed)
    syllables = ["bar", "kel", "mor", "tin", "vex", "lum", "dor", "pax", "ryn", "sul"]

    def word() -> str:
        return "".join(rng.choice(syllables) for _ in range(3))

    used: set[str] = set()

    def fresh() -> str:
        while True:
            candidate = word()
            if candidate not in used:
                used.add(candidate)
                return candidate

    rows = [[fresh() for _ in range(3)] for _ in range(n)]
    embedder = HashEmbedder()
    with tempfile.TemporaryDirectory() as tmp:
        corpus = Corpus(Path(tmp) / "retrieval.db")
        try:
            for index, words in enumerate(rows):
                corpus.upsert_record(
                    Record(
                        id=f"g{index}",
                        source="slack",
                        uri=f"gen://{index}",
                        title=f"Note {index}",
                        text=f"Quinn reported on {words[0]} and {words[1]} with {words[2]} work.",
                    )
                )
            index_passages(corpus, embedder)
            cfg = ExactConfig()
            ranks: dict[str, list[int | None]] = {"lexical": [], "vector": [], "fused": []}
            for index, words in enumerate(rows):
                pair = rng.sample(words, 2)
                question = f"{pair[0]} {pair[1]} work"
                target = f"gen://{index}"
                lexical = collect_hits(corpus, question, cfg, limit=k * 3)
                found = corpus.nearest_passages(embedder.embed([question])[0], embedder.model, limit=k * 3)
                vector = [Hit(uri, "", text, 1, cosine=score) for uri, text, score in found]
                fused = _fuse(lexical, vector, k * 3) if lexical and vector else (lexical or vector)
                for route, hits in (("lexical", lexical), ("vector", vector), ("fused", fused)):
                    uris = [hit.uri for hit in hits]
                    ranks[route].append(uris.index(target) + 1 if target in uris else None)
        finally:
            corpus.close()
    recall = {r: sum(1 for x in v if x is not None and x <= k) / len(v) for r, v in ranks.items()}
    mrr = {r: sum(1 / x for x in v if x) / len(v) for r, v in ranks.items()}
    return RetrievalReport(queries=n, k=k, recall=recall, mrr=mrr)
