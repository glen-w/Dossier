# Architecture

```text
optional adapters
    → gitignored local corpus (data/evidence.db)
        → claim extractor (locker) and retriever (RAG, later)
            → human gate (`dossier approve`)
                → buffet you can paste
                → answers with citations (later)
```

## Source protocol

One adapter per source. Registered by appending `CONTRIBUTIONS` in `src/dossier/contributions.py`. Not discovered from a plugins folder.

- `detect(path)` — this adapter owns the file or folder
- `load(path, corpus)` — read into the local corpus (not a second data_dumps warehouse)
- `tables()` — record names this adapter provides

data_dumps stays the GDPR ingest path. Dossier reads that warehouse when the adapter exists. It does not copy loaders.

Claim cards: empty citations, missing records, or text that will not carry the sentence → **refused**. A human must approve a pending card before it is paste-ready.

## Wired (locker A)

`pubs`, `chatgpt`, `linkedin`, `applications`, `transcripts`. See README.

## Later — ask-the-corpus RAG

Hue C. Same records. Not this sitting. Recallr-style SQLite hybrid search is a candidate backend, not the product UI.

## Later — parked adapters

mbox (wrap rollup `parse.py`; never default to the 26G IDDRI box), Slack, employer-named folders (explicit path allowlist; do not walk Documents), git, TranscriptX exports.

## Later — referee suggest

Not v0. Read-only CRM lookup (Glen: Twenty People, Company, Notes). Rank on job-content fit, closeness already in notes or timeline, and hiring-firm overlap. Warn before spending a scarce referee. Human confirms before a name is attached to a PDF. Do not write Tasks or Opportunities. Do not add a last-contacted column.
