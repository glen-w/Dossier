"""ChatGPT messages from an export or the data_dumps warehouse. Read-only."""

from __future__ import annotations

from pathlib import Path

from dossier.sources.chatgpt_export import is_chatgpt_export, load_chatgpt_export
from dossier.sources.warehouse import connect_readonly, has_table, resolve_warehouse
from dossier.store import Corpus, Record
from dossier.util import record_id

CHATGPT_LIMIT = 2000
TEXT_CAP = 8000


class ChatGPTSource:
    name = "chatgpt"

    def detect(self, path: Path) -> bool:
        if is_chatgpt_export(path):
            return True
        db = resolve_warehouse(path)
        if not db.is_file():
            return False
        try:
            conn = connect_readonly(path)
        except Exception:
            return False
        try:
            return has_table(conn, "chatgpt.messages")
        finally:
            conn.close()

    def load(self, path: Path, corpus: Corpus) -> None:
        if is_chatgpt_export(path):
            load_chatgpt_export(path, corpus)
            return
        conn = connect_readonly(path)
        try:
            join_title = has_table(conn, "chatgpt.conversations")
            if join_title:
                sql = """
                SELECT m.message_id, m.conversation_id, m.role, m.text, c.title
                FROM chatgpt.messages AS m
                LEFT JOIN chatgpt.conversations AS c
                  ON m.conversation_id = c.conversation_id
                WHERE m.text IS NOT NULL AND length(m.text) > 40
                ORDER BY m.ts_utc DESC NULLS LAST
                LIMIT ?
                """
            else:
                sql = """
                SELECT m.message_id, m.conversation_id, m.role, m.text,
                       CAST(NULL AS VARCHAR) AS title
                FROM chatgpt.messages AS m
                WHERE m.text IS NOT NULL AND length(m.text) > 40
                ORDER BY m.ts_utc DESC NULLS LAST
                LIMIT ?
                """
            rows = conn.execute(sql, [CHATGPT_LIMIT]).fetchall()
        finally:
            conn.close()
        for message_id, conversation_id, role, text, title in rows:
            body = str(text or "").strip()
            if not body:
                continue
            cid = str(conversation_id or "unknown")
            mid = str(message_id or record_id(body))
            uri = f"chatgpt://{cid}/{mid}"
            heading = str(title or "").strip() or f"ChatGPT {role or 'message'}"
            corpus.upsert_record(
                Record(
                    id=record_id(uri),
                    source="chatgpt",
                    uri=uri,
                    title=heading,
                    text=body[:TEXT_CAP],
                    table="chatgpt.messages",
                )
            )

    def tables(self) -> list[str]:
        return ["chatgpt.messages"]
