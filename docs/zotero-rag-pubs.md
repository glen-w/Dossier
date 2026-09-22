# Publications index

Type: GUIDE
Authority: How the sibling pubs server is wired. Ingest stays off until the collection is confirmed. Ask behavior lives in [status](status.md).

Own publications are retrieved from a separate [zotero-rag](https://github.com/anapaulagomes/zotero-rag) instance. Dossier does not embed a Zotero library, and it does not reuse an index built for some other collection.

Suggested layout, when you choose to run one:

- Its own compose project and its own LanceDB directory
- `ZOTERO_COLLECTION` set to the collection that is actually your publications
- Loopback port `8012` (the `pubs` adapter’s default `DOSSIER_PUBS_URL`)
- A thin `POST /search` endpoint that wraps LanceDB retrieval (upstream zotero-rag is Chainlit + CLI today)

That compose project is the pubs server only. The locker stays a host CLI. See [install](install.md).

Confirm the collection name in Zotero before any ingest. A large library and a publications folder are different scopes.

```text
uv run python scripts/list_zotero_collections.py
```

## HTTP contract

`POST {DOSSIER_PUBS_URL}/search` with JSON `{"query": str, "top_k": int}` returns
`{"hits": [{"uri", "title", "text", ...}]}`.

Optional env, or the same keys under `[pubs]` in gitignored `data/dossier.toml`
(environment variables win):

- `DOSSIER_PUBS_SEED` / `seed` — query used when ingesting (default `publications`)
- `DOSSIER_PUBS_TOP_K` / `top_k` — hit cap (default `50`)
- `collection` — Zotero collection name. `doctor` prints it when set. Dossier does not embed that library and does not start ingest
- `zotero_db` — path to `zotero.sqlite` for `scripts/list_zotero_collections.py`

Ping tries `GET /health` then `GET /`.

## What the adapter does now

`PubsSource` can load a JSON fixture (`{"records": [{"uri", "title", "text"}]}`) for tests. `HttpPubsRetriever` pings the URL and maps `/search` hits into corpus records. Until the sibling pubs server implements `/search` and ingest is confirmed, live `records()` stays empty. This repo does not start the other service. `ask.pubs` can call `/search` for one answer and does not write those hits into the corpus. See [roadmap](roadmap.md).
