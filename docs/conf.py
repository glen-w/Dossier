# Sphinx configuration for Dossier hosted docs.
# Build: make docs | uv run sphinx-build -b html docs docs/_build/html

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _release() -> str:
    try:
        from importlib.metadata import version as pkg_version

        return pkg_version("dossier")
    except Exception:
        init = (ROOT / "src" / "dossier" / "__init__.py").read_text(encoding="utf-8")
        match = re.search(r'__version__\s*=\s*"([^"]+)"', init)
        return match.group(1) if match else "dev"


project = "Dossier"
author = "Dossier contributors"
copyright = f"{date.today().year}, {author}"

release = _release()
version = ".".join(str(release).split(".")[:2])

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints",
    "sphinxcontrib.mermaid",
]

templates_path = ["_templates"]
exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

master_doc = "index"

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "replacements",
    "smartquotes",
    "strikethrough",
    "tasklist",
]
myst_heading_anchors = 3
myst_fence_as_directive = ["mermaid"]
suppress_warnings = ["myst.xref_missing", "misc.highlighting_failure"]

html_theme = "furo"
html_title = "Dossier"
html_static_path = ["_static", "../website/chrome"]
html_css_files = ["site_chrome.css"]
html_js_files = ["site_nav.js"]
html_favicon = "favicon.png"
# Light sidebar keeps the ink wordmark. Dark sidebar uses the light wordmark.
html_theme_options = {
    "light_logo": "logo-on-light.png",
    "dark_logo": "logo.png",
}
