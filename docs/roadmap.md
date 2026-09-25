# Roadmap

Type: PRODUCT
Authority: What shipped, what is next, and the refuse lines. Current behavior lives in [status](status.md).

Versioned waves from the locker you have today through a product someone else can try. Behaviour detail lives in [status](status.md). Pipeline shape lives in [architecture](architecture.md). Life facts stay out of this repo.

Waves are ambition, not a calendar. Hard boundaries at the bottom do not move.

## Shipped

### 0.4 — Locker plus interview

Local SQLite corpus, ten explicit adapters, deterministic then optional-model claim drafts, human `approve`, and `ask` / `brief` / `run` over approved claims, passages, one Lens/Kind hop, and a call budget. Read-only `referees`. `doctor` for data dir, FTS5, provider, budget, adapters.

### 0.5 — Show the carrying sentence

`span`, `defend`, `gaps`, and `packet`. One sentence must carry the claim on its own; whole-record support is not enough.

Tested on synthetic fixtures.

### 0.6 — Prove it on a real locker

- `dossier prove` — disposable real-corpus pass, ledger, never approves
- `doctor` prints python / sqlite / FTS5; install guide documents a known-good interpreter
- Own-pubs HTTP `POST /search` maps hits into records when no Zotero collection is configured
- Product page + Sphinx guide (`make pages-site`)

Still open for the full done-when: a warehouse `make prove` spot-check on a real locker. The named Zotero collection is ingested with the other adapters.

### 0.8 — Thin corpus and hybrid ask

Employer allowlist, ChatGPT export, Slack export, and git history, plus the meetings lane and a capped exported-mbox folder. Passage vectors live in `evidence.db`. `ask` fuses them with full text when the lexical set is empty or thin, still refuses when nothing carries the sentence, and can optionally retrieve from the pubs server without writing the corpus. `gaps` points at ingest or extract. `dossier index` is the embed step. Ollama stays the default.

### 0.9 — Paste-ready employment kit

`dossier tailor` turns a posting and spanned approved cards into CV or letter markdown, plus a coverage list. `--arrange` may reorder a letter from those spans only. Referees can use a pubs name already in the corpus and print up to two claims they could speak to. Still confirm before listing. Still no PDF renderer and no Twenty writes.

## Waves

### 0.9 → 1.0 — User testing

Find what breaks on a machine that is not the one that grew this locker, and not synthetic fixtures. Match lists evidence for each requirement in a pasted job spec (`dossier match` and the workbench Match page). Tailor stays off that page. There is still no PDF.

- Someone else installs from the README, enables only adapters they have, and completes ingest → extract → approve → ask → packet (and optional brief, tailor, or referees). A thin install (no warehouse) is the same path.
- Acceptance checklist: refusals that should refuse, citations that resolve, egress notice when cloud is opted in, Twenty read-only when used, no dumps or evidence DB in git.
- Docs and `doctor` messages fixed for every footgun found; features deferred, not patched in as drive-bys.
- Career inventory covers years across the locker (seeker year floor, employer career folders at read time), not only the three newest files per kind.
- **1.0** means that path is boring enough to call done — not that every Later idea below has shipped.

### After 1.0 — Workbench

The loopback workbench (`dossier gui`, `[web]` extra) covers the daily loop: locker, ingest, extract, review (including the carrying sentence and defend), ask, match, tailor, packet, gaps, index, brief, and run, plus effort, saved profiles, a prompt catalogue, and editable question packs. Nav is grouped into Prepare, Decide, Use, and Settings; every page keeps its URL. The locker leads with the next step. Review can be a one-card queue on the same approve, refuse, reopen, and defend actions. Match shows a coverage rail and can open Tailor with the same posting; Tailor stays off the Match page. Ask, match, and tailor keep the submitted text when the job finishes. `dossier review` opens that same review page. Failed jobs surface the error only; tracebacks stay in the server log. Vocabulary is in [vocab](vocab.md). The scriptable path stays the CLI.

Still later: prove and referees as pages, then cited chat streamed on the same ask path. A CV PDF renderer stays out. Office text (PDF via the `office` extra, Word and PowerPoint in the standard library) is capped record text, not a renderer.

## Boundaries that stay

These are not delayed features; they are refuse lines.

- No Twenty writes (Tasks, Opportunities, Notes, last-contacted)
- No auto-attach of a referee name to an application
- No cloud LLM default. Text leaves the machine only when the provider is `litellm` or `DOSSIER_LLM_ALLOW_REMOTE` is set. The CLI prints an egress notice first. `dossier doctor` reports `egress: no` or `egress: yes`
- No walk of a blocked mail tree; no Sent Mail as a folder walker; no re-embed of a Zotero library you did not name
- No plugin directory or entry-point scan
- No Docker image for the locker. It installs with `uv` on the host. Publications are the named Zotero collection, read in-process. No compose server, and no re-embed of a Zotero library you did not name
- Dumps, warehouse, LanceDB, `evidence.db`, `.env`, mbox, and PDFs stay off git. Before every push, `python3 scripts/release/check_gitignore.py` must pass
