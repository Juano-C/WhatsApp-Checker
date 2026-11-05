import csv
import sqlite3
from datetime import date
from pathlib import Path
from typing import Iterable

from .parser import Message


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        # La importación corre en un QThread distinto al de la interfaz.
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                source TEXT,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL REFERENCES chats(id),
                message_date TEXT NOT NULL,
                message_time TEXT NOT NULL,
                contact TEXT NOT NULL,
                text TEXT NOT NULL,
                UNIQUE(chat_id, message_date, message_time, contact, text)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_chat_date
                ON messages(chat_id, message_date);
            CREATE INDEX IF NOT EXISTS idx_messages_contact
                ON messages(chat_id, contact);
            CREATE INDEX IF NOT EXISTS idx_messages_time
                ON messages(chat_id, message_time);
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                chat TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                text_filter TEXT NOT NULL DEFAULT '',
                contact_filter TEXT NOT NULL DEFAULT '',
                include_system INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS snapshot_stats (
                snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
                contact TEXT NOT NULL,
                total INTEGER NOT NULL,
                PRIMARY KEY(snapshot_id, contact)
            );
            """
        )
        # Migración sencilla para bases creadas por versiones anteriores.
        snapshot_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(snapshots)")}
        if "include_system" not in snapshot_columns:
            self.connection.execute("ALTER TABLE snapshots ADD COLUMN include_system INTEGER NOT NULL DEFAULT 0")
        self.connection.commit()

    def chat_names(self) -> list[str]:
        return [row[0] for row in self.connection.execute("SELECT name FROM chats ORDER BY name")]

    def contacts(self, chat: str, include_system: bool = False) -> list[str]:
        condition = "c.name=?" if include_system else "c.name=? AND m.contact != 'Sistema'"
        return [row[0] for row in self.connection.execute(
            f"""SELECT DISTINCT m.contact FROM messages m
                JOIN chats c ON c.id=m.chat_id WHERE {condition} ORDER BY m.contact""",
            (chat,),
        )]

    def import_messages(self, name: str, source: str, messages: Iterable[Message], batch_size=1000) -> tuple[int, int]:
        cursor = self.connection.execute(
            "INSERT INTO chats(name, source) VALUES(?, ?) "
            "ON CONFLICT(name) DO UPDATE SET source=excluded.source RETURNING id",
            (name, source),
        )
        chat_id = cursor.fetchone()[0]
        inserted = 0
        total = 0
        batch = []
        for message in messages:
            total += 1
            batch.append((chat_id, message.date, message.time, message.contact, message.text))
            if len(batch) >= batch_size:
                inserted += self._insert_batch(batch)
                batch.clear()
        if batch:
            inserted += self._insert_batch(batch)
        return total, inserted

    def _insert_batch(self, batch) -> int:
        before = self.connection.total_changes
        self.connection.executemany(
            "INSERT OR IGNORE INTO messages(chat_id, message_date, message_time, contact, text) VALUES(?, ?, ?, ?, ?)",
            batch,
        )
        self.connection.commit()
        return self.connection.total_changes - before

    def search(self, chat: str, text: str = "", contact: str = "", start: str = "", end: str = "", include_system: bool = False):
        params = [chat]
        conditions = ["c.name = ?"]
        if not include_system:
            conditions.append("m.contact != 'Sistema'")
        if text:
            conditions.append("m.text LIKE ?")
            params.append(f"%{text}%")
        if contact:
            conditions.append("m.contact LIKE ?")
            params.append(f"%{contact}%")
        if start:
            conditions.append("m.message_date >= ?")
            params.append(start)
        if end:
            conditions.append("m.message_date <= ?")
            params.append(end)
        query = """SELECT m.message_date, m.message_time, m.contact, m.text
                   FROM messages m JOIN chats c ON c.id = m.chat_id
                   WHERE """ + " AND ".join(conditions) + " ORDER BY m.message_date, m.message_time"
        return self.connection.execute(query, params).fetchall()

    def stats(self, chat: str, text: str = "", contact: str = "", start: str = "", end: str = "", include_system: bool = False):
        params = [chat]
        conditions = ["c.name = ?"]
        if not include_system:
            conditions.append("m.contact != 'Sistema'")
        if text:
            conditions.append("m.text LIKE ?"); params.append(f"%{text}%")
        if contact:
            conditions.append("m.contact LIKE ?"); params.append(f"%{contact}%")
        if start:
            conditions.append("m.message_date >= ?"); params.append(start)
        if end:
            conditions.append("m.message_date <= ?"); params.append(end)
        query = """SELECT m.contact, COUNT(*) AS total
                   FROM messages m JOIN chats c ON c.id=m.chat_id
                   WHERE """ + " AND ".join(conditions) + " GROUP BY m.contact " \
                "ORDER BY CASE WHEN m.contact='Sistema' THEN 0 ELSE 1 END, total DESC"
        return [(row[0], row[1]) for row in self.connection.execute(query, params)]

    def save_snapshot(self, name: str, chat: str, text: str, contact: str, start: str, end: str, include_system: bool) -> int:
        stats = self.stats(chat, text, contact, start, end, include_system)
        cursor = self.connection.execute(
            """INSERT INTO snapshots(name, chat, start_date, end_date, text_filter, contact_filter, include_system)
               VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (name, chat, start, end, text, contact, int(include_system)),
        )
        snapshot_id = cursor.lastrowid
        self.connection.executemany(
            "INSERT INTO snapshot_stats(snapshot_id, contact, total) VALUES(?, ?, ?)",
            [(snapshot_id, item[0], item[1]) for item in stats],
        )
        self.connection.commit()
        return snapshot_id

    def snapshots(self):
        return self.connection.execute(
            """SELECT id, name, chat, start_date, end_date, text_filter, contact_filter, include_system, created_at
               FROM snapshots ORDER BY id DESC"""
        ).fetchall()

    def compare_snapshots(self, first_id: int, second_id: int):
        return self.connection.execute(
            """SELECT COALESCE(a.contact, b.contact) AS contact,
                      COALESCE(a.total, 0) AS first_total,
                      COALESCE(b.total, 0) AS second_total
               FROM snapshot_stats a
               FULL OUTER JOIN snapshot_stats b ON a.contact=b.contact
                   AND a.snapshot_id=? AND b.snapshot_id=?
               WHERE a.snapshot_id=? OR b.snapshot_id=?
               ORDER BY CASE WHEN COALESCE(a.contact, b.contact)='Sistema' THEN 0 ELSE 1 END,
                        second_total DESC""", (first_id, second_id, first_id, second_id)
        ).fetchall()

    def export_csv(self, rows, path: str):
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["fecha", "hora", "contacto", "mensaje"])
            writer.writerows((row[0], row[1], row[2], row[3]) for row in rows)
