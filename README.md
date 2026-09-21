# Dossier

Dossier is a local-first locker for professional evidence. It turns records you already have into claim cards you could paste into a CV or letter. Each claim cites a record. If the record will not carry the sentence, the claim is refused. You approve a card before it is paste-ready.

Exports, mail, and PDFs stay on your machine. They are not part of this git tree.

Ask-the-corpus — “what did I actually do?” — is `dossier ask`. It answers from records already in the locker and prints the citation URIs. Version **0.4** adds passages, approved-card answers, one seeker hop, compound split, and a model call budget. How far that goes is under [Status](docs/status.md). What comes next is under [Roadmap](docs/roadmap.md).

## How a card gets made

1. **Ingest** an adapter you actually have. Records land in a local SQLite file, `data/evidence.db`.
2. **Extract** drafts a card when the record already carries the sentence, then asks a local model for the rest.
3. Empty citations, missing records, or text that does not support the sentence are stored as **refused**.
4. **Buffet** lists the cards. **Approve** is the human gate. Nothing is copied into a CV by the tool.
5. **Ask** quotes a matching span when that span carries the question. An approved claim can answer first. Otherwise one local completion, still cited or refused.
6. **Brief** and **run** answer a fixed question pack into `data/briefs/`. They do not approve cards. **Doctor** prints whether this interpreter has full text and which adapters detect.

Adapters are an explicit list in `src/dossier/contributions.py`. There is no plugin directory and no entry-point scan. Turn on only the sources you have.

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```text
uv sync --extra dev
uv run dossier --help
```

The default model is Ollama at `http://127.0.0.1:11434`. Set `DOSSIER_LLM_PROVIDER=off` to skip model calls. `dossier ask --mode exact` still quotes from the corpus. An OpenAI-compatible API is opt-in (`DOSSIER_LLM_PROVIDER=litellm`, plus `dossier[llm]`). If a completion can leave the machine, the CLI prints an egress notice before it runs. Copy `dossier.example.toml` to `data/dossier.toml` to change defaults; environment variables win.

## CLI

```text
uv run dossier ingest --adapter applications ./path/to/applications
uv run dossier ingest --adapter slack
uv run dossier ingest --adapter mbox
uv run dossier extract --source slack
uv run dossier extract
uv run dossier buffet --status pending
uv run dossier approve <card-id>
uv run dossier ask "what did I write about coastal governance?"
uv run dossier ask --mode exact --source pubs "coastal governance"
uv run dossier brief
uv run dossier brief --posting ./posting.txt
uv run dossier run
uv run dossier doctor
uv run dossier referees --posting ./posting.txt --employer "Hiring Org"
```

`dossier referees` reads a JSON people file, or Twenty when both API variables below are set. It prints a shortlist and does not write the corpus or the CRM. Put skips in a local policy file (`--policy` or `DOSSIER_REFEREE_POLICY`), for example under `private/`, which is gitignored.

`evidence.db` is created under `~/Documents/Dossier/data` unless you set `DOSSIER_DATA` to another directory. That file is gitignored.

| Variable | Use |
| --- | --- |
| `DOSSIER_LLM_MODEL` | Ollama tag (default `qwen3.8:latest`) |
| `DOSSIER_ASK_MODE` | `exact`, `auto` (default), or `rich` |
| `DOSSIER_ASK_FTS` | Use SQLite full text on title, text, and passages (`true` by default). Whole-word overlap is used when this Python has no FTS5 module |
| `DOSSIER_ASK_CARDS_FIRST` | Prefer an approved claim that carries the question (`true` by default) |
| `DOSSIER_ASK_PASSAGES` | Search passage rows and cite the parent record (`true` by default) |
| `DOSSIER_ASK_HOPS` | After a miss, hop once on Lens/Kind (default `1`) |
| `DOSSIER_ASK_DECOMPOSE` | Split compound questions: `off`, `auto` (default), or `on` |
| `DOSSIER_ASK_PLANNER` | `off` (default) or `rich` to spend one call on sub-questions |
| `DOSSIER_LLM_MAX_CALLS` | Cap completions per process (default `6`) |
| `DOSSIER_EXTRACT_LLM` | Ask the model after drafts (`true` by default) |
| `DOSSIER_RUN_PACK` | Question pack for `brief` and `run` (default `career`) |
| `DOSSIER_RUN_POSTING` | Local posting path for the posting pack |
| `DOSSIER_RUN_ADAPTERS` | Comma-separated adapter allowlist for `run` |
| `DOSSIER_LLM_BASE_URL` | Ollama root |
| `DOSSIER_LLM_ALLOW_REMOTE` | Allow a non-loopback Ollama URL |
| `DOSSIER_LLM_API_BASE` | Base URL when provider is `litellm` |
| `DATA_DUMPS_WAREHOUSE` | DuckDB file for ChatGPT, LinkedIn, Slack, and mail seekers |
| `DOSSIER_MAIL_ROOT` | Thunderbird tree for mbox body fetch (default `~/email`) |
| `DOSSIER_SLACK_USER_IDS` | Comma-separated Slack user ids to treat as you |
| `DOSSIER_SEEKER_PER_STRATUM` | Max hits per lens/kind/year (default 20) |
| `DOSSIER_SEEKER_OVERALL` | Max seeker records per ingest (default 400) |
| `DOSSIER_APPLICATIONS` | Folder of prior application packs |
| `DOSSIER_CURSOR_PROJECTS` | Cursor projects root (transcripts) |
| `DOSSIER_GROK_BLOBS` | Optional extra transcript folder |
| `DOSSIER_PUBS_URL` | Publications RAG base URL (default `http://127.0.0.1:8012`) |
| `DOSSIER_TWENTY_API_URL` | Twenty API origin for `referees` (read-only GraphQL) |
| `DOSSIER_TWENTY_API_KEY` | Bearer token for that read. Never commit it |

## Privacy

Do not commit dumps, DuckDB files, LanceDB, `evidence.db`, `.env`, mbox, or PDFs. See `.gitignore`.

Work stays on loopback unless you opt into a remote model. The egress notice is the warning, not a block.

## Docs

- [Status](docs/status.md) — what is implemented, stubbed, and unbuilt
- [Roadmap](docs/roadmap.md) — now / next / later, and hard boundaries
- [Architecture](docs/architecture.md) — pipeline and adapter protocol
- [Seekers](docs/seekers.md) — mail and Slack: seek, quotas, targeted fetch
- [Prior art](docs/prior-art.md) — what this borrows
- [Publications index](docs/zotero-rag-pubs.md) — separate RAG instance for your own papers

MIT. Copyright 2026 Glen.
