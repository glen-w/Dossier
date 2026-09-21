"""Mail seeker. Gloda metadata in the warehouse; bodies from small allowlisted mboxes."""

from __future__ import annotations

from pathlib import Path

from dossier.fetch.mbox import build_mbox_index, fetch_mbox_body, is_mbox_file, mbox_max_bytes
from dossier.fetch.snippet import record_from_hit
from dossier.identity import is_blocked_mail_root
from dossier.paths import mail_root, warehouse_db
from dossier.seekers.hits import merge_hits
from dossier.seekers.mail import hunt_mail, hunt_mbox_folder
from dossier.seekers.quota import apply_quotas
from dossier.sources.warehouse import connect_readonly, has_table, resolve_warehouse
from dossier.store import Corpus


class MboxSource:
    name = "mbox"

    def detect(self, path: Path) -> bool:
        db = resolve_warehouse(path)
        if db.is_file():
            try:
                conn = connect_readonly(path)
            except Exception:
                return False
            try:
                return has_table(conn, "thunderbird.messages")
            finally:
                conn.close()
        if path.is_dir():
            if is_blocked_mail_root(path):
                return True
            return _dir_has_mbox(path)
        return is_mbox_file(path)

    def load(self, path: Path, corpus: Corpus) -> None:
        db = resolve_warehouse(path)
        if db.is_file() and _warehouse_has_mail(path):
            self._load_warehouse(path, mail_root(), corpus)
            return
        if is_blocked_mail_root(path):
            wh = warehouse_db()
            if wh.is_file() and _warehouse_has_mail(wh):
                self._load_warehouse(wh, path.parent if path.name.lower() == "iddri" else path, corpus)
            return
        hits = apply_quotas(merge_hits(hunt_mbox_folder(path, max_bytes=mbox_max_bytes())))
        root = path if path.is_dir() else path.parent
        self._put_hits(hits, root, corpus)

    def tables(self) -> list[str]:
        return ["thunderbird.messages", "mbox.hits"]

    def _load_warehouse(self, warehouse: Path, root: Path, corpus: Corpus) -> None:
        conn = connect_readonly(warehouse)
        try:
            hits = apply_quotas(merge_hits(hunt_mail(conn)))
        finally:
            conn.close()
        self._put_hits(hits, root, corpus)

    def _put_hits(self, hits, root: Path, corpus: Corpus) -> None:
        catalog = build_mbox_index(root)
        for hit in hits:
            body = ""
            if hit.fetch_body:
                body = fetch_mbox_body(
                    root,
                    account_key=hit.account_key,
                    folder_name=hit.folder_name,
                    header_message_id=hit.header_message_id,
                    index=catalog,
                )
            corpus.upsert_record(record_from_hit(hit, body))


def _warehouse_has_mail(path: Path) -> bool:
    try:
        conn = connect_readonly(path)
    except Exception:
        return False
    try:
        return has_table(conn, "thunderbird.messages")
    finally:
        conn.close()


def _dir_has_mbox(path: Path) -> bool:
    from dossier.fetch.mbox import iter_mbox_files

    for _ in iter_mbox_files(path):
        return True
    return False
