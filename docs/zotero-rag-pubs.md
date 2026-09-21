# Publications index

Own publications are retrieved from a separate [zotero-rag](https://github.com/anapaulagomes/zotero-rag) instance. Dossier does not embed a Zotero library, and it does not reuse an index built for some other collection.

Suggested layout, when you choose to run one:

- Its own compose project and its own LanceDB directory
- `ZOTERO_COLLECTION` set to the collection that is actually your publications
- Loopback port `8012` (the `pubs` adapter’s default `DOSSIER_PUBS_URL`)

Confirm the collection name in Zotero before any ingest. A large library and a publications folder are different scopes.

## What the adapter does now

`PubsSource` can load a JSON fixture (`{"records": [{"uri", "title", "text"}]}`) for tests. `HttpPubsRetriever` may ping `DOSSIER_PUBS_URL`. Its `records()` method returns an empty list. Wiring real hits from that index is still to do, and this repo does not start the other service.
