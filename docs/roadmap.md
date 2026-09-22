# Roadmap

Type: PRODUCT
Authority: What shipped, what is next, and the refuse lines. Current behavior lives in [status](status.md).

Versioned waves from the locker you have today through a product someone else can try. Behaviour detail lives in [status](status.md). Pipeline shape lives in [architecture](architecture.md). Life facts and commitment stay in Untangle (`projects/dossier.md`).

Waves are ambition, not a calendar. Hard boundaries at the bottom do not move.

## Shipped

### 0.4 — Locker plus interview

Local SQLite corpus, ten explicit adapters, deterministic then optional-model claim drafts, human `approve`, and `ask` / `brief` / `run` over approved claims, passages, one Lens/Kind hop, and a call budget. Read-only `referees`. `doctor` for data dir, FTS5, provider, budget, adapters.

### 0.5 — Show the carrying sentence

`span`, `defend`, `gaps`, and `packet`. One sentence must carry the claim on its own; whole-record support is not enough.

Tested on synthetic fixtures.

### 0.6 — Prove it on Glen’s machine

- `dossier prove` — disposable real-corpus pass, ledger, never approves
- `doctor` prints python / sqlite / FTS5; install guide documents a known-good interpreter
- Own-pubs HTTP `POST /search` maps hits into records when no Zotero collection is configured
- Product page + Sphinx guide (`make pages-site`)

Still open for the full done-when: warehouse `make prove` spot-check by Glen. The named Zotero collection is ingested with the other adapters.

### 0.8 — Thin corpus and hybrid ask

Employer allowlist, ChatGPT export, Slack export, and git history, plus the meetings lane and a capped exported-mbox folder. Passage vectors live in `evidence.db`. `ask` fuses them with full text when the lexical set is empty or thin, still refuses when nothing carries the sentence, and can optionally retrieve from the pubs server without writing the corpus. `gaps` points at ingest or extract. `dossier index` is the embed step. Ollama stays the default.

### 0.9 — Paste-ready employment kit

`dossier tailor` turns a posting and spanned approved cards into CV or letter markdown, plus a coverage list. `--arrange` may reorder a letter from those spans only. Referees can use a pubs name already in the corpus and print up to two claims they could speak to. Still confirm before listing. Still no PDF renderer and no Twenty writes.

## Waves

### 0.9 → 1.0 — User testing

Find what breaks when it is not Glen’s laptop and not synthetic fixtures. Match lists evidence for each requirement in a pasted job spec (`dossier match` and the workbench Match page). Tailor stays off that page. There is still no PDF.

- Second person (or Glen running as a thin user) installs from the README, enables only adapters they have, and completes ingest → extract → approve → ask → packet (and optional brief, tailor, or referees).
- Acceptance checklist: refusals that should refuse, citations that resolve, egress notice when cloud is opted in, Twenty read-only when used, no dumps or evidence DB in git.
- Docs and `doctor` messages fixed for every footgun found; features deferred, not patched in as drive-bys.
- Career inventory covers years across the locker (seeker year floor, employer career folders at read time), not only the three newest files per kind.
- **1.0** means that path is boring enough to call done — not that every Later idea below has shipped.

### After 1.0 — Workbench

The optional loopback workbench (`dossier gui`, `[web]` extra) covers the daily loop: locker, ingest, extract, review, ask, match, index, brief, and run, plus effort (context and timeout ladder; `balanced` matches today's defaults), saved profiles, a prompt catalogue, and editable question packs. Failed jobs and ingest/extract counts surface on the page; the job strip polls only while busy. Vocabulary is in [vocab](vocab.md). The 1.0 path stays CLI plus `dossier review` with no new dependency.

Still later: tailor, packet, gaps, prove, and referees as pages, then cited chat streamed on the same ask path.

## Boundaries that stay

These are not delayed features; they are refuse lines.

- No Twenty writes (Tasks, Opportunities, Notes, last-contacted)
- No auto-attach of a referee name to an application
- No cloud LLM default. Text leaves the machine only when the provider is `litellm` or `DOSSIER_LLM_ALLOW_REMOTE` is set. The CLI prints an egress notice first. `dossier doctor` reports `egress: no` or `egress: yes`
- No 26G IDDRI mbox stream; no Sent Mail as a folder walker; no re-embed of hoops/ocean
- No plugin directory or entry-point scan
- No Docker image for the locker. It installs with `uv` on the host. Publications are the named Zotero collection, read in-process. No compose server, and no re-embed of hoops or ocean
- Dumps, warehouse, LanceDB, `evidence.db`, `.env`, mbox, and PDFs stay off git. Before every push, `python3 scripts/release/check_gitignore.py` must pass
