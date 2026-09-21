# CLI

```text
uv run dossier ingest --adapter applications ./path/to/applications
uv run dossier ingest --adapter slack
uv run dossier ingest --adapter mbox
uv run dossier ingest --adapter meetings
uv run dossier extract --source slack
uv run dossier extract
uv run dossier buffet --status pending
uv run dossier approve <card-id>
uv run dossier span "synthetic paper on coastal governance"
uv run dossier defend
uv run dossier gaps
uv run dossier packet
uv run dossier ask "what did I write about coastal governance?"
uv run dossier ask --mode exact --source pubs "coastal governance"
uv run dossier brief
uv run dossier brief --posting ./posting.txt
uv run dossier run
uv run dossier prove
uv run dossier doctor
uv run dossier referees --posting ./posting.txt --employer "Hiring Org"
```

`dossier prove` runs a disposable real-corpus pass into a throwaway data
directory. It never approves cards. See [prove](prove.md).

`dossier referees` reads a JSON people file, or Twenty when both API
variables are set. It prints a shortlist and does not write the corpus or
the CRM.

`evidence.db` is created under `~/Documents/Dossier/data` unless you set
`DOSSIER_DATA`. That file is gitignored.

Environment knobs are listed in the repository README and
`dossier.example.toml`.
