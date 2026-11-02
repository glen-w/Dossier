"""Synthetic golden set for ask refusals and citations. No personal corpus."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dossier.cards import STATUS_APPROVED, ClaimCard, card_id
from dossier.interview import conduct
from dossier.llm.client import NullLLMClient
from dossier.store import Corpus, Record

BUNDLED = Path(__file__).resolve().parent / "eval_set.json"


@dataclass(frozen=True)
class EvalReport:
    total: int
    passed: int
    failed: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.failed

    def __str__(self) -> str:
        lines = [f"eval: {self.passed}/{self.total}"]
        for item in self.failed:
            lines.append(f"fail {item}")
        return "\n".join(lines)


def default_set() -> list[dict]:
    if BUNDLED.is_file():
        data = json.loads(BUNDLED.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    return _builtin()


def seed_corpus(corpus: Corpus) -> None:
    rec = Record(
        id="eval-1",
        source="slack",
        uri="eval://coastal",
        title="Coastal note",
        text=(
            "Lens: delivered\nKind: chapter\n"
            "Quinn wrote a synthetic paper on coastal governance."
        ),
    )
    corpus.upsert_record(rec)
    claim = "synthetic paper on coastal governance"
    card = ClaimCard(
        id=card_id(claim, [rec.uri]),
        claim=claim,
        citations=[rec.uri],
        source="slack",
        status=STATUS_APPROVED,
        extras={
            "span": "Quinn wrote a synthetic paper on coastal governance.",
            "span_uri": rec.uri,
        },
    )
    corpus.put_card(card)


def run_eval(corpus: Corpus, *, path: Path | None = None) -> EvalReport:
    cases = json.loads(path.read_text(encoding="utf-8")) if path else default_set()
    if not isinstance(cases, list):
        cases = _builtin()
    if not corpus.records():
        seed_corpus(corpus)
    failed: list[str] = []
    passed = 0
    client = NullLLMClient()

    class _Cfg:
        ask_mode = "exact"
        ask_limit = 5
        ask_fts = True
        ask_cards_first = True
        ask_passages = True
        ask_hops = 0
        ask_decompose = "off"
        ask_planner = "off"
        ask_embed = False
        ask_pubs = False
        lexicon = None
        llm_enabled = False
        embed_model = "nomic-embed-text"

    for case in cases:
        if not isinstance(case, dict):
            continue
        question = str(case.get("question") or "")
        expect_refuse = bool(case.get("refuse"))
        answer = conduct(corpus, question, _Cfg(), client, mode="exact", limit=5)
        ok = answer.refused == expect_refuse
        if ok and not expect_refuse:
            cited = set(answer.citations)
            expected = set(case.get("citations") or [])
            if expected and not expected.issubset(cited):
                ok = False
        if ok:
            passed += 1
        else:
            failed.append(question or "(empty)")
    return EvalReport(total=len(cases), passed=passed, failed=tuple(failed))


def _builtin() -> list[dict]:
    return [
        {
            "question": "synthetic paper on coastal governance",
            "refuse": False,
            "citations": ["eval://coastal"],
        },
        {"question": "", "refuse": True},
        {"question": "commanded a lunar base", "refuse": True},
    ]
