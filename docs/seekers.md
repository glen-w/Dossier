# Seekers (mail, Slack, and meetings)

Type: GUIDE
Authority: How mail, Slack, and meetings are sought. Caps and refuse lines live in [status](status.md) and [roadmap](roadmap.md).

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

A thin user skips the warehouse. Slack can start from an export zip, and mail from one exported folder. Quotas still apply.

## Lenses

Closed set. Folder and channel names feed the seeker; cards are filed under lenses.

- **delivered** — artifacts and events (brief, paper, chapter, book, report, tables, slides, workshop, webinar, teaching, side-event)
- **skills** — evidenced in context (not a LinkedIn dump). Kept only if the hit shows the skill in use
- **contributions** — role (drafted, edited, coordinated, reviewed, taught, convened, data/tables, outreach)

IDDRI mail is research/teaching. REN21 Slack is GSR/GFR production. Quotas exist so the buffet is not only one of those.

## Slack

Glen: read `slack.*` in the data_dumps warehouse. Thin user: a Slack export zip or folder (`users.json` plus channel JSON), via `DOSSIER_SLACK_EXPORT` or the path you pass. Quotas apply to both. The export is not copied into git.

Identity: `DOSSIER_SLACK_USER_IDS` (ids or a display name), or `[identity] slack_user_ids` in gitignored `$DOSSIER_DATA/dossier.toml`. Nothing is built in. Warehouse hunts stay on those rows: file posts, long messages, hot threads, file-conversations, files that mention you or sit in a thread you replied to, samples from GSR/research/events channels. The export path keeps messages from those ids. When ids are unset, speaker names from that same file can match a Slack display name.

## Mail

Seek `thunderbird.messages` (Gloda: subject, folder, attachments, direction). Bodies are not in the warehouse.

- Exclude newsletters, receipts, google alerts, affiliate mail, bounce folders, `la vie de l'iddri`, and out of office, plus Gloda `signals` of newsletter, receipt, subscription, and signup
- Keep admin, budget, and finance folders. A reimbursement or a budget note there is evidence. One message tagged as a receipt still drops
- Those lists are on without a config file. Each source has a section in gitignored `dossier.toml`: `[mail]`, `[names]`, `[slack]`, `[meetings]`, `[employer]`, and `exclude` on `[git]`, `[chatgpt]`, `[linkedin]`, `[transcripts]`, `[pubs]`, and `[applications]`. A list adds phrases. The matching `_off` key turns a built-in phrase off. Environment variables `DOSSIER_<SECTION>_<KEY>` override the file. Sent, Inbox, and All Mail stay closed. `.git` stays skipped
- Prefer activity folders (Teaching, webinars, workshops, BBNJ, IKI, PROG, Review, …)
- Rank sent+document in those folders; delivery-ish subjects; starred/replied
- Sent+document outside activity folders is metadata only
- **Never** stream `~/email/iddri` or `Sent Mail`. Wrap rollup `parse_message` for **one** allowlisted mbox under `DOSSIER_MBOX_MAX_BYTES` (default 200MB). If the only copy is Sent Mail, keep subject + attachment names

Glen: `uv run dossier ingest --adapter mbox` reads the warehouse and fetches from `DOSSIER_MAIL_ROOT` (default `~/email`). Thin user: one exported folder, same heuristics, no Gloda.

## Meetings

Read a TranscriptX library (`DOSSIER_TRANSCRIPTX`, else `TRANSCRIPTX_TRANSCRIPTS_DIR`, else `~/Documents/transcripts`). Speaker names live in `metadata/speaker_maps/*.speaker_map.json`. A folder of JSON files with colocated `.speaker_map.json` sidecars works the same way. Dossier does not import the TranscriptX package.

Identity: `DOSSIER_SPEAKER_NAMES` (comma-separated display names), or `[identity] speaker_names` in the gitignored toml. When both are empty, no speaker is you. A `SPEAKER_00` → `SPEAKER_00` self-map is not a name. Ignored speakers are skipped. A segment may name the diarized id (`SPEAKER_00`, `0`) or the display name.

A meeting is kept when you are a named speaker and someone else spoke, or you are the only speaker and the filename is an event (workshop, webinar, teaching, slides). Solo notes are skipped. Conflicted copies and `__inbox` duplicates of a file already in the library are skipped. The stored text is your turns, capped, plus the other named people. Their speech stays in the library.

## Quotas

Default 20 hits per (source, lens, kind, year), 1000 overall. After one hit per stratum, a year floor keeps up to 15 further document hits per calendar year (round-robin across years, skipping logistics noise) before score fill. A year ceiling (default 80) stops a busy recent year from eating the budget. Override `DOSSIER_SEEKER_PER_STRATUM`, `DOSSIER_SEEKER_OVERALL`, `DOSSIER_SEEKER_YEAR_FLOOR`, and `DOSSIER_SEEKER_YEAR_CEILING`. At least one hit per populated stratum when possible.

## Extract

`dossier extract --source slack` (or `mbox`, or `meetings`) sends only those snippets to the model. By default that model is Ollama on loopback, so the snippets stay on this machine. A remote LLM is off unless you set provider `litellm` or `DOSSIER_LLM_ALLOW_REMOTE`; the CLI then prints an egress notice before the prompt is sent.
