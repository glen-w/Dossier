# Roadmap

Type: PRODUCT
Authority: What shipped, what is next, and the refuse lines. Current behavior lives in [status](status.md).

Versioned waves from the locker you have today through a product someone else can try. Behaviour detail lives in [status](status.md). Pipeline shape lives in [architecture](architecture.md). Life facts and commitment stay in Untangle (`projects/dossier.md`).

Waves are ambition, not a calendar. Hard boundaries at the bottom do not move.

## Shipped

### 0.4 — Locker plus interview

Local SQLite corpus, seven explicit adapters, deterministic then optional-model claim drafts, human `approve`, and `ask` / `brief` / `run` over approved claims, passages, one Lens/Kind hop, and a call budget. Read-only `referees`. `doctor` for data dir, FTS5, provider, budget, adapters.

### 0.5 — Show the carrying sentence

`span`, `defend`, `gaps`, and `packet`. One sentence must carry the claim on its own; whole-record support is not enough.

Tested on synthetic fixtures.

### 0.6 — Prove it on Glen’s machine

- `dossier prove` — disposable real-corpus pass, ledger, never approves
- `doctor` prints python / sqlite / FTS5; install guide documents a known-good interpreter
- Own-pubs HTTP `POST /search` maps hits into records; live compose/ingest stays gated on collection confirm
- Product page + Sphinx guide (`make pages-site`)

Still open for the full done-when: warehouse `make prove` spot-check by Glen, and pubs after collection name + ~353 confirmed.

### 0.8 — Thin corpus and hybrid ask

Employer allowlist, ChatGPT export, Slack export, and git history, plus the meetings lane and a capped exported-mbox folder. Passage vectors live in `evidence.db`. `ask` fuses them with full text when the lexical set is empty or thin, still refuses when nothing carries the sentence, and can optionally retrieve from the pubs server without writing the corpus. `gaps` points at ingest or extract. `dossier index` is the embed step. Ollama stays the default.

### 0.9 — Paste-ready employment kit

`dossier tailor` turns a posting and spanned approved cards into CV or letter markdown, plus a coverage list. `--arrange` may reorder a letter from those spans only. Referees can use a pubs name already in the corpus and print up to two claims they could speak to. Still confirm before listing. Still no PDF renderer and no Twenty writes.

## Waves

### 0.9 → 1.0 — User testing

No new product surface. Find what breaks when it is not Glen’s laptop and not synthetic fixtures.

- Second person (or Glen running as a thin user) installs from the README, enables only adapters they have, and completes ingest → extract → approve → ask → packet (and optional brief, tailor, or referees).
- Acceptance checklist: refusals that should refuse, citations that resolve, egress notice when cloud is opted in, Twenty read-only when used, no dumps or evidence DB in git.
- Docs and `doctor` messages fixed for every footgun found; features deferred, not patched in as drive-bys.
- **1.0** means that path is boring enough to call done — not that every Later idea below has shipped.

## Boundaries that stay

These are not delayed features; they are refuse lines.

- No Twenty writes (Tasks, Opportunities, Notes, last-contacted)
- No auto-attach of a referee name to an application
- No cloud LLM default; egress notice when a completion can leave the machine
- No 26G IDDRI mbox stream; no Sent Mail as a folder walker; no re-embed of hoops/ocean
- No plugin directory or entry-point scan
- Dumps, warehouse, LanceDB, `evidence.db`, `.env`, mbox, and PDFs stay off git
