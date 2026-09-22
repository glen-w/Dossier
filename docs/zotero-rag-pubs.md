# Publications index

Type: GUIDE
Authority: How own publications enter the corpus. Ask behavior lives in [status](status.md).

`dossier ingest` and `dossier run` read one Zotero collection into `pubs` records. The career brief lists those records under “What did I publish?”. No separate server, and no PDF parsing.

Set the collection in gitignored `data/dossier.toml` (environment variables win):

```toml
[pubs]
collection = "my pubs"
zotero_db = "/absolute/path/to/zotero.sqlite"
```

`collection` is the collection name or key, including child collections. Unset means this path does not run. A different collection, including a whole library, is not read. `zotero_db` defaults to `~/Zotero/zotero.sqlite`. `DOSSIER_PUBS_COLLECTION` and `ZOTERO_DB` override the file.

Each item becomes one record: title, authors, year, journal, DOI, and abstract when Zotero has one. The URI is `zotero://` plus the item key. Attachments, notes, and deleted items are skipped.

List collection names without ingesting:

```text
uv run python scripts/list_zotero_collections.py
```

`doctor` prints the collection and, when the file has items, `adapter pubs: detected rows=N`. When a collection is set but `rows=0`, it prints a warn (wrong name or missing `zotero.sqlite`). A configured collection blocks the optional HTTP `/search` fallback.

## Optional loopback search

When `collection` is unset, the adapter can still `POST {DOSSIER_PUBS_URL}/search` with `{"query", "top_k"}` and map `{"hits": [{"uri","title","text"}]}`. The default URL is `http://127.0.0.1:8012`. A non-loopback host is not contacted. `DOSSIER_PUBS_SEED` and `DOSSIER_PUBS_TOP_K` apply only to that search. `ask.pubs` can call it for one answer and does not write the corpus.

[zotero-rag](https://github.com/anapaulagomes/zotero-rag) remains a separate project for embedded PDF chat. Dossier does not start it and does not reuse its index.
