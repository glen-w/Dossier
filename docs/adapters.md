# Adapters

Adapters are an explicit list in `src/dossier/contributions.py`. There is no
plugin directory and no entry-point scan. Turn on only the sources you have.

| Adapter | What `ingest` does now |
| --- | --- |
| `pubs` | JSON fixture in tests. Live: `POST /search` on `DOSSIER_PUBS_URL` when the pubs server returns hits. Does not embed a Zotero library. |
| `chatgpt` | Reads `chatgpt.messages` from a DuckDB warehouse you already have. |
| `linkedin` | Reads positions, education, skills, publications from that warehouse. |
| `applications` | Walks one folder whose name contains “job application”. Text files are stored; PDFs are inventory only. |
| `transcripts` | Cursor `agent-transcripts` and optional Grok blobs. |
| `slack` | Seeks Glen-touched rows in warehouse `slack.*`, then fetches selected bodies under caps. |
| `mbox` | Seeks Thunderbird Gloda metadata; fetches **one** allowlisted mbox body under a size cap. Never streams IDDRI or Sent Mail. |
| `meetings` | Seeks a TranscriptX library for meetings where you are a named speaker, then stores your turns. |

ChatGPT, LinkedIn, and Slack expect the warehouse schema produced elsewhere.
Point `DATA_DUMPS_WAREHOUSE` at `catalog.duckdb`.

Behaviour detail: [status](status.md). Seekers: [seekers](seekers.md).
