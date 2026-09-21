# Changelog

## Unreleased

`meetings` seeks a TranscriptX library for meetings where you are a named
speaker and stores your turns. It does not import TranscriptX or copy the
library.

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
