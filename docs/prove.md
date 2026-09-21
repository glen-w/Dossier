# Prove (0.6)

`dossier prove` fills a disposable locker from adapters already on disk,
drafts cards, writes an exact-mode brief, runs defend / gaps / packet, and
smokes a few `ask --mode exact` questions. It writes `ledger.json` and
`ledger.md` under the data directory. **It never approves a card.**

## Default behaviour

- Temporary `DOSSIER_DATA` (or `--data`)
- Adapters: `linkedin,chatgpt,applications` (no `mbox` by default — IDDRI risk)
- Seeker caps lowered (`DOSSIER_SEEKER_OVERALL=80`)
- Model off (`DOSSIER_LLM_PROVIDER=off`) unless `--with-llm`
- Refuses when FTS5 is missing unless `--allow-overlap`
- `--pubs` includes the pubs adapter (empty until `/search` returns rows)

```text
uv run dossier prove
uv run dossier prove --data /tmp/dossier-prove --adapters applications
bash scripts/prove_0_6.sh
bash scripts/prove_0_6.sh --pubs
```

## After prove

```text
DOSSIER_DATA=<path from ledger> uv run dossier buffet --status pending
DOSSIER_DATA=<path> uv run dossier approve <card-id>
DOSSIER_DATA=<path> uv run dossier ask "…"
```

Spot-check refusals and spanned packets. Own-pubs live rows require the
collection confirm gate — see [publications index](zotero-rag-pubs.md).

## Collection listing (read-only)

```text
uv run python scripts/list_zotero_collections.py
```

Prints Zotero collection names and item counts. Does not ingest or embed.
