<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo.png">
    <img src="docs/logo-on-light.png" alt="Dossier" width="280">
  </picture>
</h1>

<p align="center">
  <strong>Local-first locker for professional evidence.</strong><br>
  Records become claim cards you could paste into a CV or letter.
  Each claim cites a record. If the record will not carry the sentence,
  the claim is refused. You approve a card before it is paste-ready.
</p>

Exports, mail, and PDFs stay on your machine. They are not part of this git tree.

## Locker and ask

Ingest an adapter you have. Records land in `data/evidence.db`. Extract drafts a card when the text already carries the sentence, then may ask a local model for the rest. Approve is the human gate. `dossier ask` quotes a cited span, or refuses. `dossier index` can add a passage-vector neighbor when full text misses. What the commands do is in [Status](docs/status.md). The pipeline shape is in [Architecture](docs/architecture.md).

## Warehouse and a thin install

Point `DATA_DUMPS_WAREHOUSE` at an existing DuckDB file when you already have one. LinkedIn, and the warehouse paths for ChatGPT, Slack, and mail, read that file. They do not build it.

A thin install has no warehouse. Turn on sources you actually have: an employer folder you list, a ChatGPT export, a Slack export, a git repo you list, one exported mbox folder, or a meetings library. Two of those can fill a buffet. Then extract, `review` or approve, `defend`, and `tailor`. The same adapters serve both setups. There is no plugin scan. Ollama stays the default. Completions are unlimited unless you set a call cap. A remote model is opt-in and prints an egress notice.

## Adapters

The list is `src/dossier/contributions.py`. Names and limits: [Adapters](docs/adapters.md).

## Install

Python 3.11+ and [uv](https://docs.astral.sh/uv/) on the machine that holds the folders. There is no container image. The default model is Ollama on loopback. `DOSSIER_LLM_PROVIDER=off` skips model calls. A remote completion prints an egress notice. Interpreter and FTS5 notes: [Install](docs/install.md).

```text
uv sync --extra dev
uv run dossier doctor
```

## CLI

```text
uv run dossier ingest --adapter employer /path/you/listed
uv run dossier ingest --adapter git /path/to/repo
uv run dossier index
uv run dossier ask "what did I write about coastal governance?"
uv run dossier match --posting ./posting.txt
uv run dossier review
uv run dossier gui
uv run dossier defend
uv run dossier tailor --posting ./posting.txt
uv run dossier gaps
```

The full command list and environment knobs are in [CLI](docs/cli.md). Copy `dossier.example.toml` to `data/dossier.toml` when you want file defaults. Environment variables win. `dossier gui` is the optional loopback workbench (`uv sync --extra web`). The install path without that extra stays the CLI plus `dossier review`.

## Privacy

Records stay on this machine. The only way text leaves is a remote LLM, and that is off by default: provider `litellm`, or `DOSSIER_LLM_ALLOW_REMOTE=true` for a non-loopback Ollama. The CLI prints an egress notice before that call (not when a remote URL is blocked). `dossier doctor` prints `egress: no` or `egress: yes`, and warns on empty identity, empty pubs, and Sent-folder metadata. Dumps, the corpus, exports, and local assessments stay out of git. Before every push, run `python3 scripts/release/check_gitignore.py` and do not push if it fails. Detail is in [Privacy](docs/privacy.md).

## Later

`tailor` writes markdown from approved spans. A PDF or portal CV is still outside this repo. Own publications are the Zotero collection named in config. Next is a second person installing from this README. See [Roadmap](docs/roadmap.md).

## Docs

- [Changelog](CHANGELOG.md) — 0.4 through 0.9
- [Status](docs/status.md) — what this version does
- [Roadmap](docs/roadmap.md) — user testing after 0.9
- [Architecture](docs/architecture.md) — pipeline and where an adapter plugs in
- [Seekers](docs/seekers.md) — mail, Slack, meetings
- [Prior art](docs/prior-art.md) — what this borrows
- [Publications index](docs/zotero-rag-pubs.md) — named Zotero collection
- Product page and Sphinx guide: `uv sync --extra docs && make pages-site` → `_site/`

MIT. Copyright 2026 Dossier contributors.
