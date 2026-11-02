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
| **Review** | The human gate on the workbench: approve, refuse, reopen, defend. The CLI list command stays `buffet`. |
| **Span / defend** | The one sentence that carries the claim; `defend` stores it on the card. |
| **Packet** | Markdown of spanned approved cards under `data/packets/`. |
| **Drift** | Stale cards, duplicate sentences, and full-walk URIs the last ingest missed. It does not delete or approve. |

## Answers and employment kit

| Term | Meaning |
| --- | --- |
| **Ask** | One cited answer from the locker, or a refusal. |
| **Match** | Ordered evidence for each requirement in a pasted job spec, under `data/matches/`. |
| **Chat** | Streamed cited ask on the workbench ask page. Follow-up is another question on that page. |
| **Pack** | A list of questions for a brief. Not a prompt. |
| **Brief** | Answers to a pack, under `data/briefs/`. |
| **Tailor** | Posting-shaped CV or letter under `data/drafts/`, as markdown, HTML, DOCX, or PDF. |
| **Prove** | Disposable corpus pass; never approves. |
| **Run** | Ingest, extract, then brief on the real locker. |
| **Job** | One workbench background task (ingest, ask, …). The strip polls only while busy; Cancel cooperates with progress callbacks. History lives under `$DOSSIER_DATA/jobs/`. Errors and result counts show on the page. |
| **Eval** | Synthetic golden set (`dossier eval`). Reports refusal precision and citation validity. |
| **Backup** | Consistent copy of `evidence.db` via the SQLite backup API. |

## Config surface

| Term | Meaning |
| --- | --- |
| **Answer model** | `[llm] model`. Ask and brief. Default `qwen3.8:latest`. |
| **Fast model** | `[llm] fast`. Extract, the employer folder filter, the ask planner, and letter arrange. Default `qwen2.5:3b`. Thinking is off and the reply stops at 512 tokens. A missing tag uses the first installed alternate (`qwen2.5:7b`, `llama3.2:3b`, `qwen3:4b`, `gemma3:4b`), then the answer model. JSON on a thinking tag (`qwen3`, `deepseek-r1`, `gpt-oss`) also turns thinking off. |
| **Effort** | Global LLM investment: `light`, `balanced`, or `high`. Balanced uses the fast model for extract and the answer model for ask. Light drafts without a model. High uses the answer model for both, and sets a context cap and a timeout. |
| **Profile** | A named saved overlay of tunable knobs. Not identity, not effort itself, not a referee. |
| **Scope** | Sources, year range, and effort for one ask, match, or brief. Defaults live in settings and in a profile. |
| **Identity** | Slack ids, speaker names, and the mail-folder map in gitignored `dossier.toml`. |
| **Phrase list** | Built-in include and exclude words for a source. The workbench edits them in that same file. |
| **Prompt** | A versioned template for extract, ask, or tailor. |
| **Pack** | A list of questions for a brief. Not a prompt. |

## Collisions to keep straight

- **contributions** names both the adapter registry (`CONTRIBUTIONS`) and a lens. Say “adapter registry” or “contributions lens” when the distinction matters.
- A referee “could speak to” a claim is not a **profile**.
