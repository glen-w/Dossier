# Architecture

```text
adapters you enable
    → local corpus (data/evidence.db, gitignored)
        → deterministic drafts, then the model for what is left
            → human approve
                → buffet of cards you can paste
        → full-text ask (exact quote, then one completion)
            → cited answer, or a refusal
            → data/briefs when you run a question pack
```

`dossier ask` searches records already in the corpus. SQLite FTS5 ranks them when it is available; whole-word overlap is the fallback and the tie-break. It does not embed them, and it does not query the publications server. `exact` never calls a model. See [status](status.md).

## Source protocol

One adapter per source. Register it by appending `CONTRIBUTIONS` in `src/dossier/contributions.py`. Adapters are not discovered from a plugins folder.

- `detect(path)` — this adapter owns the file or folder
- `load(path, corpus)` — write records into the local corpus
- `tables()` — record names this source provides

`load` copies text into Dossier’s SQLite file. It does not create a second export warehouse. ChatGPT, LinkedIn, and Slack only read an existing DuckDB file. Mail seeks Gloda in that warehouse, then fetches selected bodies. See [seekers](seekers.md).

## Claim rule

A proposed claim becomes `pending` only when every citation resolves to corpus text and that text can carry the sentence. Otherwise the card is stored as `refused`, with a reason. `dossier approve` accepts a pending card. Refused cards stay refused until a better record exists.

Extraction writes a draft card when the sentence is already in a LinkedIn row or a seeker record, then asks the configured model for JSON claims on the rest. The model does not get to mark a card approved. `DOSSIER_LLM_PROVIDER=off` leaves only the drafts.

## Wired adapters

`pubs`, `chatgpt`, `linkedin`, `applications`, `transcripts`, `slack`, `mbox`. Behaviour and limits: [status](status.md).

## Referee shortlist

`dossier referees` reads people you already keep and prints at most seven names. Rank is local scoring: hiring-firm overlap first, then shared words with title, keywords, bio, and notes, then closeness from a note, a timeline event, and an existing last-contact time. It does not call a model.

People come from a JSON file, or from a GraphQL read when `DOSSIER_TWENTY_API_URL` and `DOSSIER_TWENTY_API_KEY` are both set. That read loads People, company name, note text, and whether a timeline event exists. It does not write Tasks, Opportunities, Notes, or a last-contacted field. Skips and scarce-name warnings live in a local policy file, not in this repo. Each printed line ends with “confirm before listing.” The command does not attach a name to a PDF and it does not send mail.

## Later

- **Ask-the-corpus, beyond full text.** `dossier ask` cites hits from `evidence.db`. A hybrid or embedding index is a later backend. It is not required for the command to exist.
- **More sources.** Employer-named folders (an explicit allowlist), git history, and meeting exports. Mail and Slack adapters already exist; they seek selected rows and do not ingest a whole mailbox or workspace.
- **Tailoring.** A posting in, a CV or letter out, using approved cards only. A PDF renderer stays out of the locker.
