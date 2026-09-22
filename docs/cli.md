# CLI

Type: GUIDE
Authority: How to run the commands and which knobs exist. What they refuse lives in [status](status.md).

```text
uv run dossier ingest --adapter applications ./path/to/applications
uv run dossier ingest --adapter slack
uv run dossier ingest --adapter mbox
uv run dossier ingest --adapter meetings
uv run dossier ingest --adapter employer
uv run dossier ingest --adapter git
uv run dossier extract --source slack
uv run dossier extract --limit 20
uv run dossier extract
uv run dossier buffet --status pending
uv run dossier approve <card-id>
uv run dossier approve --all --except chatgpt,git
uv run dossier refuse --all --source chatgpt
uv run dossier reopen <card-id>
uv run dossier review
uv run dossier span "synthetic paper on coastal governance"
uv run dossier defend
uv run dossier gaps
uv run dossier packet
uv run dossier tailor --posting ./posting.txt
uv run dossier tailor --posting ./posting.txt --kind letter --arrange
uv run dossier index
uv run dossier ask "what did I write about coastal governance?"
uv run dossier ask --mode exact --source pubs "coastal governance"
uv run dossier brief
uv run dossier brief --posting ./posting.txt
uv run dossier run
uv run dossier prove
uv run dossier doctor
uv run dossier referees --posting ./posting.txt --employer "Hiring Org"
```

`ingest --adapter employer` and `ingest --adapter git` use the folders and
repos in gitignored `data/dossier.toml` when you do not pass a path.

`dossier run` is ingest → extract → brief in one shot. Progress banners and
bars print on stderr while those phases work.

Split the pipeline when you want control:

- `DOSSIER_EXTRACT_LLM=0 uv run dossier extract` — deterministic drafts only
  (no Ollama). Fast on a large corpus.
- `uv run dossier extract --limit 20` — only the first N records without an
  open card; useful while tuning the model.
- `uv run dossier brief` — answer the question pack without re-ingesting or
  re-extracting.

`dossier approve --all` and `dossier refuse --all` change every pending card
that matches `--source` and skips `--except`. `dossier reopen` sends approved
or refused cards back to pending, one id or `--all` with the same filters.
A card id and `--all` cannot be combined. A name in both `--source` and
`--except` is skipped. A `--source` with no cards is reported and not treated
as a match.

`dossier review` serves one page on `127.0.0.1:8765` (override with `--port`).
Sources open into lens and kind groups. Approve or refuse applies to pending
cards in that group, that source, or one card. Reopen walks a card back to
pending. Source and group actions ask before they run. A claim search and the
first cited record's opening text sit on each card.

`dossier tailor` writes CV or letter markdown under `data/drafts/` from
approved cards that already have a span. `--arrange` is letter-only.

`dossier index` embeds passages into `evidence.db` with the local Ollama
embed model. `ask` uses those vectors when full text is empty or thin.

`dossier prove` runs a disposable real-corpus pass into a throwaway data
directory. It never approves cards. See [prove](prove.md).

`dossier referees` reads a JSON people file, or Twenty when both API
variables are set. It prints a shortlist and does not write the corpus or
the CRM.

`evidence.db` is created under `~/Documents/Dossier/data` unless you set
`DOSSIER_DATA`. That file is gitignored.

Copy `dossier.example.toml` to `$DOSSIER_DATA/dossier.toml`. Environment variables win over that file. Slack ids, speaker names, and the mail-folder map go in `[identity]` there. They are not built into the package.

Records stay on this machine. Text leaves only when a remote LLM is on, which is off by default (`litellm`, or `DOSSIER_LLM_ALLOW_REMOTE`). `dossier doctor` prints `egress: no` or `egress: yes`.

| Variable | Use |
| --- | --- |
| `DOSSIER_LLM_MODEL` | Ollama tag (default `qwen3.8:latest`) |
| `DOSSIER_ASK_MODE` | `exact`, `auto` (default), or `rich` |
| `DOSSIER_ASK_FTS` | Full text on title, text, and passages (`true` by default). Whole-word overlap when this Python has no FTS5, and when full-text hits fall outside the current source or lens filter |
| `DOSSIER_ASK_CARDS_FIRST` | Prefer an approved claim that carries the question (`true` by default) |
| `DOSSIER_ASK_PASSAGES` | Search passage rows and cite the parent record (`true` by default) |
| `DOSSIER_ASK_HOPS` | After a miss, hop on Lens/Kind (default `1`) |
| `DOSSIER_ASK_DECOMPOSE` | Split compound questions: `off`, `auto` (default), or `on` |
| `DOSSIER_ASK_PLANNER` | `off` (default) or `rich` to spend one call on sub-questions |
| `DOSSIER_EMBED_MODEL` | Ollama embed tag for `dossier index` (default `nomic-embed-text`) |
| `DOSSIER_ASK_EMBED` | Use stored passage vectors when full text is empty or thin (`true` by default) |
| `DOSSIER_ASK_PUBS` | One optional pubs `/search` for that answer (`false` by default). Does not write the corpus. Ingested Zotero rows are already in the brief |
| `DOSSIER_CV_NAME` | Name printed on a tailored CV or letter. Empty omits it |
| `DOSSIER_REFEREE_PUBS` | Treat a name on an ingested pubs record as a coauthor (`true` by default) |
| `DOSSIER_EMPLOYER_PATHS` | Comma-separated employer folders. `~/Documents` itself is ignored |
| `DOSSIER_EMPLOYER_FILTER` | Skip caches, junk types, and older copies (`true` by default) |
| `DOSSIER_EMPLOYER_FILTER_LLM` | Ask the model which remaining folders to drop (`true` by default; no call when the provider is off) |
| `DOSSIER_EMPLOYER_FILTER_LLM_CALLS` | Cap for that folder pass (default `4`). Does not spend `DOSSIER_LLM_MAX_CALLS` |
| `DOSSIER_CHATGPT_EXPORT` | ChatGPT export zip or folder, used before the warehouse |
| `DOSSIER_SLACK_EXPORT` | Slack export zip or folder, used before the warehouse |
| `DOSSIER_GIT_PATHS` | Comma-separated git repos. No home-directory scan |
| `DOSSIER_GIT_USER` | Author name or email fragment. Empty keeps every author |
| `DOSSIER_MBOX_MAX_FILES` | Max mbox files opened in one exported folder (default 40) |
| `DOSSIER_LLM_MAX_CALLS` | Cap completions per process (`0` = unlimited, the default) |
| `DOSSIER_EXTRACT_LLM` | Ask the model after drafts (`true` by default) |
| `DOSSIER_RUN_PACK` | Question pack for `brief` and `run` (default `career`) |
| `DOSSIER_RUN_POSTING` | Local posting path for the posting pack |
| `DOSSIER_RUN_ADAPTERS` | Comma-separated adapter allowlist for `run` |
| `DOSSIER_LLM_BASE_URL` | Ollama root (default `http://127.0.0.1:11434`) |
| `DOSSIER_LLM_ALLOW_REMOTE` | Off by default. Set `true` to allow a non-loopback Ollama host. The prompt may then leave this machine |
| `DOSSIER_LLM_API_BASE` | Base URL when provider is `litellm`. That provider is remote LLM and prints an egress notice |
| `DATA_DUMPS_WAREHOUSE` | DuckDB file for LinkedIn and the warehouse paths of ChatGPT, Slack, and mail |
| `DOSSIER_MAIL_ROOT` | Thunderbird tree for mbox body fetch (default `~/email`) |
| `DOSSIER_MAIL_ACCOUNTS` | `email:folder` pairs, comma-separated. Overlays `[identity.mail_accounts]` |
| `DOSSIER_SLACK_USER_IDS` | Comma-separated Slack user ids or display names to treat as you |
| `DOSSIER_SEEKER_PER_STRATUM` | Max hits per lens/kind/year (default 20) |
| `DOSSIER_SEEKER_OVERALL` | Max seeker records per ingest (default 1000) |
| `DOSSIER_SEEKER_YEAR_FLOOR` | Extra document hits kept per year before score fill (default 15) |
| `DOSSIER_SEEKER_YEAR_CEILING` | Max hits from one calendar year (default 80) |
| `DOSSIER_APPLICATIONS` | Folder of prior application packs |
| `DOSSIER_CURSOR_PROJECTS` | Cursor projects root (transcripts) |
| `DOSSIER_GROK_BLOBS` | Optional extra transcript folder |
| `DOSSIER_TRANSCRIPTX` | TranscriptX library root (default `~/Documents/transcripts`, or `TRANSCRIPTX_TRANSCRIPTS_DIR`) |
| `DOSSIER_SPEAKER_NAMES` | Comma-separated display names to treat as you in meetings |
| `DOSSIER_PUBS_COLLECTION` | Zotero collection name to ingest. Overrides `[pubs] collection` |
| `ZOTERO_DB` | Path to `zotero.sqlite`. Overrides `[pubs] zotero_db` |
| `DOSSIER_PUBS_URL` | Optional `/search` base URL when no collection is set (default `http://127.0.0.1:8012`) |
| `DOSSIER_PUBS_SEED` | Query for that `/search` (default `publications`) |
| `DOSSIER_PUBS_TOP_K` | Max hits from that `/search` (default `50`) |
| `DOSSIER_TWENTY_API_URL` | Twenty API origin for `referees` (read-only GraphQL) |
| `DOSSIER_TWENTY_API_KEY` | Bearer token for that read. Never commit it |
