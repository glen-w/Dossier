"""Presentation of a tailored CV or letter: markdown, HTML, DOCX, or PDF.

A renderer only lays out a `DraftDoc`. It never writes, shortens, or reorders prose.
Every text run it prints is a stored span, an approved claim, a heading taken from the
lens name, the name or contact line from your config, a citation URI, or a fixed label.
`DraftDoc.texts()` lists exactly those, and the tests hold each format to it.
Nothing here touches the network.
"""

from __future__ import annotations

import html
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

FORMATS = ("markdown", "html", "docx", "pdf")
SUFFIX = {"markdown": ".md", "html": ".html", "docx": ".docx", "pdf": ".pdf"}

LABEL_CV = "CV"
LABEL_LETTER = "Letter"
LABEL_NOT_INCLUDED = "Not included"
LABEL_COVERAGE = "Coverage"
LABEL_SOURCES = "Sources"
LABEL_CITATION = "citation: "
LABELS = (
    LABEL_CV,
    LABEL_LETTER,
    LABEL_NOT_INCLUDED,
    LABEL_COVERAGE,
    LABEL_SOURCES,
    LABEL_CITATION.strip(),
)


class RenderError(Exception):
    """A format could not be produced (missing extra, no font)."""


@dataclass(frozen=True)
class Entry:
    """One quoted span, with the claim it carries and the record it came from."""

    claim: str
    span: str
    uri: str = ""


@dataclass(frozen=True)
class Section:
    heading: str
    entries: tuple[Entry, ...]


@dataclass(frozen=True)
class DraftDoc:
    kind: str  # "cv" or "letter"
    name: str = ""
    subtitle: str = ""
    contact: str = ""
    paragraphs: tuple[str, ...] = ()  # letter body: stored spans, or the one glue line
    sections: tuple[Section, ...] = ()  # cv body
    not_included: tuple[tuple[str, str], ...] = ()  # (card id, claim)
    coverage: tuple[str, ...] = ()
    with_sources: bool = False

    @property
    def title(self) -> str:
        return LABEL_LETTER if self.kind == "letter" else LABEL_CV

    def source_uris(self) -> list[str]:
        seen: list[str] = []
        for section in self.sections:
            for entry in section.entries:
                if entry.uri and entry.uri not in seen:
                    seen.append(entry.uri)
        return seen

    def runs(self) -> list[str]:
        """Every text run, in page order. HTML, DOCX, and PDF print exactly these."""
        out: list[str] = [self.name.strip() or self.title]
        if self.name.strip() and self.kind != "letter" and self.subtitle.strip():
            out.append(self.subtitle.strip())
        if self.contact.strip():
            out.append(self.contact.strip())
        if self.kind == "letter":
            out.extend(self.paragraphs)
        else:
            for section in self.sections:
                out.append(section.heading)
                for entry in section.entries:
                    out.append(entry.claim)
                    out.append(entry.span)
                    if entry.uri:
                        out.append(LABEL_CITATION + entry.uri)
        if self.not_included:
            out.append(LABEL_NOT_INCLUDED)
            out.extend(f"{cid}: {claim}" for cid, claim in self.not_included)
        out.append(LABEL_COVERAGE)
        out.extend(line for line in self.coverage if line.strip())
        if self.with_sources:
            out.append(LABEL_SOURCES)
            out.extend(self.source_uris())
        return out

    def texts(self) -> set[str]:
        """Every string a rendering may print. Nothing else is allowed on the page."""
        out: set[str] = set(LABELS)
        out.update(
            part.strip() for part in (self.name, self.subtitle, self.contact) if part.strip()
        )
        out.update(p.strip() for p in self.paragraphs if p.strip())
        for section in self.sections:
            out.add(section.heading)
            for entry in section.entries:
                out.add(entry.claim.strip())
                out.add(entry.span.strip())
                if entry.uri:
                    out.add(entry.uri)
                    out.add(LABEL_CITATION + entry.uri)
        for card_id, claim in self.not_included:
            out.add(f"{card_id}: {claim}")
            out.add(card_id)
            out.add(claim)
        out.update(line.strip() for line in self.coverage if line.strip())
        return {t for t in out if t}


@dataclass(frozen=True)
class Theme:
    font_pt: int = 10
    margin_mm: int = 18
    page: str = "A4"
    accent: str = "#1f4e79"


# ---------------------------------------------------------------- markdown


def to_markdown(doc: DraftDoc) -> str:
    """The original draft format. Byte for byte what `render_draft` has always written."""
    lines = [f"# {doc.title}", ""]
    if doc.name.strip():
        lines.extend([doc.name.strip(), ""])
    if doc.kind != "letter" and doc.subtitle.strip():
        lines.extend([doc.subtitle.strip(), ""])
    if doc.contact.strip():
        lines.extend([doc.contact.strip(), ""])
    if doc.kind == "letter":
        for paragraph in doc.paragraphs:
            lines.extend([paragraph, ""])
    else:
        for section in doc.sections:
            lines.extend([f"## {section.heading}", ""])
            for entry in section.entries:
                lines.append(f"- {entry.claim}")
                lines.append("")
                lines.append(f"> {entry.span}")
                lines.append("")
                if entry.uri:
                    lines.append(f"{LABEL_CITATION}{entry.uri}")
                    lines.append("")
    if doc.not_included:
        lines.extend([f"# {LABEL_NOT_INCLUDED}", ""])
        for card_id, claim in doc.not_included:
            lines.append(f"- {card_id}: {claim}")
        lines.append("")
    lines.extend([f"# {LABEL_COVERAGE}", ""])
    lines.extend(doc.coverage)
    lines.append("")
    if doc.with_sources:
        lines.extend([f"# {LABEL_SOURCES}", ""])
        lines.extend(f"- {uri}" for uri in doc.source_uris())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# -------------------------------------------------------------------- html

_CSS = """
@page { size: %(page)s; margin: %(margin)dmm; }
body { font-family: "DejaVu Sans", Helvetica, Arial, sans-serif; font-size: %(pt)dpt;
       line-height: 1.4; color: #111; max-width: 46em; margin: 2em auto; }
h1 { font-size: 1.7em; margin: 0 0 .1em; }
h2 { font-size: 1.1em; color: %(accent)s; border-bottom: 1px solid %(accent)s;
     margin: 1.2em 0 .4em; text-transform: capitalize; }
.subtitle { color: #444; margin: 0 0 .2em; }
.contact { color: #444; margin: 0 0 1em; font-size: .9em; }
blockquote { margin: .2em 0 .2em 1em; font-style: italic; }
.claim { font-weight: bold; margin: .6em 0 0; }
.cite { color: #666; font-size: .8em; }
.meta { margin-top: 2em; color: #555; font-size: .85em; }
@media print { body { margin: 0; max-width: none; } .meta { page-break-before: auto; } }
"""


def to_html(doc: DraftDoc, theme: Theme | None = None) -> str:
    theme = theme or Theme()
    e = html.escape
    css = _CSS % {
        "page": theme.page,
        "margin": theme.margin_mm,
        "pt": theme.font_pt,
        "accent": theme.accent,
    }
    out = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>{e(doc.name.strip() or doc.title)}</title>",
        f"<style>{css}</style></head><body>",
    ]
    heading = doc.name.strip() or doc.title
    out.append(f"<h1>{e(heading)}</h1>")
    if doc.name.strip() and doc.kind != "letter" and doc.subtitle.strip():
        out.append(f'<p class="subtitle">{e(doc.subtitle.strip())}</p>')
    if doc.contact.strip():
        out.append(f'<p class="contact">{e(doc.contact.strip())}</p>')
    if doc.kind == "letter":
        out.extend(f"<p>{e(p)}</p>" for p in doc.paragraphs)
    else:
        for section in doc.sections:
            out.append(f"<h2>{e(section.heading)}</h2>")
            for entry in section.entries:
                out.append(f'<p class="claim">{e(entry.claim)}</p>')
                out.append(f"<blockquote>{e(entry.span)}</blockquote>")
                if entry.uri:
                    out.append(f'<p class="cite">{e(LABEL_CITATION + entry.uri)}</p>')
    out.append('<div class="meta">')
    if doc.not_included:
        out.append(f"<h2>{e(LABEL_NOT_INCLUDED)}</h2><ul>")
        out.extend(f"<li>{e(f'{cid}: {claim}')}</li>" for cid, claim in doc.not_included)
        out.append("</ul>")
    out.append(f"<h2>{e(LABEL_COVERAGE)}</h2>")
    out.extend(f"<p>{e(line)}</p>" for line in doc.coverage if line.strip())
    if doc.with_sources:
        out.append(f"<h2>{e(LABEL_SOURCES)}</h2><ul>")
        out.extend(f"<li>{e(uri)}</li>" for uri in doc.source_uris())
        out.append("</ul>")
    out.append("</div></body></html>")
    return "\n".join(out) + "\n"


# -------------------------------------------------------------------- docx

_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    "</Types>"
)
_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/></Relationships>'
)
_DOC_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
    'Target="styles.xml"/></Relationships>'
)


def _styles(theme: Theme) -> str:
    half_points = theme.font_pt * 2
    accent = theme.accent.lstrip("#")

    def style(sid: str, name: str, *, size: int, bold: bool = False, italic: bool = False,
              color: str = "", before: int = 0, after: int = 80, indent: int = 0) -> str:
        rpr = f'<w:sz w:val="{size}"/>'
        if bold:
            rpr = "<w:b/>" + rpr
        if italic:
            rpr = "<w:i/>" + rpr
        if color:
            rpr += f'<w:color w:val="{color}"/>'
        ppr = f'<w:spacing w:before="{before}" w:after="{after}"/>'
        if indent:
            ppr += f'<w:ind w:left="{indent}"/>'
        return (
            f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/>'
            f"<w:basedOn w:val=\"Normal\"/><w:pPr>{ppr}</w:pPr><w:rPr>{rpr}</w:rPr></w:style>"
        )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{_NS}">'
        '<w:docDefaults><w:rPrDefault><w:rPr>'
        '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>'
        f'<w:sz w:val="{half_points}"/></w:rPr></w:rPrDefault></w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
        + style("Title", "Title", size=half_points * 2 - 4, bold=True, after=40)
        + style("Heading2", "heading 2", size=half_points + 4, bold=True, color=accent, before=240)
        + style("Quote", "Quote", size=half_points, italic=True, indent=360)
        + style("Claim", "Claim", size=half_points, bold=True, before=120, after=20)
        + style("Cite", "Cite", size=max(half_points - 4, 12), color="666666", indent=360)
        + style("Muted", "Muted", size=max(half_points - 2, 14), color="444444")
        + "</w:styles>"
    )


def _w_para(text: str, style: str = "") -> str:
    esc = html.escape(text, quote=False)
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{esc}</w:t></w:r></w:p>'


def to_docx(doc: DraftDoc, theme: Theme | None = None) -> bytes:
    theme = theme or Theme()
    paras: list[str] = []
    paras.append(_w_para(doc.name.strip() or doc.title, "Title"))
    if doc.name.strip() and doc.kind != "letter" and doc.subtitle.strip():
        paras.append(_w_para(doc.subtitle.strip(), "Muted"))
    if doc.contact.strip():
        paras.append(_w_para(doc.contact.strip(), "Muted"))
    if doc.kind == "letter":
        paras.extend(_w_para(p) for p in doc.paragraphs)
    else:
        for section in doc.sections:
            paras.append(_w_para(section.heading, "Heading2"))
            for entry in section.entries:
                paras.append(_w_para(entry.claim, "Claim"))
                paras.append(_w_para(entry.span, "Quote"))
                if entry.uri:
                    paras.append(_w_para(LABEL_CITATION + entry.uri, "Cite"))
    if doc.not_included:
        paras.append(_w_para(LABEL_NOT_INCLUDED, "Heading2"))
        paras.extend(_w_para(f"{cid}: {claim}", "Muted") for cid, claim in doc.not_included)
    paras.append(_w_para(LABEL_COVERAGE, "Heading2"))
    paras.extend(_w_para(line, "Muted") for line in doc.coverage if line.strip())
    if doc.with_sources:
        paras.append(_w_para(LABEL_SOURCES, "Heading2"))
        paras.extend(_w_para(uri, "Muted") for uri in doc.source_uris())
    margin = int(theme.margin_mm * 56.7)
    width, height = (11906, 16838) if theme.page.upper() == "A4" else (12240, 15840)
    body = (
        "".join(paras)
        + f'<w:sectPr><w:pgSz w:w="{width}" w:h="{height}"/>'
        f'<w:pgMar w:top="{margin}" w:right="{margin}" w:bottom="{margin}" w:left="{margin}" '
        'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_NS}"><w:body>{body}</w:body></w:document>'
    )
    buf = BytesIO()
    fixed = (2020, 1, 1, 0, 0, 0)  # stable bytes for the same document
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in (
            ("[Content_Types].xml", _CONTENT_TYPES),
            ("_rels/.rels", _RELS),
            ("word/_rels/document.xml.rels", _DOC_RELS),
            ("word/document.xml", document),
            ("word/styles.xml", _styles(theme)),
        ):
            info = zipfile.ZipInfo(name, date_time=fixed)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data.encode("utf-8"))
    return buf.getvalue()


# --------------------------------------------------------------------- pdf

_FONT_DIR = Path(__file__).resolve().parent / "fonts"


def to_pdf(doc: DraftDoc, theme: Theme | None = None) -> bytes:
    """A PDF through `fpdf2` (the `render` extra) and the bundled DejaVu Sans."""
    theme = theme or Theme()
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise RenderError("PDF needs the render extra: uv sync --extra render") from exc
    regular = _FONT_DIR / "DejaVuSans.ttf"
    bold = _FONT_DIR / "DejaVuSans-Bold.ttf"
    italic = _FONT_DIR / "DejaVuSans-Oblique.ttf"
    if not (regular.is_file() and bold.is_file() and italic.is_file()):
        raise RenderError("bundled fonts are missing from this install")

    pdf = FPDF(format=theme.page.upper() if theme.page.upper() in {"A4", "LETTER"} else "A4")
    pdf.set_margins(theme.margin_mm, theme.margin_mm, theme.margin_mm)
    pdf.set_auto_page_break(auto=True, margin=theme.margin_mm)
    pdf.set_creator("Dossier")
    pdf.set_creation_date(datetime(2020, 1, 1, tzinfo=UTC))
    pdf.add_font("DejaVu", "", str(regular))
    pdf.add_font("DejaVu", "B", str(bold))
    pdf.add_font("DejaVu", "I", str(italic))
    pdf.add_page()
    accent = _rgb(theme.accent)
    size = theme.font_pt
    line = size * 0.5  # mm per line of text

    def write(text: str, *, style: str = "", pt: float = size, color=(17, 17, 17),
              indent: float = 0, before: float = 0, after: float = 1.2) -> None:
        pdf.set_font("DejaVu", style, pt)
        pdf.set_text_color(*color)
        if before:
            pdf.ln(before)
        pdf.set_x(pdf.l_margin + indent)
        pdf.multi_cell(
            pdf.w - pdf.l_margin - pdf.r_margin - indent,
            line * pt / size,
            text,
            new_x="LMARGIN",
            new_y="NEXT",
        )
        if after:
            pdf.ln(after)

    write(doc.name.strip() or doc.title, style="B", pt=size * 1.9, after=0.6)
    if doc.name.strip() and doc.kind != "letter" and doc.subtitle.strip():
        write(doc.subtitle.strip(), pt=size, color=(68, 68, 68), after=0.4)
    if doc.contact.strip():
        write(doc.contact.strip(), pt=size * 0.9, color=(68, 68, 68), after=2)
    if doc.kind == "letter":
        for paragraph in doc.paragraphs:
            write(paragraph, after=2.5)
    else:
        for section in doc.sections:
            write(section.heading, style="B", pt=size * 1.15, color=accent, before=3, after=1)
            for entry in section.entries:
                write(entry.claim, style="B", before=1, after=0.4)
                write(entry.span, style="I", indent=4, after=0.4)
                if entry.uri:
                    write(LABEL_CITATION + entry.uri, pt=size * 0.8, color=(102, 102, 102),
                          indent=4, after=1.4)
    if doc.not_included:
        write(LABEL_NOT_INCLUDED, style="B", pt=size * 1.15, color=accent, before=4, after=1)
        for cid, claim in doc.not_included:
            write(f"{cid}: {claim}", pt=size * 0.9, color=(68, 68, 68), after=0.6)
    write(LABEL_COVERAGE, style="B", pt=size * 1.15, color=accent, before=4, after=1)
    for text in doc.coverage:
        if text.strip():
            write(text, pt=size * 0.9, color=(68, 68, 68), after=0.6)
    if doc.with_sources:
        write(LABEL_SOURCES, style="B", pt=size * 1.15, color=accent, before=4, after=1)
        for uri in doc.source_uris():
            write(uri, pt=size * 0.9, color=(68, 68, 68), after=0.6)
    return bytes(pdf.output())


def _rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    if len(raw) != 6:
        return (31, 78, 121)
    try:
        return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
    except ValueError:
        return (31, 78, 121)


# ---------------------------------------------------------------- dispatch


def render_bytes(doc: DraftDoc, fmt: str, theme: Theme | None = None) -> bytes:
    if fmt == "markdown":
        return to_markdown(doc).encode("utf-8")
    if fmt == "html":
        return to_html(doc, theme).encode("utf-8")
    if fmt == "docx":
        return to_docx(doc, theme)
    if fmt == "pdf":
        return to_pdf(doc, theme)
    raise RenderError(f"unknown format {fmt!r}; choose one of {', '.join(FORMATS)}")


def write_render(doc: DraftDoc, fmt: str, directory: Path, theme: Theme | None = None) -> Path:
    """Write a rendering next to the markdown drafts. Gitignored by suffix and folder."""
    data = render_bytes(doc, fmt, theme)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%y%m%d-%H%M%S")
    path = directory / f"{stamp}{SUFFIX[fmt]}"
    if path.exists():
        path = directory / f"{datetime.now(UTC).strftime('%y%m%d-%H%M%S-%f')}{SUFFIX[fmt]}"
    path.write_bytes(data)
    return path

