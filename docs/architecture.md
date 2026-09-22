# Architecture

Type: ARCHITECTURE
Authority: Pipeline shape and where an adapter plugs in. What a command refuses lives in [status](status.md).

```text
adapters you enable
    → local corpus (data/evidence.db, gitignored)
        → dossier index (passage vectors in that same file)
        → deterministic drafts, then the model for what is left
            → human approve
                → buffet of cards you can paste
                    → defend stores the carrying sentence
                        → data/packets when you write a packet
                        → data/drafts when you tailor a posting
        → interview ask (approved claim, full text, vectors when thin, hops, one completion)
            → cited answer, or a refusal
            → data/briefs when you run a question pack
```

Ask reads records already in the corpus, then the passage vectors in that same file when full text is thin. The order — approved card, quote, hops, one completion — and when a neighbor is quoted live in [status](status.md).

The locker is a host process: `uv run dossier` on the machine that holds the folders, the SQLite file, and Ollama on loopback. There is no image. See [install](install.md).

## Source protocol

One adapter per source. Register it by appending `CONTRIBUTIONS` in `src/dossier/contributions.py`. Adapters are not discovered from a plugins folder.

- `detect(path)` — this adapter owns the file or folder
- `load(path, corpus)` — write records into the local corpus
- `tables()` — record names this source provides

`load` copies text into Dossier’s SQLite file. It does not create a second export warehouse. LinkedIn reads an existing DuckDB file. ChatGPT and Slack read that warehouse or an export you point at. Mail seeks Gloda in the warehouse, then fetches selected bodies; a thin user can point at one exported folder. Git and employer read only paths you list. See [seekers](seekers.md) and [adapters](adapters.md).

## After ingest

Drafts, the human approve gate, defend, packet, gaps, and ask are described in [status](status.md). This page does not restate those rules. `dossier index` writes passage vectors into the same SQLite file. It does not open a second store.

## Wired adapters

`pubs`, `chatgpt`, `linkedin`, `applications`, `transcripts`, `slack`, `mbox`, `meetings`, `employer`, `git`. Behaviour and limits: [status](status.md).

## Referee shortlist

`dossier referees` reads a JSON file or a Twenty GraphQL read. It does not write Tasks, Opportunities, Notes, or a last-contacted field, and it does not attach a name to an application. Ranking detail is in [status](status.md).

## Roadmap

Versioned waves; 0.9 ships tailor from spanned approved cards. Next is 0.9→1.0 user testing: [roadmap](roadmap.md).
