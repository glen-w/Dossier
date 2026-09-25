# Adapters

Type: GUIDE
Authority: Which ingest paths exist. Limits live in [status](status.md).

Adapters are an explicit list in `src/dossier/contributions.py`. There is no
plugin directory and no entry-point scan. Turn on only the sources you have.

| Adapter | What `ingest` does now |
| --- | --- |
| `pubs` | The Zotero collection named in config. Title, authors, year, journal, DOI, and abstract. No PDFs and no embeddings. |
| `chatgpt` | ChatGPT export zip or folder, or `chatgpt.messages` from a DuckDB warehouse you already have. |
| `linkedin` | Reads positions, education, skills, publications from that warehouse. |
| `applications` | Walks one folder whose name contains “job application”. Text files are stored; PDFs are inventory only. Stops after `DOSSIER_APPLICATIONS_MAX_FILES` (default 2000). |
| `transcripts` | Cursor `agent-transcripts` and optional Grok blobs. |
| `slack` | Slack export zip or folder, or your rows in warehouse `slack.*`. Quotas apply. |
| `mbox` | Seeks Thunderbird Gloda metadata; fetches **one** allowlisted mbox body under a size cap. An exported folder stops after a file cap. Never streams a blocked mail tree or Sent Mail. |
| `meetings` | Seeks a TranscriptX library for meetings where you are a named speaker, then stores your turns. |
| `employer` | Text in every folder you list, after a cache and duplicate filter. Not a walk of Documents. |
| `git` | Subject, date, and file names from repos you list, or one repo you pass to `ingest`. Optional author filter. No patches. |

LinkedIn still expects the warehouse schema. ChatGPT and Slack use that warehouse when you point them at it, and an export zip when you point them at one.
Point `DATA_DUMPS_WAREHOUSE` at `catalog.duckdb`.

Built-in include and exclude phrases apply on their own. Edit them in gitignored `dossier.toml`; the keys are listed in `dossier.example.toml` and [seekers](seekers.md).

Behaviour detail: [status](status.md). Seekers: [seekers](seekers.md).
