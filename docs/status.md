# Status

Dossier 0.6 proves the locker on a disposable real-corpus pass (`dossier prove`), can retrieve own-pubs rows over HTTP when a pubs `/search` answers, and ships a product page plus Sphinx guide. Retrieval still prefers a quote. When one span is not enough, it can stitch compound questions, hop once on seeker headers, and call a local model only inside a call budget. Fixture tests are green. A full warehouse prove and live pubs ingest (after collection confirm) are still human steps.

## Works

- SQLite corpus and claim cards (`pending`, `approved`, `refused`) under `data/evidence.db`. Accepted and refused answers are stored in the same file and are not claim cards. Long records are split into passages stored beside them.
- Refuse rule: no citation, a citation that is not in the corpus, or evidence text that does not carry the sentence.
- CLI: `ingest`, `extract`, `buffet`, `approve`, `ask`, `brief`, `run`, `span`, `defend`, `gaps`, `packet`, `prove`, `doctor`, `referees`.
- `prove` — disposable `DOSSIER_DATA`, capped adapters (default linkedin/chatgpt/applications), exact brief, defend/packet, ask smoke, `ledger.json`. Never approves. Fails closed without FTS5 unless `--allow-overlap`.
- Optional `$DOSSIER_DATA/dossier.toml` (gitignored). Environment variables override it. `dossier.example.toml` lists the knobs. Defaults: Ollama on loopback, `ask.mode = auto`, full text on, extract may call the model, at most six model calls per process.
- `extract` writes a pending card from LinkedIn rows and from seeker records that already carry a Lens and Kind header, using only words in that record. Records that already have a pending or approved card are left alone. The model sees only what is left, and only when extraction is on and the provider is not `off`.
- `ask` modes: `exact` quotes a span and never calls a model; `auto` (default) tries an approved claim, then a quote, then one hop on `Lens`/`Kind` that may open sibling records and quote any of them, then one completion when several hits tie or the span will not carry the question; `rich` always composes when there are hits unless an approved claim already carries the question. Retrieval uses SQLite FTS5 on title, text, and passages when that module is built in. Whole-word overlap is the fallback when full text cannot run, and it breaks ties when it can. An empty full-text result stays empty. A token inside a longer word does not count. Compound questions can split into at most four parts. The answer is printed only when every citation is one of the hits and the cited text can carry the sentence. No hits, an empty question, a citation outside the hits, or an unsupported sentence is a refusal. `--source`, `--lens`, and `--kind` limit the search. At most 8 hits go into the prompt. `--follow` adds up to three earlier accepted answers as context. Those lines are not citations.
- `brief` runs the built-in `career` pack, a local `posting` pack, or a JSON pack you pass, and writes `data/briefs/<stamp>.md`. After a refusal it may add one closed follow-up. `run` ingests adapters it can already detect, drafts cards, optionally extracts, writes that brief, and prints a ledger of records, skipped adapters, model calls, and whether egress was possible. Neither command approves a card.
- `span` prints the shortest non-header sentence that carries a claim, plus the record title and URI. `--uri` and `--source` narrow the search. No model. An empty claim, or no single sentence, is a refusal.
- `defend` walks pending and approved cards. When one cited record contains that sentence, it stores `span` and `span_uri` on the card. It does not change status and it does not approve. Cards with no such sentence print as `unspanned`. The whole-record check can still pass when the words are spread across sentences; `span` and `defend` require one sentence.
- `gaps` counts seeker `Lens` and `Kind` headers on records, lists lenses with zero records, and lists approved cards that are the only spanned card for their lens and kind. No model.
- `packet` writes `data/packets/<stamp>.md` from approved cards that already have a span: the claim, lens and kind when present, the sentence as a quote, and the URI. Approved cards without a span are listed under “Not included” and are not quoted. No model.
- `doctor` prints the data directory, python executable, SQLite version, whether FTS5 is available, the provider, the call budget, pubs URL, and which adapters detect (pubs includes a row count from `/search` when the server answers). It does not write.
- `referees` prints at most seven people for a posting. Rank is local (hiring-firm overlap, shared words, note, timeline, existing last-contact time). It does not call a model. People come from `--people` / `DOSSIER_PEOPLE`, or from Twenty when both API env vars are set. No people source exits without ranking. A policy file can skip names, warn on scarce names, and alias employers. Every line says to confirm before listing. The command does not write the corpus or Twenty, and it does not send mail.
- Ollama on loopback by default. LiteLLM is optional and prints an egress notice when a completion can leave the machine.
- Eight adapters, registered by hand in `src/dossier/contributions.py`.
- Product page under `website/` and Sphinx guide under `docs/` (`make pages-site`).

## Adapters, as they behave today

| Adapter | What `ingest` does now |
| --- | --- |
| `pubs` | Loads a JSON fixture in tests. Against a live URL it pings `/health` or `/`, then `POST /search` maps hits into records. Empty until the pubs server returns hits. It does not embed a Zotero library and it does not download PDFs. |
| `chatgpt` | Reads `chatgpt.messages` (and conversation titles when present) from a DuckDB file you already have. It does not unpack a ChatGPT export zip. |
| `linkedin` | Reads `positions`, `education`, `skills`, and `publications` from that same warehouse. It skips the rest of a LinkedIn archive. |
| `applications` | Walks one folder whose name contains “job application” (or is `applications`). Text files are stored. Other files are inventory lines only; PDF bytes are not read. |
| `transcripts` | Reads Cursor `agent-transcripts/*.jsonl` user queries, and JSON blobs in a folder you point at. Binary blobs are skipped. Nothing from these paths is written to git by the adapter. |
| `slack` | Seeks Glen-touched rows in warehouse `slack.*` (files, hot threads, mentions, channel samples). Applies diversity quotas. Fetches selected message text plus tight thread context. Does not unzip the export or copy a channel. |
| `mbox` | Seeks Thunderbird Gloda metadata (activity folders, sent+documents). Fetches **one** allowlisted mbox body under a size cap via rollup `parse_message` (stdlib fallback). Never streams IDDRI or Sent Mail. Thin user: one small exported folder. |
| `meetings` | Seeks a TranscriptX library (or a folder of JSON plus speaker-map sidecars) for meetings where you are a named speaker. Stores your turns, under the usual lenses, and applies seeker quotas. Does not import the TranscriptX package or copy the library. Placeholder `SPEAKER_00` labels, ignored speakers, solo notes, conflicted copies, and `__inbox` duplicates are skipped. |

ChatGPT, LinkedIn, and Slack expect the warehouse schema produced elsewhere (see [prior art](prior-art.md)). Point `DATA_DUMPS_WAREHOUSE` at `catalog.duckdb`.

## Not in this version

See [roadmap](roadmap.md) for waves 0.7–0.9 and 0.9→1.0 user testing. Still out of 0.6:

- Live pubs ingest (compose up) until the collection name and ~353 scope are confirmed.
- Embeddings, LanceDB inside Dossier, or hybrid ask (0.8). Full text and passages stay inside `evidence.db` unless pubs HTTP returns rows.
- A CV or letter renderer. Briefs are markdown under `data/`. Posting packs answer questions; they do not write a tailored CV.
- Employer-folder walking or git history (0.7). The meetings lane reads a TranscriptX library already.
- A plugin loader.

## Tests

`uv run pytest` uses synthetic rows only. Fixtures live in `tests/fixtures/`. Do not add real mail, dumps, or PDFs to the tree. `make prove` is local-only against sources on disk.
