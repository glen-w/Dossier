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

### 0.10 — Gates, span rule, workbench as 1.0 loop

Engineering gates (interpreter pin, ruff, mypy, CI). A stored span is one paste-sized sentence (`SPAN_MAX`, default 320). `defend --refresh` re-spans; `audit-cards` lists approved cards the new rule would refuse. The loopback workbench covers the daily loop, including prove, referees, and gaps pages, plus streamed cited ask. Notes and `.ics` adapters. `eval`, `export` / `import`, `backup`, `tailor --format json-resume` (data, not a renderer). `scripts/release/second_machine.sh` is the synthetic second-machine path.

## Waves

### 1.0 — Second machine

The workbench loop shipped in 0.10. 1.0 is that loop plus a boring path on a machine that is not this locker:

- Someone else installs from the README, enables only adapters they have, and completes ingest → extract → approve → defend → ask → packet (and optional brief, tailor, or referees). A thin install (no warehouse) is the same path.
- Acceptance: refusals that should refuse, citations that resolve, every quoted span at or under `SPAN_MAX`, egress notice when cloud is opted in, Twenty read-only when used, no dumps or evidence DB in git.
- `scripts/release/second_machine.sh` is the synthetic form of that path.

Still later: a CV PDF renderer. Office text (PDF via the `office` extra, Word and PowerPoint in the standard library) is capped record text, not a renderer. `sqlite-vec` stays an optional extra; pure Python is the floor.

## Boundaries that stay

These are not delayed features; they are refuse lines.

- No Twenty writes (Tasks, Opportunities, Notes, last-contacted)
- No auto-attach of a referee name to an application
- No cloud LLM default. Text leaves the machine only when the provider is `litellm` or `DOSSIER_LLM_ALLOW_REMOTE` is set. The CLI prints an egress notice first. `dossier doctor` reports `egress: no` or `egress: yes`
- No walk of a blocked mail tree; no Sent Mail as a folder walker; no re-embed of a Zotero library you did not name
- No plugin directory or entry-point scan
- No Docker image for the locker. It installs with `uv` on the host. Publications are the named Zotero collection, read in-process. No compose server, and no re-embed of a Zotero library you did not name
- Dumps, warehouse, LanceDB, `evidence.db`, `.env`, mbox, and PDFs stay off git. Before every push, `python3 scripts/release/check_gitignore.py` must pass
