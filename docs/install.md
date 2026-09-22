# Install

Type: GUIDE
Authority: How to install and which interpreter has FTS5. Command behavior lives in [status](status.md).

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/) on the machine that holds the folders. There is no container image. See [Where it runs](#where-it-runs).

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
- `embed_model:` and `vectors:` — passage vectors from `dossier index`
- `employer_paths:` and `git_paths:` — how many folders you listed
- `tailor:` — how many spanned approved cards a posting draft can quote. What that draft contains is in [status](status.md).

Prefer an interpreter that reports `fts5: yes`. On this Mac the stock
`uv` venv may report `fts5: no` while Homebrew Python 3.13 reports yes:

```text
UV_PYTHON=/opt/homebrew/opt/python@3.13/bin/python3.13 uv sync --extra dev
uv run dossier doctor
```

Do not vendor SQLite into this repo. `dossier prove` exits non-zero when
FTS5 is missing unless you pass `--allow-overlap`.

## Where it runs

`uv sync` on the host. The corpus is `data/evidence.db` on that machine. Adapters read paths you list there: an employer folder, a git repo, an export, an mbox, or `DATA_DUMPS_WAREHOUSE`. The default model is Ollama at `http://127.0.0.1:11434`.

A container would need a bind mount for each of those paths and a second route to loopback Ollama. The 1.0 install is this page. FTS5 is the interpreter note above (`UV_PYTHON`), not an image pin. The refuse line is in [roadmap](roadmap.md).

The pubs search server, when you run one, is its own compose project. This repo does not start it. See [Publications index](zotero-rag-pubs.md).

## Model

The default model is Ollama at `http://127.0.0.1:11434`. Completions are
unlimited unless `DOSSIER_LLM_MAX_CALLS` (or `[llm] max_calls`) is a positive
cap. Set `DOSSIER_LLM_PROVIDER=off` to skip model calls. `dossier ask --mode exact`
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
