# Dossier

Local-first evidence locker and ask-the-corpus RAG for professional work. Private. Dumps, mail, and PDFs stay on your machine, outside this git tree.

Untangle spec (Glen): `~/Documents/untangle/projects/dossier.md`. This README does not copy task lists from there.

## What it does

1. **Locker** — claim cards with citations. If the evidence will not carry a claim, the claim is refused. A human approves a card before it is pasted into a CV.
2. **RAG** — ask what you actually did. Answers cite the same records.

v0 is this scaffold. Extractors are not wired yet.

## Glen vs a thin install

| | Glen | Thin user |
| --- | --- | --- |
| LLM | Ollama on `127.0.0.1:11434` | Ollama, or an OpenAI-compatible API you opt into |
| Mail | Thunderbird mbox under `~/email` (bodies). data_dumps Thunderbird tables are metadata only | One exported folder |
| Dumps | Read `~/Documents/data_dumps_raw` warehouse. Do not re-implement those loaders | Skip, or one export zip |
| Pubs | Zotero collection `my pubs` via a separate zotero-rag instance (see `docs/zotero-rag-pubs.md`). Do not re-embed other libraries | Optional PDF folder |
| People / referees | Later: read Twenty. Not in v0 | Skip, or a local CSV |

Cloud models are opt-in and must print an egress notice. Work mail and Slack do not leave the machine by default.

## Adapters

Explicit list in `src/dossier/contributions.py`. No plugin directory, no entry-point scan. Enable only the adapters you have. The list is empty until a source is in hand.

## Privacy

Do not commit dumps, DuckDB, LanceDB, evidence databases, `.env`, mbox, or PDFs. See `.gitignore`.

## Later

**Referee suggest** is not v0. When it exists it will read a CRM (Glen: Twenty People / Company / Notes) and shortlist names from job text, closeness already recorded, and hiring-firm overlap. A human confirms before a name is written on an application. No last-contacted column. No email send. Spec: Untangle `projects/dossier.md` (Later — referee suggest).
