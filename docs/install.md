# Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```text
uv sync --extra dev
uv run dossier --help
uv run dossier doctor
```

## Full text (FTS5)

`dossier ask` prefers SQLite FTS5 on title, text, and passages. Whole-word
overlap is the fallback when this interpreter was built without the module.

`dossier doctor` prints:

- `python:` — the executable in use
- `sqlite:` — SQLite version
- `fts5: yes|no`

Prefer an interpreter that reports `fts5: yes`. On this Mac the stock
`uv` venv may report `fts5: no` while Homebrew Python 3.13 reports yes:

```text
UV_PYTHON=/opt/homebrew/opt/python@3.13/bin/python3.13 uv sync --extra dev
uv run dossier doctor
```

Do not vendor SQLite into this repo. `dossier prove` exits non-zero when
FTS5 is missing unless you pass `--allow-overlap`.

## Model

The default model is Ollama at `http://127.0.0.1:11434`. Set
`DOSSIER_LLM_PROVIDER=off` to skip model calls. `dossier ask --mode exact`
still quotes from the corpus. An OpenAI-compatible API is opt-in
(`DOSSIER_LLM_PROVIDER=litellm`, plus `dossier[llm]`). If a completion can
leave the machine, the CLI prints an egress notice before it runs.

Copy `dossier.example.toml` to `$DOSSIER_DATA/dossier.toml` to change
defaults; environment variables win.

## Docs site (optional)

```text
uv sync --extra docs
make docs
make pages-site
```

Open `_site/index.html` for the product page and `_site/guide/` for this
guide.
