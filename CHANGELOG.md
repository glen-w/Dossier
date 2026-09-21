# Changelog

## 0.5.0

`span`, `defend`, `gaps`, and `packet` show the sentence that carries a claim. `defend` stores that sentence on the card and does not change its status. A sentence must carry the claim on its own; words spread across two sentences can still pass the whole-record check. Extract prompts no longer break when record text contains braces. Opening the corpus no longer rebuilds passages for empty records.

## 0.4.0

Interview ask over the local locker: approved cards first, passages, one Lens/Kind hop, compound questions, and a per-process call budget.
