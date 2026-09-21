# Roadmap

What ships now, what is next, and what stays later. Behaviour detail lives in [status](status.md). Pipeline shape lives in [architecture](architecture.md). Life facts and commitment stay in Untangle (`projects/dossier.md`).

## Shipped — 0.4

Local locker plus interview over the same SQLite records.

- Ingest through seven explicit adapters; seek/fetch for mail and Slack under the hard caps
- Deterministic claim drafts, then an optional local model; human `approve`
- `ask` / `brief` / `run`: approved claims first, passages, one Lens/Kind hop, compound split, call budget
- Read-only `referees` shortlist (JSON or Twenty GraphQL read). No CRM writes, no auto-attach
- `doctor` for data dir, FTS5 availability, provider, budget, adapter detect

Tested on synthetic fixtures. Not yet run as a full extract or ask over a real corpus in this repository’s history.

## Now — 0.5

Show the sentence that carries a claim.

- `span` prints that sentence, with its URI and title, or refuses
- `defend` stores it on pending and approved cards (`extras.span`, `extras.span_uri`) and does not change status
- `gaps` counts Lens and Kind headers and lists approved cards that are the only spanned card for that pair
- `packet` writes `data/packets/<stamp>.md` from approved cards that have a span
- A sentence must carry the claim on its own. Words spread across two sentences can still pass the whole-record check and still fail `span`

## Next

Ship these before new product surfaces. Order is preference, not a promise.

1. **Own-pubs retrieve that returns rows.** Keep `zotero-rag-pubs` as a separate instance. Turn ingest on only after Glen confirms the collection name (`my pubs` / similar) and the 353-item scope. Do not embed hoops or ocean.
2. **One real-corpus pass.** Point `DOSSIER_DATA` at a disposable dir, ingest sources Glen already has (warehouse Slack/LinkedIn/ChatGPT and/or a small mbox folder), run `extract` and `brief --mode exact`, then spot-check refusals. Still no IDDRI stream and no Documents walk.
3. **Interpreter that can run FTS5.** The default `uv` Python on this Mac may lack the module; `doctor` reports it and overlap remains the fallback. Prefer documenting a known-good Python, not vendoring SQLite.
4. **Employer-folder adapter (allowlist only).** Named paths Glen lists. Not a walk of all of Documents.

## Later

- **Hybrid or embedding index** behind `ask`, still citing `evidence.db` URIs. Recallr-style search is a candidate backend, not a second product.
- **More sources:** git history, meeting-export packets (TranscriptX wrap), thin-user zip paths where warehouse is absent.
- **Tailoring (JD factory):** posting in, CV or letter out from **approved** cards only. RenderCV / JSON Resume stay outside this repo; Dossier does not grow a PDF renderer.
- **Ask into the publications server** as an optional retrieve source once own-pubs ingest is on — still not a re-embed of other libraries.
- **France Travail / portal CV** as a consumer of approved cards — Untangle admin tick, not a Dossier feature.

## Boundaries that stay

These are not delayed features; they are refuse lines.

- No Twenty writes (Tasks, Opportunities, Notes, last-contacted)
- No auto-attach of a referee name to an application
- No cloud LLM default; egress notice when a completion can leave the machine
- No 26G IDDRI mbox stream; no Sent Mail as a folder walker; no re-embed of hoops/ocean
- No plugin directory or entry-point scan
- Dumps, warehouse, LanceDB, `evidence.db`, `.env`, mbox, and PDFs stay off git
