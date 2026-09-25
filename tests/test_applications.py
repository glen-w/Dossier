from pathlib import Path

from dossier.sources.applications import ApplicationsSource, applications_max_files
from dossier.store import Corpus


def test_applications_loads_text_and_skips_pdf_body(tmp_path: Path, corpus: Corpus) -> None:
    root = tmp_path / "job applications" / "Oceana"
    root.mkdir(parents=True)
    (root / "cover.md").write_text(
        "Quinn led the Oceana BBNJ working group and wrote this pack.\n",
        encoding="utf-8",
    )
    (root / "cv.pdf").write_bytes(b"%PDF-fake")
    src = ApplicationsSource()
    assert src.detect(tmp_path / "job applications")
    src.load(tmp_path / "job applications", corpus)
    recs = {r.uri: r for r in corpus.records("applications")}
    cover = recs["file://applications/Oceana/cover.md"]
    assert "Oceana BBNJ" in cover.text
    pdf = recs["file://applications/Oceana/cv.pdf"]
    assert "not ingested" in pdf.text
    assert b"%PDF" not in pdf.text.encode()


def test_applications_does_not_claim_random_folders(tmp_path: Path) -> None:
    other = tmp_path / "random-docs"
    other.mkdir()
    (other / "note.md").write_text("hi", encoding="utf-8")
    assert not ApplicationsSource().detect(other)


def test_applications_respects_file_cap(
    tmp_path: Path, corpus: Corpus, monkeypatch, capsys
) -> None:
    root = tmp_path / "job applications" / "pack"
    root.mkdir(parents=True)
    for i in range(5):
        (root / f"note{i}.md").write_text(f"claim {i}\n", encoding="utf-8")
    monkeypatch.setenv("DOSSIER_APPLICATIONS_MAX_FILES", "2")
    assert applications_max_files() == 2
    ApplicationsSource().load(tmp_path / "job applications", corpus)
    assert len(corpus.records("applications")) == 2
    assert "stopped after 2 files" in capsys.readouterr().err
