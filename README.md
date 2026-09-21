# Dossier

Local-first evidence locker and ask-the-corpus RAG for professional work. Private. Dumps, mail, and PDFs stay on your machine, outside this git tree.

Untangle spec (Glen): `~/Documents/untangle/projects/dossier.md`. This README does not copy task lists from there.

## What it does

1. **Locker** — claim cards with citations. If the evidence will not carry a claim, the claim is refused. A human approves a card before it is pasted into a CV.
2. **RAG** — ask what you actually did. Answers cite the same records. **Not built yet.**

v0 is the locker: five explicit adapters, extract, buffet, approve. Mail and Slack are parked.

## Glen vs a thin install

| | Glen | Thin user |
| --- | --- | --- |
| LLM | Ollama on `127.0.0.1:11434` | Ollama, or an OpenAI-compatible API you opt into |
| Mail | Thunderbird mbox under `~/email` (bodies). data_dumps Thunderbird tables are metadata only | One exported folder |
| Dumps | Read `~/Documents/data_dumps_raw` warehouse. Do not re-implement those loaders | Skip, or one export zip |
| Pubs | Zotero collection `my pubs` via a separate zotero-rag instance (see `docs/zotero-rag-pubs.md`). Do not re-embed other libraries | Optional JSON fixture |
| People / referees | Later: read Twenty. Not in v0 | Skip, or a local CSV |

Cloud models are opt-in and must print an egress notice. Work mail and Slack do not leave the machine by default.

## Adapters

Explicit list in `src/dossier/contributions.py`. No plugin directory, no entry-point scan. Enable only the adapters you have.

| Name | Glen path | Notes |
| --- | --- | --- |
| `pubs` | zotero-rag-pubs `:8012` | Retrieve only. Ingest off until the collection is confirmed. Tests use a stub. |
| `chatgpt` | warehouse `chatgpt.messages` | Read DuckDB. No zip loader. |
| `linkedin` | warehouse positions / education / skills / publications | Read DuckDB. |
| `applications` | `~/Documents/job applications/` | Text files in. PDF bytes stay on disk. |
| `transcripts` | Cursor `agent-transcripts/` and Grok Bot blobs | Local scan. Not committed. |

## CLI

Corpus and cards live in `~/Documents/Dossier/data/evidence.db` (gitignored). Override with `DOSSIER_DATA`.

```text
uv run dossier ingest --adapter chatgpt
uv run dossier ingest --adapter applications "~/Documents/job applications"
uv run dossier extract
uv run dossier buffet --status pending
uv run dossier approve <card-id>
```

`extract` talks to Ollama unless `DOSSIER_LLM_PROVIDER=off`. LiteLLM / a non-loopback URL prints a yellow egress notice.

## Privacy

Do not commit dumps, DuckDB, LanceDB, evidence databases, `.env`, mbox, or PDFs. See `.gitignore`.

## Later

**Ask-the-corpus RAG** over the same records. **mbox** (not the 26G IDDRI box as a first folder). **Slack**. Employer-named folders (needs an allowlist). Git. TranscriptX exports. JD factory (RenderCV).

**Referee suggest** is not v0. When it exists it will read a CRM (Glen: Twenty People / Company / Notes) and shortlist names from job text, closeness already recorded, and hiring-firm overlap. A human confirms before a name is written on an application. No last-contacted column. No email send. Spec: Untangle `projects/dossier.md` (Later — referee suggest).
