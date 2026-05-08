"""Tiny SQLite-backed store for staged orders. Pragmatic, not a full ORM."""
import json
import logging
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

log = logging.getLogger("db")


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def init(self) -> None:
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    ocr_text TEXT NOT NULL,
                    ocr_confidence REAL NOT NULL,
                    draft_json TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    external_id TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
                """
            )
            log.info("DB ready at %s", self.path)

    def save_raw(self, order_id: str, filename: str,
                 ocr_text: str, ocr_confidence: float) -> None:
        now = datetime.utcnow().isoformat()
        with self._conn() as c:
            c.execute(
                """INSERT INTO orders
                   (id, filename, ocr_text, ocr_confidence, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
                (order_id, filename, ocr_text, ocr_confidence, now, now),
            )

    def save_draft(self, order_id: str, draft: Dict) -> None:
        now = datetime.utcnow().isoformat()
        with self._conn() as c:
            c.execute(
                "UPDATE orders SET draft_json=?, updated_at=? WHERE id=?",
                (json.dumps(draft, default=str), now, order_id),
            )

    def get_raw(self, order_id: str) -> Optional[Dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        return dict(row) if row else None

    def get_full(self, order_id: str) -> Optional[Dict]:
        rec = self.get_raw(order_id)
        if not rec:
            return None
        if rec.get("draft_json"):
            try:
                rec["draft"] = json.loads(rec["draft_json"])
            except json.JSONDecodeError:
                rec["draft"] = None
        return rec

    def list_orders(self, status_filter: Optional[str] = None) -> List[Dict]:
        with self._conn() as c:
            if status_filter:
                rows = c.execute(
                    "SELECT id, filename, status, ocr_confidence, external_id, "
                    "created_at, updated_at FROM orders WHERE status=? ORDER BY created_at DESC",
                    (status_filter,),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT id, filename, status, ocr_confidence, external_id, "
                    "created_at, updated_at FROM orders ORDER BY created_at DESC LIMIT 200"
                ).fetchall()
        return [dict(r) for r in rows]

    def set_status(self, order_id: str, status: str,
                   external_id: Optional[str] = None, error: Optional[str] = None) -> None:
        now = datetime.utcnow().isoformat()
        with self._conn() as c:
            c.execute(
                """UPDATE orders SET status=?, external_id=COALESCE(?, external_id),
                                     error=?, updated_at=? WHERE id=?""",
                (status, external_id, error, now, order_id),
            )
