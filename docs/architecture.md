# Architecture

```text
adapters you enable
    → local corpus (data/evidence.db, gitignored)
        → deterministic drafts, then the model for what is left
            → human approve
                → buffet of cards you can paste
                    → defend stores the carrying sentence
                        → data/packets when you write a packet
        → interview ask (approved claim, passages, one hop, then one completion)
            → cited answer, or a refusal
            → data/briefs when you run a question pack
```

`dossier ask` searches records already in the corpus. An approved claim that carries the question is preferred. SQLite FTS5 ranks title, text, and passages when it is available. A missing FTS module falls back to whole-word overlap, and overlap breaks ties among full-text hits. URIs and source names are not part of the index. After a miss, one hop can add the top hit’s `Lens` and `Kind` tokens and quote a span from any of the hopped hits. Compound questions may split and stitch without a model. Completions stay inside a per-process call budget. It does not embed records, and it does not query the publications server. `exact` never calls a model. See [status](status.md) and [roadmap](roadmap.md).

## Source protocol

One adapter per source. Register it by appending `CONTRIBUTIONS` in `src/dossier/contributions.py`. Adapters are not discovered from a plugins folder.

- `detect(path)` — this adapter owns the file or folder
- `load(path, corpus)` — write records into the local corpus
- `tables()` — record names this source provides

`load` copies text into Dossier’s SQLite file. It does not create a second export warehouse. ChatGPT, LinkedIn, and Slack only read an existing DuckDB file. Mail seeks Gloda in that warehouse, then fetches selected bodies. See [seekers](seekers.md).

## Claim rule

A proposed claim becomes `pending` only when every citation resolves to corpus text and that text can carry the sentence. Otherwise the card is stored as `refused`, with a reason. `dossier approve` accepts a pending card. Refused cards stay refused until a better record exists.

Extraction writes a draft card when the sentence is already in a LinkedIn row or a seeker record, then asks the configured model for JSON claims on the rest. The model does not get to mark a card approved. `DOSSIER_LLM_PROVIDER=off` leaves only the drafts.

`dossier defend` stores a carrying sentence on a pending or approved card (`extras.span` and `extras.span_uri`). That check is one sentence, stricter than the whole-record rule above. It does not change status. `dossier packet` writes markdown for the approved cards that have a span under `data/packets/`. `dossier gaps` counts Lens and Kind headers already on records. None of these calls a model.

## Wired adapters

`pubs`, `chatgpt`, `linkedin`, `applications`, `transcripts`, `slack`, `mbox`. Behaviour and limits: [status](status.md).

## Referee shortlist

`dossier referees` reads people you already keep and prints at most seven names. Rank is local scoring: hiring-firm overlap first, then shared words with title, keywords, bio, and notes, then closeness from a note, a timeline event, and an existing last-contact time. It does not call a model.

People come from a JSON file, or from a GraphQL read when `DOSSIER_TWENTY_API_URL` and `DOSSIER_TWENTY_API_KEY` are both set. That read loads People, company name, note text, and whether a timeline event exists. It does not write Tasks, Opportunities, Notes, or a last-contacted field. Skips and scarce-name warnings live in a local policy file, not in this repo. Each printed line ends with “confirm before listing.” The command does not attach a name to a PDF and it does not send mail.

## Roadmap

Next and later work, including own-pubs ingest, a real-corpus pass, employer-folder allowlist, hybrid search, and CV/letter tailoring: [roadmap](roadmap.md).
