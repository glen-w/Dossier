# zotero-rag pubs (proposal)

Read-only look at `~/Documents/papers/zotero.sqlite` on 21 Sep 2026 (immutable open; Zotero had the file locked).

A collection is named **`my pubs`** (353 items). That matches the name already used for Glen’s own publications. This note proposes a third zotero-rag instance. It does not start one.

- Clone pattern: laptop compose beside hoops `:8009` and ocean `:8010`
- Suggested port: `:8012`
- `ZOTERO_COLLECTION=my pubs`
- Own LanceDB directory
- Ingest **off** until Glen confirms the collection and that 353 items is the right scope

Dossier’s `pubs` adapter retrieves from that index later (HTTP ping on `:8012`). Today it loads a JSON fixture or a stub retriever. Live `records()` is empty on purpose.

Do not re-embed hoops or ocean into Dossier. Do not wire Homer/Kuma/Syncthing in this sitting.
