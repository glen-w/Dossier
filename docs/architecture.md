# Architecture

```text
optional adapters
    → gitignored local corpus
        → claim extractor (locker) and retriever (RAG)
            → human gate
                → buffet you can paste
                → answers with citations
```

## Source protocol

One adapter per source. Registered by appending `CONTRIBUTIONS` in `src/dossier/contributions.py`. Not discovered from a plugins folder.

- `detect(path)` — this adapter owns the file or folder
- `load(path)` — read into the local corpus (not a second data_dumps warehouse)
- `tables()` — record names this adapter provides

data_dumps stays the GDPR ingest path. Dossier reads that warehouse when the adapter exists. It does not copy loaders.

## Later — referee suggest

Not v0. Read-only CRM lookup (Glen: Twenty People, Company, Notes). Rank on job-content fit, closeness already in notes or timeline, and hiring-firm overlap. Warn before spending a scarce referee. Human confirms before a name is attached to a PDF. Do not write Tasks or Opportunities. Do not add a last-contacted column.
