# Vocabulary

Type: GUIDE
Authority: Shared product words for the CLI, docs, and workbench. Pipeline shape lives in [architecture](architecture.md).

Use these words in the GUI and in new docs. Prefer the locked term over a synonym.

## Locker and warehouse

| Term | Meaning |
| --- | --- |
| **Locker** | The SQLite file `evidence.db` and the host process around it (`Corpus`). |
| **Warehouse** | The read-only DuckDB catalog used by some adapters. Separate from the locker. |

## Sources and ingest

| Term | Meaning |
| --- | --- |
| **Source** | One registered adapter (see `CONTRIBUTIONS`). Ingest loads it. There is no plugin scan. |
| **Ingest** | Copy adapter text into the locker. |
| **Seek** | Quota’d metadata hunt (mail, Slack, meetings). Not ingest. |
| **Fetch** | One capped body or snippet after a seek. Not ingest. |
| **Record** | Text copied into the locker. |
| **Passage** | A chunk of a record. Embedded by `dossier index`. |

## Claims and the human gate

| Term | Meaning |
| --- | --- |
| **Extract** | Propose claim cards from records. |
| **Draft** | A model-free claim sentence inside extract. Tailor output is never a “draft” in the GUI. |
| **Card** | One claim: `pending`, `approved`, or `refused`. |
| **Lens / kind** | Closed facets on a card. |
| **Review** | The human gate: approve, refuse, reopen. The CLI list command stays `buffet`. |
| **Span / defend** | The one sentence that carries the claim; `defend` stores it on the card. |
| **Packet** | Markdown of spanned approved cards under `data/packets/`. |

## Answers and employment kit

| Term | Meaning |
| --- | --- |
| **Ask** | One cited answer from the locker, or a refusal. |
| **Chat** | Later multi-turn ask. Wave 1 of the workbench does not use this word. |
| **Pack** | A list of questions for a brief. Not a prompt. |
| **Brief** | Answers to a pack, under `data/briefs/`. |
| **Tailor** | Posting-shaped CV or letter under `data/drafts/`. |
| **Prove** | Disposable corpus pass; never approves. |
| **Run** | Ingest, extract, then brief on the real locker. |

## Config surface

| Term | Meaning |
| --- | --- |
| **Effort** | Global LLM investment: `light`, `balanced`, or `high`. |
| **Profile** | A named saved overlay of tunable knobs. Not identity, not effort itself, not a referee. |
| **Identity** | Slack ids, speaker names, and the mail-folder map in gitignored `dossier.toml`. |
| **Prompt** | A versioned template (later). A pack is questions, not a prompt. |

## Collisions to keep straight

- **contributions** names both the adapter registry (`CONTRIBUTIONS`) and a lens. Say “adapter registry” or “contributions lens” when the distinction matters.
- A referee “could speak to” a claim is not a **profile**.
