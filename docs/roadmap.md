# Roadmap

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

## Waves

### 0.7 — Corpus a thin user could grow

Breadth without a second warehouse product.

- **Employer-folder adapter (allowlist only).** Named paths Glen lists. Not a walk of all of Documents.
- **Thin-user paths where warehouse is absent:** ChatGPT export zip, Slack export zip, one small exported mbox folder — same adapters, no DuckDB required.
- **Meetings lane** reads a TranscriptX library, or a folder of JSON plus speaker-map sidecars. It keeps meetings where you are a named speaker and stores your turns. It does not import TranscriptX or copy the library.
- **Git history** as an optional explicit adapter.
- **Ask into the publications server** as an optional retrieve source once own-pubs ingest is on — still not a re-embed of other libraries.
- **Done when:** someone without `data_dumps` can enable two adapters they actually have and fill a buffet.

### 0.8 — Search that finds what FTS misses

Depth of interview, still citing `evidence.db` URIs.

- **Hybrid or embedding index** behind `ask`. Recallr-style search is a candidate backend, not a second product.
- Stronger compound and hop behaviour inside the existing call budget; refuse stays refuse.
- Gaps that point at extract or ingest targets (empty lenses, unspanned approved cards) without auto-approving anything.
- **Done when:** a question that used to refuse on FTS-only often returns a cited span or an honest refusal, not a wrong guess.

### 0.9 — Paste-ready employment kit

The locker becomes something you ship from, not only something you interview.

- **Tailoring (JD factory):** posting in, CV or letter **markdown** out from **approved** cards only. RenderCV / JSON Resume stay outside this repo; Dossier does not grow a PDF renderer.
- Referee shortlist polish (optional own-pubs coauthor signal) — still read-only, still “confirm before listing,” still no auto-attach.
- Thin-user onboarding: one folder + optional OpenAI-compatible API with egress notice; Ollama remains the default.
- France Travail / portal CV remains an Untangle admin tick that *consumes* approved cards — not a Dossier feature.
- **Done when:** Glen can take a posting, pull a packet or tailored draft from approved spanned cards, and shortlist referees without leaving the machine — and a second person could follow the same path with their own adapters.

### 0.9 → 1.0 — User testing

No new product surface. Find what breaks when it is not Glen’s laptop and not synthetic fixtures.

- Second person (or Glen running as a thin user) installs from the README, enables only adapters they have, and completes ingest → extract → approve → ask → packet (and optional brief / referees).
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
