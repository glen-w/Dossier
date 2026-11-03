# Architecture

Type: ARCHITECTURE
Authority: Pipeline shape and where an adapter plugs in. What a command refuses lives in [status](status.md).

```text
adapters you enable
    → local corpus (data/evidence.db, gitignored)
        → dossier index (passage vectors in that same file; paged, resumable)
        → deterministic drafts, then the fast model for what is left
            → human gate (buffet, approve, refuse, reopen, review)
                → buffet of cards you can paste
                    → defend stores the carrying sentence
                        → data/packets when you write a packet
                        → data/drafts when you tailor a posting (markdown, html, docx, pdf)
        → interview ask (approved claim, full text, vectors when thin, hops, one answer-model completion)
            → cited answer, or a refusal
            → data/briefs when you run a question pack
            → data/matches when you match a job spec (evidence per requirement)
```

Ask reads records already in the corpus, then the passage vectors in that same file when full text is thin. A quoted span is one paste-sized sentence (`SPAN_MAX`, default 320). A cosine neighbor must still carry the question. Full text names the candidate records first, and only those load; vector search is a streaming scan, or the same scan in C with the optional `vec` extra (`src/dossier/vecindex.py`). The order — approved card, quote, hops, one completion — lives in [status](status.md).

The locker is a host process: `uv run dossier` on the machine that holds the folders, the SQLite file, and Ollama on loopback. There is no image. See [install](install.md). Shared product words (locker, source, extract, card, ask, effort, profile) live in [vocab](vocab.md).

## Source protocol

One adapter per source. Register it by appending `CONTRIBUTIONS` in `src/dossier/contributions.py`. Adapters are not discovered from a plugins folder.

- `detect(path)` — this adapter owns the file or folder
- `load(path, corpus)` — write records into the local corpus
- `tables()` — record names this source provides

`load` copies text into Dossier’s SQLite file. It does not create a second export warehouse. LinkedIn reads an existing DuckDB file. ChatGPT and Slack read that warehouse or an export you point at. Mail seeks Gloda in the warehouse, then fetches selected bodies; a thin user can point at one exported folder. Git and employer read only paths you list. See [seekers](seekers.md) and [adapters](adapters.md).

## After ingest

Drafts, the human gate (`buffet`, `approve`, `refuse`, `reopen`, `review`), defend, packet, gaps, and ask are described in [status](status.md). This page does not restate those rules. `dossier index` writes passage vectors into the same SQLite file. It does not open a second store.

## Locker schema

`evidence.db` carries a schema version (v3). Each record stores a SHA-256 of its text. `Corpus` runs numbered migrations in order on open and, when the locker already holds records, copies it to `evidence.pre-v<N>.db` first. A locker from a newer Dossier is refused. A text change marks citing cards stale and does not approve them. Behaviour: [status](status.md).

## Rendering a draft

`tailor` builds one typed `DraftDoc` (`src/dossier/render.py`) from spanned approved cards, then lays it out as markdown, HTML, DOCX, or PDF. A renderer adds no prose. Every text run is a stored span, an approved claim, a lens heading, the name or contact line from config, a citation URI, or a fixed label, and the tests read each format back to check it. Rendering makes no network call.

## Wired adapters

`pubs`, `chatgpt`, `linkedin`, `applications`, `transcripts`, `slack`, `mbox`, `meetings`, `employer`, `git`, `notes`, `ics`. Behaviour and limits: [status](status.md).

## Referee shortlist

`dossier referees` reads a JSON file or a Twenty GraphQL read. It does not write Tasks, Opportunities, Notes, or a last-contacted field, and it does not attach a name to an application. Ranking detail is in [status](status.md).

## Roadmap

Versioned waves; 0.11 shipped the paste-time span check, 0.12 (wave 1.1) notices when a record's text changes, and 1.0 is the second-machine tag. Later waves stay in [roadmap](roadmap.md).
