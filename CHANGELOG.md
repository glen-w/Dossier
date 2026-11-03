# Changelog

## 1.0.0

Second-machine release of the locker loop.

- A thin install and a warehouse install use the same commands. `scripts/release/second_machine.sh` is the synthetic path: ingest through packet, golden eval, a v2 migrate, backup, restore check, and drift. CI runs it.
- `python3 scripts/release/check_gitignore.py` is required before every push. Default `doctor` prints `egress: no`.
- The 0.12 locker is in this tag: tighter carry, stale cards, `drift`, checked `restore`, and the renderer.
- A warehouse `make prove` on a real locker stays a human step. Its ledger stays off git.

## 0.12.0

The locker notices when evidence moves.

- A question or claim is carried only when every specific word is in the evidence. Generic words may still overlap in part. The bundled golden set no longer treats a mixed question as a known gap.
- Schema v3 stores `text_hash` and `text_changed_at`. Changing a record's text marks citing cards `stale_reason=record_changed` without changing status or dropping the span. `defend` keeps the previous span in `span_prev` and clears the mark when it stores a new one.
- `dossier drift` lists stale cards, exact duplicate sentences, and URIs a full walk missed. `dossier drop-record` removes one record only when no approved card cites it.
- `backup` checks integrity and counts. `restore` is check-only unless `--replace`. `import` skips a card the locker cannot still carry and does not replay answers.
- `match --postings` writes requirements that are gaps in two or more of up to 20 files.
- A workbench job left running is marked interrupted on the next start. The drift page only reads.

## 0.11.0

Evidence you can paste, and retrieval that scales.

- `tailor`, `packet`, and `match` quote a stored span only while it is still in its cited record. `audit-cards` names a span the record no longer holds.
- A golden eval of about sixty synthetic cases (refusals, paraphrases, injected text, odd characters) runs against a throwaway locker. Known leniency is printed on every run. `dossier eval --retrieval` reports recall@k and MRR with a deterministic embedder.
- Property tests for the span cap, the citation rule, and the paste path. Docs-drift tests for commands and environment variables.
- Store schema v2 with numbered migrations, an automatic copy of a locker with records before it migrates, and a refusal to open a locker from a newer Dossier. Vector size is stored; a model that changes size is refused.
- `ask` loads only the records and passages full text names, not the whole locker. Vector search streams rows; with `uv sync --extra vec` it runs in C through `sqlite-vec` (`DOSSIER_VEC` picks the backend).
- `dossier index` is paged and resumable, with `--sources` and `--limit`, and the workbench job can cancel without losing finished pages. `scripts/bench_retrieval.py` times it on a generated locker.
- `tailor --format html|docx|pdf` and `--with-sources`, from one typed draft. The renderer adds no prose; tests read each file back. PDF needs the `render` extra and uses a bundled DejaVu Sans. The workbench Tailor page picks a format and links the download.

## 0.10.0

Engineering gates and the carrying-sentence contract.

- Interpreter pin (`.python-version` 3.13), ruff, mypy, coverage, CI, and pre-commit.
- A stored span is one paste-sized sentence (`SPAN_MAX`, default 320). A claim with no content words is refused. `defend --refresh` re-spans under the new rule; `audit-cards` lists approved cards that would now be refused.
- Workbench CSRF, security headers, atomic config writes, pack-path allowlist, and a body size cap.
- Store schema version, batch writes, a single-writer lock, and `dossier backup`.
- Shared `ops` implementations for CLI and workbench. Notes and calendar adapters. `dossier eval`, `export`/`import`, and a second-machine acceptance script. Prove, referees, and gaps are workbench pages; ask streams the cited answer.

## 0.9.0

`dossier tailor` writes CV or letter markdown from approved cards that
already have a span. A posting coverage list names kinds and skills with no
card. `--arrange` may reuse those spans for a letter and drops any other
sentence. Referee lines can note a pubs coauthor already in the corpus and up
to two claims they could speak to. Every line still says to confirm before
listing. Nothing is attached to an application.

The loopback workbench (`dossier gui`) covers locker, ingest, extract, review,
ask, match, tailor, packet, gaps, index, brief, and run, plus effort, saved
profiles, a prompt catalogue, phrase lists, and question packs. Ask, match,
and brief take `--sources`, `--year-from`, `--year-to`, and `--effort`.

## 0.8.0

Thin-user sources without the warehouse: allowlisted employer folders, a
ChatGPT export zip, a Slack export zip, and git history for repos you list.
An optional git author keeps other people's commits out.
Meetings read a TranscriptX library and store turns where you are a named
speaker. An exported mbox folder stops after a file cap.

`dossier index` stores passage vectors in `evidence.db`. `ask` can quote a
high-cosine neighbor when full text misses, and still refuses when no sentence
carries the answer. `gaps` names an ingest or extract command and does not run
it. `ask.pubs` can retrieve from the pubs server for that answer only.

## 0.6.0

Prove a disposable real-corpus pass (`dossier prove`), document a known-good
FTS5 interpreter in `doctor` and the install guide, and wire own-pubs HTTP
`POST /search` so retrieve can return rows once the pubs server is confirmed.
Product page (`website/`) plus Sphinx/MyST/Furo guide (`make pages-site`).
Live pubs ingest remains gated on the collection name and ~353-item scope.

## 0.5.0

`span`, `defend`, `gaps`, and `packet` show the sentence that carries a claim. `defend` stores the carrying sentence on the card and does not change its status. A sentence must carry the claim on its own; words spread across two sentences can still pass the whole-record check. Extract prompts no longer break when record text contains braces. Opening the corpus no longer rebuilds passages for empty records.

## 0.4.0

Interview ask over the local locker: approved cards first, passages, one Lens/Kind hop, compound questions, and a per-process call budget.
