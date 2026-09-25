# AGENTS.md

Instructions for agents in this repo. Life facts stay out of this tree.

- No secrets, dumps, mail, or PDFs in git.
- Warehouse seek of Thunderbird/Slack metadata is allowed. Do not parse a blocked mail tree or Sent Mail as a stream. Body fetch is one allowlisted mbox message under the size cap.
- Do not re-embed a Zotero library you did not name.
- Ollama is the default LLM. Text leaves the machine only for a remote LLM, which is off unless the user sets `litellm` or `DOSSIER_LLM_ALLOW_REMOTE`. Print the egress notice when that is on.
- Before every push, run `python3 scripts/release/check_gitignore.py`. Do not push if it fails. Personal corpus, exports, and `dossier.toml` stay gitignored.
- No Twenty writes. Referee shortlist is read-only; do not attach a name to an application.
- Tests use synthetic fixtures only.
- Pubs ingest reads only the Zotero collection named in `data/dossier.toml`. Do not re-read a library you did not name, and do not `docker compose up` zotero-rag.
- Product now/next/later: [docs/roadmap.md](docs/roadmap.md).
