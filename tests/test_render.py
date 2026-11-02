"""The renderer lays out stored spans. It never adds, trims, or reorders prose."""

from __future__ import annotations

import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

import pytest

from dossier.cards import STATUS_APPROVED, ClaimCard
from dossier.cli import main
from dossier.office import extract_office
from dossier.render import (
    FORMATS,
    DraftDoc,
    Entry,
    RenderError,
    Section,
    Theme,
    render_bytes,
    to_docx,
    to_html,
    to_markdown,
    write_render,
)
from dossier.store import Corpus, Record
from dossier.tailor import Picked, build_doc, render_draft

SPAN_A = "Quinn wrote a “synthetic” paper on coastal governance — with José Álvarez."
SPAN_B = "Quinn convened a workshop on kelp restoration in 2021 & invited six harbour towns <all>."
LONG = ("Quinn " + "mapped tidal marshes across the estuary " * 5).strip() + "."


def _picked(claim: str, span: str, lens: str, uri: str) -> Picked:
    card = ClaimCard(
        id=f"id-{abs(hash(claim)) % 999}",
        claim=claim,
        citations=[uri],
        source="slack",
        status=STATUS_APPROVED,
        extras={"span": span, "span_uri": uri, "lens": lens},
    )
    return Picked(card, lens, "chapter", 3)


def _cv() -> DraftDoc:
    picked = [
        _picked("synthetic paper on coastal governance", SPAN_A, "delivered", "slack://1"),
        _picked("workshop on kelp restoration", SPAN_B, "delivered", "slack://2"),
        _picked("mapped tidal marshes", LONG, "skills", "slack://3"),
    ]
    bare = [
        ClaimCard(
            id="bare1", claim="Convened a forum", citations=["slack://9"], source="slack",
            status=STATUS_APPROVED,
        )
    ]
    return build_doc(
        kind="cv",
        posting="We need a workshop and a paper on ocean methods.",
        picked=picked,
        bare=bare,
        name="Quinn Ünal",
        subtitle="Policy researcher",
        contact="quinn@example.org · +00 000",
        with_sources=True,
    )


def _letter() -> DraftDoc:
    picked = [_picked("synthetic paper", SPAN_A, "delivered", "slack://1")]
    return build_doc(
        kind="letter",
        posting="A paper.",
        picked=picked,
        bare=[],
        name="Quinn",
        paragraphs=[SPAN_A, "I am applying for the role in the posting."],
    )


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text)


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.runs: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"style", "title"}:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in {"style", "title"}:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.runs.append(data.strip())


def test_markdown_is_byte_identical_to_the_draft_format() -> None:
    picked = [_picked("synthetic paper on coastal governance", SPAN_A, "delivered", "slack://1")]
    posting = "A paper on coastal governance."
    old = render_draft(kind="cv", posting=posting, picked=picked, bare=[], name="Q", subtitle="S")
    doc = build_doc(kind="cv", posting=posting, picked=picked, bare=[], name="Q", subtitle="S")
    assert to_markdown(doc) == old
    assert f"> {SPAN_A}" in old and "# Coverage" in old


@pytest.mark.parametrize("make", [_cv, _letter])
def test_html_prints_exactly_the_runs(make) -> None:
    doc = make()
    parser = _Text()
    parser.feed(to_html(doc))
    assert parser.runs == [run.strip() for run in doc.runs()]


@pytest.mark.parametrize("make", [_cv, _letter])
def test_docx_prints_exactly_the_runs(make, tmp_path: Path) -> None:
    doc = make()
    data = to_docx(doc)
    path = tmp_path / "out.docx"
    path.write_bytes(data)
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        root = ElementTree.fromstring(archive.read("word/document.xml"))
        styles = ElementTree.fromstring(archive.read("word/styles.xml"))
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    runs = [node.text or "" for node in root.iter(f"{ns}t")]
    assert runs == doc.runs()
    assert styles is not None
    text, err = extract_office(path)
    assert err == ""
    assert _norm(text) == _norm("".join(doc.runs()))


def test_docx_bytes_are_stable() -> None:
    assert to_docx(_cv()) == to_docx(_cv())


@pytest.mark.parametrize("make", [_cv, _letter])
def test_pdf_prints_exactly_the_runs(make, tmp_path: Path) -> None:
    pytest.importorskip("fpdf")
    pypdf = pytest.importorskip("pypdf")
    doc = make()
    path = tmp_path / "out.pdf"
    path.write_bytes(render_bytes(doc, "pdf"))
    reader = pypdf.PdfReader(str(path))
    extracted = "".join(page.extract_text() or "" for page in reader.pages)
    assert _norm(extracted) == _norm("".join(doc.runs()))
    assert len(reader.pages) >= 1


def test_pdf_keeps_curly_quotes_and_accents(tmp_path: Path) -> None:
    pytest.importorskip("fpdf")
    pypdf = pytest.importorskip("pypdf")
    path = tmp_path / "u.pdf"
    path.write_bytes(render_bytes(_cv(), "pdf"))
    text = "".join(page.extract_text() or "" for page in pypdf.PdfReader(str(path)).pages)
    for needle in ("“synthetic”", "José", "Álvarez", "Ünal", "—"):
        assert needle in text


def test_every_run_is_an_allowed_text() -> None:
    for doc in (_cv(), _letter()):
        allowed = doc.texts()
        for run in doc.runs():
            assert run.strip() in allowed, run


def test_a_long_cv_flows_to_more_pages(tmp_path: Path) -> None:
    pytest.importorskip("fpdf")
    pypdf = pytest.importorskip("pypdf")
    picked = [
        _picked(f"claim number {i}", f"Quinn did synthetic thing number {i} on the harbour.", "delivered", f"slack://{i}")
        for i in range(60)
    ]
    doc = build_doc(kind="cv", posting="x", picked=picked, bare=[], name="Q")
    path = tmp_path / "long.pdf"
    path.write_bytes(render_bytes(doc, "pdf"))
    assert len(pypdf.PdfReader(str(path)).pages) >= 3


def test_theme_changes_layout_not_text() -> None:
    doc = _cv()
    plain = to_html(doc, Theme())
    big = to_html(doc, Theme(font_pt=13, margin_mm=30, page="LETTER", accent="#aa0000"))
    assert plain != big
    one, two = _Text(), _Text()
    one.feed(plain)
    two.feed(big)
    assert one.runs == two.runs


def test_unknown_format_is_an_error() -> None:
    with pytest.raises(RenderError):
        render_bytes(_cv(), "rtf")
    assert set(FORMATS) == {"markdown", "html", "docx", "pdf"}


def test_write_render_names_files_by_format(tmp_path: Path) -> None:
    doc = _cv()
    for fmt, suffix in (("markdown", ".md"), ("html", ".html"), ("docx", ".docx")):
        path = write_render(doc, fmt, tmp_path)
        assert path.suffix == suffix and path.is_file()


def test_entries_and_sections_are_plain_data() -> None:
    entry = Entry(claim="c", span="s", uri="u")
    doc = DraftDoc(kind="cv", sections=(Section("h", (entry,)),))
    assert doc.source_uris() == ["u"]
    assert doc.title == "CV"


def _seed_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    corpus = Corpus(tmp_path / "evidence.db")
    corpus.upsert_record(
        Record(
            id="r1",
            source="slack",
            uri="slack://1",
            title="Note",
            text="Lens: delivered\nKind: workshop\nDrafted the ocean workshop briefing.",
        )
    )
    corpus.put_card(
        ClaimCard(
            id="c1",
            claim="Drafted the ocean workshop",
            citations=["slack://1"],
            source="slack",
            status=STATUS_APPROVED,
            extras={
                "span": "Drafted the ocean workshop briefing.",
                "span_uri": "slack://1",
                "lens": "delivered",
                "kind": "workshop",
            },
        )
    )
    corpus.close()
    posting = tmp_path / "posting.txt"
    posting.write_text("We need an ocean workshop.", encoding="utf-8")
    return posting


@pytest.mark.parametrize("fmt", ["html", "docx", "pdf"])
def test_cli_tailor_writes_each_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, fmt: str
) -> None:
    if fmt == "pdf":
        pytest.importorskip("fpdf")
    posting = _seed_cli(tmp_path, monkeypatch)
    code = main(["tailor", "--posting", str(posting), "--format", fmt, "--with-sources"])
    assert code == 0
    written = Path(capsys.readouterr().out.strip().splitlines()[-1])
    assert written.suffix == f".{fmt}"
    assert written.parent == tmp_path / "drafts"
    assert written.stat().st_size > 200


def test_cli_render_reads_contact_from_config(tmp_path: Path, monkeypatch, capsys) -> None:
    posting = _seed_cli(tmp_path, monkeypatch)
    (tmp_path / "dossier.toml").write_text(
        '[tailor]\nname = "Quinn"\n[render]\ncontact = "quinn@example.org"\nfont_pt = 11\n',
        encoding="utf-8",
    )
    assert main(["tailor", "--posting", str(posting), "--format", "html"]) == 0
    written = Path(capsys.readouterr().out.strip().splitlines()[-1])
    page = written.read_text(encoding="utf-8")
    assert "quinn@example.org" in page
    assert "11pt" in page
