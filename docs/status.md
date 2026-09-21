# Status

Dossier 0.3 is a locker plus local ask over the same SQLite records. Retrieval is SQLite full text, with whole-word overlap as a fallback. A direct quote is preferred. The model is only asked to compose when that quote is not enough. It has been tested on synthetic fixtures. It has not been run as a full extract or ask over a real corpus in this repository’s history.

## Works

- SQLite corpus and claim cards (`pending`, `approved`, `refused`) under `data/evidence.db`. Accepted and refused answers are stored in the same file and are not claim cards.
- Refuse rule: no citation, a citation that is not in the corpus, or evidence text that does not carry the sentence.
- CLI: `ingest`, `extract`, `buffet`, `approve`, `ask`, `brief`, `run`, `referees`.
- Optional `$DOSSIER_DATA/dossier.toml` (gitignored). Environment variables override it. `dossier.example.toml` lists the knobs. Defaults: Ollama on loopback, `ask.mode = auto`, full text on, extract may call the model.
- `extract` writes a pending card from LinkedIn rows and from seeker records that already carry a Lens and Kind header, using only words in that record. Records that already have a pending or approved card are left alone. The model sees only what is left, and only when extraction is on and the provider is not `off`.
- `ask` modes: `exact` quotes a span and never calls a model; `auto` (default) tries that quote, then one completion when several hits tie or the span will not carry the question; `rich` always composes when there are hits. Retrieval uses SQLite FTS5 when that module is built in, and whole-word overlap otherwise. Overlap also breaks FTS ties. A token inside a longer word does not count. The answer is printed only when every citation is one of the hits and the cited text can carry the sentence. No hits, an empty question, a citation outside the hits, or an unsupported sentence is a refusal. `--source`, `--lens`, and `--kind` limit the search. At most 8 hits go into the prompt. `--follow` adds up to three earlier accepted answers as context. Those lines are not citations.
- `brief` runs the built-in `career` pack, or a JSON pack you pass, and writes `data/briefs/<stamp>.md`. `run` ingests adapters it can already detect, drafts cards, optionally extracts, then writes that brief. Neither command approves a card.
- `referees` prints at most seven people for a posting. Rank is local (hiring-firm overlap, shared words, note, timeline, existing last-contact time). It does not call a model. People come from `--people` / `DOSSIER_PEOPLE`, or from Twenty when both API env vars are set. No people source exits without ranking. A policy file can skip names, warn on scarce names, and alias employers. Every line says to confirm before listing. The command does not write the corpus or Twenty, and it does not send mail.
- Ollama on loopback by default. LiteLLM is optional and prints an egress notice when a completion can leave the machine.
- Seven adapters, registered by hand in `src/dossier/contributions.py`.

## Adapters, as they behave today

| Adapter | What `ingest` does now |
| --- | --- |
| `pubs` | Loads a JSON fixture in tests. Against a live URL it can ping the server. `records()` returns nothing. It does not embed a Zotero library and it does not download PDFs. |
| `chatgpt` | Reads `chatgpt.messages` (and conversation titles when present) from a DuckDB file you already have. It does not unpack a ChatGPT export zip. |
| `linkedin` | Reads `positions`, `education`, `skills`, and `publications` from that same warehouse. It skips the rest of a LinkedIn archive. |
| `applications` | Walks one folder whose name contains “job application” (or is `applications`). Text files are stored. Other files are inventory lines only; PDF bytes are not read. |
| `transcripts` | Reads Cursor `agent-transcripts/*.jsonl` user queries, and JSON blobs in a folder you point at. Binary blobs are skipped. Nothing from these paths is written to git by the adapter. |
| `slack` | Seeks Glen-touched rows in warehouse `slack.*` (files, hot threads, mentions, channel samples). Applies diversity quotas. Fetches selected message text plus tight thread context. Does not unzip the export or copy a channel. |
| `mbox` | Seeks Thunderbird Gloda metadata (activity folders, sent+documents). Fetches **one** allowlisted mbox body under a size cap via rollup `parse_message` (stdlib fallback). Never streams IDDRI or Sent Mail. Thin user: one small exported folder. |

ChatGPT, LinkedIn, and Slack expect the warehouse schema produced elsewhere (see [prior art](prior-art.md)). Point `DATA_DUMPS_WAREHOUSE` at `catalog.duckdb`.

## Not in this version

- Embeddings, LanceDB, or a call from `ask` into the publications server. Full text stays inside `evidence.db`.
- A CV or letter renderer. Briefs are markdown under `data/`.
- Employer-folder walking, git history, or meeting-export adapters.
- A plugin loader.

## Tests

`uv run pytest` uses synthetic rows only. Fixtures live in `tests/fixtures/`. Do not add real mail, dumps, or PDFs to the tree.
