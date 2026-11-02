from __future__ import annotations

import json
from pathlib import Path

from dossier.cli import main
from dossier.eval import default_set, run_eval
from dossier.store import Corpus


def test_bundled_set_is_wide_and_passes(corpus: Corpus) -> None:
    spec = default_set()
    assert len(spec["cases"]) >= 50
    refusals = [case for case in spec["cases"] if case.get("refuse")]
    answers = [case for case in spec["cases"] if case.get("refuse") is False]
    assert len(refusals) >= 15
    assert len(answers) >= 15
    report = run_eval(corpus)
    assert report.ok, str(report)
    assert report.passed == report.total


def test_bundled_eval_leaves_the_given_locker_alone(corpus: Corpus) -> None:
    run_eval(corpus)
    assert corpus.records() == []
    assert corpus.cards() == []


def test_known_gaps_are_reported_not_hidden(corpus: Corpus) -> None:
    report = run_eval(corpus)
    assert report.gaps
    assert "known gap" in str(report)


def test_a_wrong_expectation_fails(corpus: Corpus, tmp_path: Path) -> None:
    spec = default_set()
    spec["cases"] = [{"question": "commanded a lunar base", "refuse": False}]
    path = tmp_path / "set.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    report = run_eval(corpus, path=path)
    assert not report.ok
    assert "refused" in report.failed[0]


def test_forbidden_citation_fails(corpus: Corpus, tmp_path: Path) -> None:
    spec = default_set()
    spec["cases"] = [
        {
            "question": "synthetic paper on coastal governance",
            "refuse": False,
            "forbid_citations": ["eval://coastal"],
        }
    ]
    path = tmp_path / "set.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    report = run_eval(corpus, path=path)
    assert not report.ok
    assert "forbidden" in report.failed[0]


def test_injection_text_in_a_record_does_not_redirect_the_citation(corpus: Corpus) -> None:
    spec = default_set()
    case = next(c for c in spec["cases"] if c["question"] == "tidal marshes survey")
    assert case["forbid_citations"] == ["eval://secret"]
    assert run_eval(corpus).ok


def test_cli_eval_exit_code_follows_the_report(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    assert main(["eval"]) == 0
    assert "eval: " in capsys.readouterr().out
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "records": [{"uri": "x://1", "text": "Quinn wrote a coastal paper."}],
                "cards": [],
                "cases": [{"question": "quantum lattice", "refuse": False}],
            }
        ),
        encoding="utf-8",
    )
    assert main(["eval", "--path", str(bad)]) == 1
