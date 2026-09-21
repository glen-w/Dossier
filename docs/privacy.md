# Privacy

Type: GUIDE
Authority: What stays off git and off the network. The refuse list is defined in [roadmap](roadmap.md).

- Do not commit dumps, DuckDB files, LanceDB, `evidence.db` (including passage vectors), `.env`, mbox, exports, or PDFs.
- Work stays on loopback unless you opt into a remote model. The egress notice
  is the warning, not a block.
- No Twenty writes (Tasks, Opportunities, Notes, last-contacted).
- No auto-attach of a referee name to an application.
- No cloud LLM default.
- No 26G IDDRI mbox stream; no Sent Mail as a folder walker; no re-embed of
  hoops or ocean Zotero libraries.
- No plugin directory or entry-point scan.
- Meeting transcripts stay in the TranscriptX library. Ingest copies your
  turns into `evidence.db` only. Do not commit that library.

See [roadmap](roadmap.md) for the full refuse list.
