# Install

Type: GUIDE
Authority: How to install and which interpreter has FTS5. Command behavior lives in [status](status.md).

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/) on the machine that holds the folders. There is no container image. See [Where it runs](#where-it-runs).

```text
uv sync --extra dev
uv sync --extra web   # optional workbench (dossier gui)
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
- `egress:` — `no` until a remote LLM is opted in; a blocked non-loopback Ollama URL stays `egress: no` (no remote notice)
- `embed_model:` and `vectors:` — passage vectors from `dossier index`
- `employer_paths:` and `git_paths:` — how many folders you listed
- `tailor:` — how many spanned approved cards a posting draft can quote. What that draft contains is in [status](status.md).
- Warnings when Slack or meetings detect but identity is empty, when a pubs collection is set but `rows=0`, or when mbox records cite hard-closed folders (`mbox_sent_metadata`)

Invalid `$DOSSIER_DATA/dossier.toml` fails the process with exit code 2 (`FAIL:` on stderr) instead of silently using empty config.

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

Publications come from the Zotero collection named under `[pubs]` in `data/dossier.toml`. This repo does not start another service. See [Publications index](zotero-rag-pubs.md).

## Model

The default model is Ollama at `http://127.0.0.1:11434` with `allow_remote = false`. Completions are unlimited unless `DOSSIER_LLM_MAX_CALLS` (or `[llm] max_calls`) is a positive cap. Set `DOSSIER_LLM_PROVIDER=off` to skip model calls. `dossier ask --mode exact` still quotes from the corpus.

Text leaves the machine only if you opt into a remote LLM. That is `DOSSIER_LLM_PROVIDER=litellm` (plus `dossier[llm]`), or `DOSSIER_LLM_ALLOW_REMOTE=true` so Ollama may use a non-loopback host. The prompt for that call is what is sent. The corpus file is not. The CLI prints an egress notice first. A remote Ollama URL without the flag is refused and does not print that notice. `dossier doctor` prints `egress: no` until you opt in (including `egress: no (remote URL blocked…)` when the URL is non-loopback without the flag).

Copy `dossier.example.toml` to `$DOSSIER_DATA/dossier.toml` to change
defaults; environment variables win. Bad TOML fails load (exit 2).

## Docs site (optional)

```text
uv sync --extra docs
make docs
make pages-site
```

Open `_site/index.html` for the product page and `_site/guide/` for this
guide.
