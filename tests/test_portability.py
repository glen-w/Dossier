from pathlib import Path

from dossier.cards import STATUS_APPROVED, ClaimCard
from dossier.cli import main
from dossier.portability import export_locker, import_locker
from dossier.store import Corpus, Record


def test_export_import_round_trip(corpus: Corpus, tmp_path: Path) -> None:
    corpus.upsert_record(
        Record(
            id="r1",
            source="slack",
            uri="slack://1",
            title="Note",
            text="Quinn wrote a synthetic paper on coastal governance.",
        )
    )
    corpus.put_card(
        ClaimCard(
            id="c1",
            claim="synthetic paper on coastal governance",
            citations=["slack://1"],
            source="slack",
            status=STATUS_APPROVED,
            extras={"span": "Quinn wrote a synthetic paper on coastal governance."},
        )
    )
    dest = tmp_path / "locker.json"
    export_locker(corpus, dest)
    other = Corpus(tmp_path / "other.db")
    n = import_locker(other, dest)
    assert n == 1
    loaded = other.get_card("c1")
    assert loaded is not None
    assert loaded.extras["span"].startswith("Quinn wrote")
    other.close()


def test_cli_eval_and_packet(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    corpus = Corpus(tmp_path / "evidence.db")
    corpus.upsert_record(
        Record(
            id="r1",
            source="slack",
            uri="eval://coastal",
            title="Note",
            text="Quinn wrote a synthetic paper on coastal governance.",
        )
    )
    corpus.close()
    assert main(["eval"]) == 0
    out = capsys.readouterr().out
    assert "eval:" in out
    assert main(["packet"]) == 0
    packet = capsys.readouterr().out.strip()
    assert packet.endswith(".md")
