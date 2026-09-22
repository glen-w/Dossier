# Privacy

Type: GUIDE
Authority: What stays on this machine, and the one way text can leave.

Your records stay on this machine. Ingest, `evidence.db` (including passage vectors), briefs, drafts, packets, mail, exports, and the gitignored `dossier.toml` are local files. Dossier does not upload them.

The only way text leaves the machine is a remote LLM, and it is off by default.

| How it turns on | What is sent |
| --- | --- |
| `DOSSIER_LLM_PROVIDER=litellm` (needs `dossier[llm]`) | The prompt for that call, to the LiteLLM provider |
| `DOSSIER_LLM_ALLOW_REMOTE=true` or `[llm] allow_remote = true` | The same prompt, or passage text for `index`, to an Ollama host that is not loopback |

Default is provider `ollama` at `http://127.0.0.1:11434` with `allow_remote = false`. A non-loopback Ollama URL without that flag is refused and does not print the remote notice. Before the first allowed remote call the CLI prints: `Remote LLM is on — the prompt for that call may leave this machine.` The corpus file is not attached. `dossier doctor` prints `egress: no` or `egress: yes` so you can see the current choice (blocked remote URLs stay `egress: no`).

Loopback calls that are not that exception:

- Pubs search defaults to `http://127.0.0.1:8012` and `ask.pubs` is off. A non-loopback pubs URL is not contacted.
- `dossier referees` reads Twenty only when both `DOSSIER_TWENTY_API_URL` and `DOSSIER_TWENTY_API_KEY` are set. The request is a fixed people query, not your corpus. It does not write Twenty.

Before every push, run `python3 scripts/release/check_gitignore.py`. It fails if `.gitignore` drops a personal-data pattern or if a corpus, export, or secret is already tracked. Do not push when it fails.

Also off git: dumps, DuckDB, LanceDB, `.env`, mbox, PDFs, office exports, and local `assessments/`. Slack ids, speaker names, the mail-folder map, and include/exclude phrase edits live only in gitignored `$DOSSIER_DATA/dossier.toml`. Invalid TOML fails load instead of silently using empty config.

- No Twenty writes (Tasks, Opportunities, Notes, last-contacted).
- No auto-attach of a referee name to an application.
- No 26G IDDRI mbox stream; no Sent Mail as a folder walker; no re-embed of hoops or ocean Zotero libraries.
- No plugin directory or entry-point scan.
- No Docker image for the locker. It installs on the host with `uv`.
- Meeting transcripts stay in the TranscriptX library. Ingest copies your turns into `evidence.db` only.

See [roadmap](roadmap.md) for the full refuse list.
