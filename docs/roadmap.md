# Roadmap

Type: PRODUCT
Authority: What shipped, what is next, and the refuse lines. Current behavior lives in [status](status.md).

Versioned waves from the locker you have today through a product someone else can try, and then through a locker you can keep. Behaviour detail lives in [status](status.md). Pipeline shape lives in [architecture](architecture.md). Shared words live in [vocab](vocab.md) once a command ships. Life facts stay out of this repo.

Waves are ambition, not a calendar. Hard boundaries at the bottom do not move. A later wave does not reopen them.

## How a wave is written

Each unshipped wave has four parts.

- **Pressure.** What is awkward once the previous wave is true.
- **Ships.** The commands and the rules. A name in backticks is the intended shape. The spelling can change when it lands in [status](status.md).
- **Done when.** Observable on synthetic fixtures. A check that needs a real locker is named, stays off git, and is never the CI signal.
- **Holds.** What this wave refuses to become, including the shortcut that would make the pressure go away faster.

Nothing in a wave approves a card by itself, sends mail, writes Twenty, or adds a sentence the record does not already hold. A renderer still lays out stored spans, claims, headings, and fixed labels.

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

Still open for the full done-when: a warehouse `make prove` spot-check on a real locker. The named Zotero collection is ingested with the other adapters. 1.0 picks this up as a human check.

### 0.8 — Thin corpus and hybrid ask

Employer allowlist, ChatGPT export, Slack export, and git history, plus the meetings lane and a capped exported-mbox folder. Passage vectors live in `evidence.db`. `ask` fuses them with full text when the lexical set is empty or thin, still refuses when nothing carries the sentence, and can optionally retrieve from the pubs server without writing the corpus. `gaps` points at ingest or extract. `dossier index` is the embed step. Ollama stays the default.

### 0.9 — Paste-ready employment kit

`dossier tailor` turns a posting and spanned approved cards into CV or letter markdown, plus a coverage list. `--arrange` may reorder a letter from those spans only. Referees can use a pubs name already in the corpus and print up to two claims they could speak to. Still confirm before listing. Still no Twenty writes.

### 0.10 — Gates, span rule, workbench as 1.0 loop

Engineering gates (interpreter pin, ruff, mypy, CI). A stored span is one paste-sized sentence (`SPAN_MAX`, default 320). `defend --refresh` re-spans; `audit-cards` lists approved cards the new rule would refuse. The loopback workbench covers the daily loop, including prove, referees, and gaps pages, plus streamed cited ask. Notes and `.ics` adapters. `eval`, `export` / `import`, `backup`, `tailor --format json-resume` (data, not a renderer). `scripts/release/second_machine.sh` is the synthetic second-machine path.

### 0.11 — Evidence you can paste, and retrieval that scales

- Paste-time check: `tailor`, `packet`, and `match` quote a stored span only while it is still in its cited record. `audit-cards` names a span the record no longer holds.
- Golden eval of about sixty synthetic cases, with known leniency printed on every run, plus recall@k and MRR (`eval --retrieval`). Property tests hold the span cap, the citation rule, and the paste path.
- Numbered store migrations, an automatic copy of a locker with records before any migration, and a refusal to open a locker written by a newer Dossier.
- Retrieval: full text names candidates and only those records and passages load, vector search streams instead of loading every blob, `sqlite-vec` runs the same scan in C when the extra is installed, and `dossier index` is paged, resumable, and narrowable.
- Renderer: `tailor --format html|docx|pdf` from one typed draft. Layout only; no prose is added. PDF needs the optional `render` extra.

## Still open at 0.11

The loop runs on this machine. These are the pressures the waves below take in order.

- A second person is not the synthetic script. The script builds one record, approves it in-process, and checks the packet. It does not follow the README, and it does not enable an adapter.
- A stored span is checked against the record at paste time. 0.12 marks the card when the text changes and keeps one previous span; it does not keep a hash of the record as it was at defend time.
- One posting is five commands: `match`, `gaps`, `tailor`, `packet`, `referees`. Rank order can quote the same record again and again.
- The same sentence can sit on several cards, and two approved cards can carry the same span under two claims. Review is still one card at a time.
- Refusals are stored and then left there. The half-overlap known gap in the bundled eval set closed in 0.12.
- The letter can only quote. It does not prefer a sentence you already wrote, and the other names already on a record stay off the card.
- A packet is for you. Its URIs are locker addresses. Export moves cards and spans without record bodies, and leaves answers behind on the way back in.

## Shipped (continued)

### 1.1 — The locker notices when evidence moves

Package 0.12. The 1.0 acceptance bar below does not move.

- Every specific token must be in the evidence. The two half-overlap questions in the golden set are refusals.
- Schema v3 stores a text hash. A text change marks citing cards `stale_reason=record_changed` and does not change status. `defend` keeps one previous span and clears the mark when it stores a new one.
- `dossier drift` reports stale cards, exact duplicate sentences, and URIs missed by the latest full walk of employer, notes, applications, git, or ics. `drop-record` removes one record only when no approved card cites it.
- `backup` verifies the copy. `restore` checks, and `--replace` swaps only after saving the live locker. `import` skips a card the locker cannot still carry.
- `match --postings` lists requirements that are gaps in two or more of up to 20 files.
- A workbench job left `queued` or `running` is shown as interrupted on the next start. `scripts/release/second_machine.sh` migrates a v2 fixture, checks a backup, and runs drift. CI runs that script.

## Waves

### 1.0 — Second machine

**Pressure.** The workbench loop shipped in 0.10 and the paste checks in 0.11. 1.0 is that loop on a machine that is not this locker, including a thin install with no warehouse.

**Ships.** The path a stranger can finish from the README: install with `uv`, `doctor`, enable only adapters they have, then ingest → extract → approve → defend → ask → packet. Brief, tailor, match, and referees stay optional steps on that same path. `[web]` stays optional. The CLI finishes without the workbench.

`scripts/release/second_machine.sh` stays the synthetic form. It keeps asserting the span cap, renderer read-back, and `dossier eval --retrieval` with the provider off. It is not the acceptance. Acceptance is a person, on a checkout that did not already contain `data/evidence.db`.

The 0.6 warehouse spot-check closes here as a human step: `make prove` (or `dossier prove`) on a real locker, ledger read, refusals and spanned lines checked, nothing committed. The ledger stays under the data directory.

**Done when.**

- A thin install and a warehouse install use the same commands. Two enabled adapters are enough to reach a buffet.
- Refusals that should refuse do refuse. Citations in an accepted answer resolve to hits. Every quoted span is at or under `SPAN_MAX` and still in its record.
- `dossier eval` passes. `doctor` on a default config prints `egress: no`. A remote completion prints the egress notice first.
- Twenty, when used, is the fixed people read. The client has no write of Tasks, Opportunities, Notes, or last-contacted.
- `python3 scripts/release/check_gitignore.py` passes on the tree that would be pushed. The real-locker prove ledger is not in that tree.
- The release is refused if a dump, an evidence DB, or a secret is tracked; if default config would leave egress on; if an adapter loads from an entry point; or if the image-less install in [install](install.md) has been replaced by a container.

**Holds.** 1.0 does not add accounts, sync, a plugin directory, a template gallery, or a required GUI. Office text stays capped record text. `sqlite-vec` and the PDF library stay optional extras. Pure Python is the floor.

### 1.1 — The quote remembers the record

Shipped in 0.12. See the section above. What remains for a later pass: a hash stored beside the span at defend time (0.12 hashes the record and marks the card), and an import that lands a mismatched approved card as `pending` instead of skipping it.

### 1.2 — One sitting

**Pressure.** A posting you might answer is a scatter of files: a match, a coverage list, a CV, a letter, a packet, a referee list. Rank order will spend the letter on one record.

**Ships.** `dossier sit --posting` writes one folder, `data/sittings/<stamp>/`, and approves nothing.

- `match.md` — requirements in spec order, the same caps and gap lines as `match`
- `cv.md` and `letter.md` — one typed draft, laid out by the renderer you ask for (`html`, `docx`, `pdf` with the `render` extra). Default is markdown
- `packet.md` — only the cards the draft quoted
- `referees.md` — the shortlist, the confirm-before-listing line, and no name copied into the CV or the letter
- `cover.md` — empty lenses, unspanned cards, requirements with no carrying sentence, and the spans the budget dropped

Selection is deterministic. Cover a requirement that has a carrying span before a second span from the same record. A letter has a span count, a per-record cap, and a character budget; the defaults are printed in `cover.md` and can be overridden for that command. A dropped span is listed with the reason `budget` or `same record`. `--arrange` stays letter-only and off. It may emit only the selected spans plus “I am applying for the role in the posting.” Any other sentence keeps the deterministic letter.

The workbench gains a Sitting page. Match can open it with the same posting, the way it already opens Tailor. Tailor, packet, and referees stay their own commands; `sit` calls them.

**Done when.** Every quoted line in the folder is a stored span still in its cited record. A requirement with no such sentence remains in `match.md`. Referee names appear only in `referees.md`. A fixture with five spans from one record quotes the first and lists the rest in `cover.md`. Pending cards and approved cards with no span stay out of the quote.

**Holds.** The folder is what you read before you apply by hand. `sit` does not open a browser, fill a portal, send mail, or write Twenty. It does not summarize a gap into a new sentence. Another file format, if it ships here, is another renderer of the same runs. CV and letter stay the two layouts. A template gallery stays outside.

### 1.3 — Echoes and clashes

**Pressure.** Extract will not open a second card on a record that already has one. The same claim still arrives from three records, and two approved cards can paste the same sentence under two claims. The queue treats them as strangers.

**Ships.** An echo is deterministic: the same normalized claim, or the same stored span, on more than one card. Review and `buffet` group them and show the count. Approving one card leaves the others pending. `approve --group` is explicit, prints every id it will change, and still refuses a member whose own record does not carry the sentence. Refuse stays per card.

A clash is smaller than a disagreement. `audit-cards` lists two shapes and changes nothing: the same stored span under two claims, or the same normalized claim with two spans that are not the same sentence. Undated records and ordinary overlap are unchecked, and the report says so. `doctor --deep` prints the count.

**Done when.** A fixture with three cards and one sentence shows one group. `approve` of one id leaves two pending. `approve --group` approves only the members that still carry. A clash fixture stays approved and appears on the audit list.

**Holds.** Echoes are not clusters and not a model judgment. Approving does not cascade unless you pass `--group`. A clash does not pick a winner. Lenses stay the closed set in `lenses.py`.

### 1.4 — The printed gaps shrink

**Pressure.** The golden set is honest about a hole and then ignores it. A question that shares only half its words with a record can still be answered, the run says so, and the exit code stays zero. Briefs store refusals and never look at them again.

**Ships.** Half overlap is a refusal unless an approved span carries the question under the full rule: every content word, and one of them specific. `exact` stays the floor — quote or refuse, no model. A paraphrase with no specific shared word refuses. A neighbor still has to carry the sentence; cosine and recall@k do not promote it.

Each `known_gap` case keeps a one-line reason. `eval` prints them, as now. The run fails when a case is marked `known_gap` without that reason, or when the set of gap ids grows without the reason being part of the case. Closing a gap deletes the mark. It does not hide the printout of whatever remains.

`dossier gaps` grows a second list from refused answers already stored: the question, the refusal reason, and the ingest or extract hint it would have printed for an empty lens. It does not re-ask and does not ingest.

**Done when.** The current half-overlap case either refuses or stays on the list with a reason, and a new unmarked `known_gap` fails `eval`. A fixture that refused the same question twice shows it once on `gaps`, beside the command you would run yourself.

**Holds.** This wave tightens carry. It does not add a grader model, a leaderboard, or a retrieval score that can override a missing sentence. Known leniency stays visible until it is gone.

### 1.5 — Already in the record

**Pressure.** People will ask the letter to sound like them, and will ask who else could speak to a line. The sentences and the names are often already in the locker. A style model and a typed-in witness both invent a person who was not there.

**Ships.** A register mark is a flag on an approved, spanned card (`dossier register` / `dossier register --clear`). Pending cards cannot take it. The span must still sit in the cited record. When several spans carry one requirement, `tailor` and `sit` prefer a register span, then the ordinary rank. `--arrange` may order register spans, the other selected spans, and the one fixed application sentence. A register span is still a quote. Clearing the mark leaves the card approved.

A witness is a name copied from the cited record at `defend` time: another author on a pubs record, or another named speaker on a meeting record. It is stored on the card as that name. Git stays one author and still stores no patch bodies, so it adds no witness. `referees` may rank a witness who already sits on a spanned card the posting matched, inside the same cap of seven people and two claims, with the confirm line. The CV and the letter gain no witness line. The packet may list “also in the record” under the quote.

**Done when.** A fixture with two carrying spans quotes the registered one first. A span that has left its record cannot be registered and is not preferred. A pubs coauthor already on the record appears on the card and in the referee shortlist, and in neither the CV nor the letter. A name that is only in a people file, and not on the record, is not stored as a witness.

**Holds.** There is no tone control, no paraphrase, and no fine-tune. Refused cards stay out of the register. A witness is not attached to an application, not mailed, and not written to Twenty. You still confirm before listing.

### 1.6 — A packet with the doors shut

**Pressure.** `export` already leaves record bodies behind and then `import` (as of 1.1) will not quote a span this locker lacks. The packet you would hand someone still contains locker URIs, and a second locker on the same machine is only an environment variable with no check that you opened the one you think you opened.

**Ships.** `dossier packet --redact` and `dossier sit --redact` write the quotes, the claims, the lens and kind, and the record titles. They omit record URIs and file paths. The file says, in a fixed line, that a recipient cannot check the quotes. Verification stays on the machine that holds the locker: the same paste-time check as 0.11, against the unredacted packet.

`doctor` prints the data directory and the schema version on the first line, so two lockers side by side are obvious. `DOSSIER_DATA` remains the way you choose one. The export file records its schema generation and still contains no record bodies. `import` refuses a file from a newer generation than the destination locker.

**Done when.** A redacted packet fixture has quotes and titles and no `://` URI. Its fixed line says it cannot be checked elsewhere. `doctor`’s first line names the directory. An export from a newer generation is refused by `import`, and the destination locker is left untouched.

**Holds.** Redaction is not a signature, not a share link, and not a sync. There is no account and no second search product. The full locker does not leave the machine as part of this wave.

## Asked, and held

These requests will keep arriving. They are the boundaries, written as the requests themselves, so they are not reopened as features.

| Request | Where it stops |
| --- | --- |
| Log into a portal and file the application | You apply by hand. `sit` writes a folder |
| A national CV form, or a gallery of templates | JSON Resume is data. A renderer lays out the same spans. Two plain layouts are enough |
| Rewrite the span so it fits, or match the posting’s tone | The span is a quote. `--arrange` may reorder quotes and one fixed sentence |
| Remember the referee on the application | The shortlist says to confirm. The name stays off the draft and out of Twenty |
| Sync two machines, or sign in | 1.0 is a second install. 1.6 is a redacted file and a second `DOSSIER_DATA` |
| A plugin for the source you have | Register the adapter in `CONTRIBUTIONS` |
| Embed the Zotero library, or walk Sent Mail | The named collection, and one allowlisted message under the cap |
| Let recall or a grade outvote a missing sentence | Carry stays the rule. Metrics describe retrieval. They do not quote |

## Boundaries that stay

These are not delayed features. They are refuse lines.

- No Twenty writes (Tasks, Opportunities, Notes, last-contacted)
- No auto-attach of a referee name to an application
- No cloud LLM default. Text leaves the machine only when the provider is `litellm` or `DOSSIER_LLM_ALLOW_REMOTE` is set. The CLI prints an egress notice first. `dossier doctor` reports `egress: no` or `egress: yes`
- No walk of a blocked mail tree; no Sent Mail as a folder walker; no re-embed of a Zotero library you did not name
- No plugin directory or entry-point scan
- No Docker image for the locker. It installs with `uv` on the host. Publications are the named Zotero collection, read in-process. No compose server, and no re-embed of a Zotero library you did not name
- Dumps, warehouse, LanceDB, `evidence.db`, `.env`, mbox, and PDFs stay off git. Before every push, `python3 scripts/release/check_gitignore.py` must pass
- No sentence in a CV, letter, packet, or sitting that was not already a stored span, an approved claim, a heading, a fixed label, or the one fixed application sentence
- No approval, mail, or Twenty write inside `prove`, `run`, `sit`, `gaps`, or `audit-cards`
