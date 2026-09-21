# Seekers (mail and Slack)

Seek, then fetch a diverse snippet buffet, then let Ollama word claims. Do not scan or embed a full history.

```text
warehouse metadata (Slack text, Thunderbird Gloda)
    → hunts (files, threads, activity folders, sent documents)
        → diversity quotas (lens × kind × year × source)
            → targeted fetch (Slack rows + thread; one small mbox message)
                → corpus records
                    → extract (drafts, then Ollama on snippets only) → human gate
                    → ask / brief (quote, hop, optional completion)
```

## Lenses

Closed set. Folder and channel names feed the seeker; cards are filed under lenses.

- **delivered** — artifacts and events (brief, paper, chapter, book, report, tables, slides, workshop, webinar, teaching, side-event)
- **skills** — evidenced in context (not a LinkedIn dump). Kept only if the hit shows the skill in use
- **contributions** — role (drafted, edited, coordinated, reviewed, taught, convened, data/tables, outreach)

IDDRI mail is research/teaching. REN21 Slack is GSR/GFR production. Quotas exist so the buffet is not only one of those.

## Slack

Read `slack.*` in the data_dumps warehouse. Do not unzip the export.

Identity: `U05E73N5733` and `UUDS0NJ9W`, or `DOSSIER_SLACK_USER_IDS`. Hunts stay on Glen-touched rows: file posts, long messages, hot threads, file-conversations, files that mention him or sit in a thread he replied to, samples from GSR/research/events channels.

## Mail

Seek `thunderbird.messages` (Gloda: subject, folder, attachments, direction). Bodies are not in the warehouse.

- Exclude newsletters, receipts, `la vie de l'iddri`, bounced, out of office, and Gloda `signals` of those kinds
- Prefer activity folders (Teaching, webinars, workshops, BBNJ, IKI, PROG, Review, …)
- Rank sent+document in those folders; delivery-ish subjects; starred/replied
- Sent+document outside activity folders is metadata only
- **Never** stream `~/email/iddri` or `Sent Mail`. Wrap rollup `parse_message` for **one** allowlisted mbox under `DOSSIER_MBOX_MAX_BYTES` (default 200MB). If the only copy is Sent Mail, keep subject + attachment names

Glen: `uv run dossier ingest --adapter mbox` reads the warehouse and fetches from `DOSSIER_MAIL_ROOT` (default `~/email`). Thin user: one exported folder, same heuristics, no Gloda.

## Quotas

Default 20 hits per (source, lens, kind, year), 400 overall. Override `DOSSIER_SEEKER_PER_STRATUM` / `DOSSIER_SEEKER_OVERALL`. At least one hit per populated stratum when possible.

## Extract

`dossier extract --source slack` (or `mbox`) sends only those snippets to Ollama. Cloud still prints an egress notice. Work mail and Slack do not leave the machine by default.
