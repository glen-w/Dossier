# Prior art

Take the rule that fits. Leave the product that does not.

**CareerForge** ([MasRama/careerforge](https://github.com/MasRama/careerforge)). Evidence in, claims out, refuse a claim the records will not carry. Local, no account. Its collectors are git history and coding sessions. Dossier keeps the refuse rule and uses other sources.

**vibe-resume** ([easyvibecoding/vibe-resume](https://github.com/easyvibecoding/vibe-resume)). Extractors for Cursor transcripts and ChatGPT exports, then a résumé. Useful shapes for those two sources. The résumé step is not this repo.

**Recallr** ([Flowdesktech/recallr](https://github.com/flowdesktech/recallr), MIT). mbox and Slack exports into SQLite hybrid search, plus MCP. A candidate search backend for ask-the-corpus. Not claim cards.

**LEANN** ([yichuan-w/LEANN](https://github.com/yichuan-w/LEANN)). Laptop RAG over files, mail, and ChatGPT exports. Retrieval, not a buffet of approved claims.

**RenderCV / JSON Resume.** A way to render a CV later, from cards you have already approved. No renderer in this repo.

**data_dumps** ([glen-w/data_dumps](https://github.com/glen-w/data_dumps)). ZIP exports to DuckDB. LinkedIn, ChatGPT, and Slack message text can already live there. Thunderbird tables are metadata only. Dossier reads that warehouse. It does not ship those loaders.

**rollup** (house). `parse.py` walks a whole mbox for newsletter digests. Dossier wraps `parse_message` for **one** allowlisted message after a Gloda seek. It does not call `parse_mbox_folder` on Sent Mail or IDDRI.

**zotero-rag** ([anapaulagomes/zotero-rag](https://github.com/anapaulagomes/zotero-rag)). RAG over one Zotero collection. Own publications should be a separate instance of that project, not a new embedder inside Dossier. See [publications index](zotero-rag-pubs.md).

The LLM client in this repo defaults to Ollama on loopback. A remote completion prints an egress notice first.
