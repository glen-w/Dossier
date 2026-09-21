# Changelog

## 0.9.0

`dossier tailor` writes CV or letter markdown from approved cards that
already have a span. A posting coverage list names kinds and skills with no
card. `--arrange` may reuse those spans for a letter and drops any other
sentence. Referee lines can note a pubs coauthor already in the corpus and up
to two claims they could speak to. Every line still says to confirm before
listing. Nothing is attached to an application.

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

`span`, `defend`, `gaps`, and `packet` show the sentence that carries a claim. `defend` stores that sentence on the card and does not change its status. A sentence must carry the claim on its own; words spread across two sentences can still pass the whole-record check. Extract prompts no longer break when record text contains braces. Opening the corpus no longer rebuilds passages for empty records.

## 0.4.0

Interview ask over the local locker: approved cards first, passages, one Lens/Kind hop, compound questions, and a per-process call budget.
