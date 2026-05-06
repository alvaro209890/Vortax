import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from config import settings


def _database_directory() -> Path:
    base = settings.DATABASE_BASE_PATH
    return base if base.name.lower() == "vortax" else base / "Vortax"


def _database_file() -> Path:
    return _database_directory() / f"vortax{settings.DATABASE_EXTENSION}"


class Database:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._db_dir = _database_directory()
        self._db_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = _database_file()
        self._connection = sqlite3.connect(self._db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._connection:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _init_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_events_task_id_id ON events(task_id, id);

                CREATE TABLE IF NOT EXISTS screenshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_id INTEGER,
                    created_at TEXT NOT NULL,
                    caption TEXT,
                    title TEXT,
                    url TEXT,
                    image_base64 TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_screenshots_task_id_id ON screenshots(task_id, id);

                CREATE TABLE IF NOT EXISTS chat_images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_id INTEGER,
                    created_at TEXT NOT NULL,
                    filename TEXT,
                    content_type TEXT NOT NULL,
                    question TEXT,
                    analysis TEXT,
                    image_base64 TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_chat_images_task_id_id ON chat_images(task_id, id);

                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT,
                    snippet TEXT,
                    extracted_text TEXT,
                    source_type TEXT NOT NULL DEFAULT 'web',
                    quality_score INTEGER NOT NULL DEFAULT 0,
                    used INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_sources_task_id_id ON sources(task_id, id);

                CREATE TABLE IF NOT EXISTS conversation_contexts (
                    task_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL DEFAULT '',
                    estimated_tokens INTEGER NOT NULL DEFAULT 0,
                    token_limit INTEGER NOT NULL DEFAULT 0,
                    warning_threshold INTEGER NOT NULL DEFAULT 0,
                    compact_threshold INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'empty',
                    compaction_count INTEGER NOT NULL DEFAULT 0,
                    last_compacted_event_id INTEGER,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );
                """
            )

    def create_task(self, task: dict[str, Any]) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO tasks (id, description, status, created_at, updated_at, result)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task["id"],
                    task["description"],
                    task["status"],
                    task["created_at"],
                    task["updated_at"],
                    task.get("result"),
                ),
            )

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT id, description, status, created_at, updated_at, result FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, description, status, created_at, updated_at, result
                FROM tasks
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def update_task(self, task_id: str, status: str, result: str | None, updated_at: str) -> dict[str, Any] | None:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE tasks
                SET status = ?, updated_at = ?, result = COALESCE(?, result)
                WHERE id = ?
                """,
                (status, updated_at, result, task_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_task(task_id)

    def delete_task(self, task_id: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return cursor.rowcount > 0

    def insert_event(self, task_id: str, event_type: str, created_at: str, payload: dict[str, Any]) -> int:
        payload_json = json.dumps(payload, ensure_ascii=False)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO events (task_id, event_type, created_at, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (task_id, event_type, created_at, payload_json),
            )
            event_id = int(cursor.lastrowid)
            if event_type == "screen_frame" and payload.get("image_base64"):
                self._connection.execute(
                    """
                    INSERT INTO screenshots (task_id, event_id, created_at, caption, title, url, image_base64)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        event_id,
                        created_at,
                        payload.get("caption"),
                        payload.get("title"),
                        payload.get("url"),
                        payload["image_base64"],
                    ),
                )
        return event_id

    def insert_chat_image(self, image: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO chat_images (
                    task_id, event_id, created_at, filename, content_type, question,
                    analysis, image_base64
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    image["task_id"],
                    image.get("event_id"),
                    image["created_at"],
                    image.get("filename"),
                    image["content_type"],
                    image.get("question"),
                    image.get("analysis"),
                    image["image_base64"],
                ),
            )
            image_id = int(cursor.lastrowid)
        saved = self.get_chat_image(image_id)
        if saved is None:
            raise RuntimeError("Imagem salva nao encontrada")
        return saved

    def update_chat_image_analysis(self, image_id: int, analysis: str) -> dict[str, Any] | None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE chat_images SET analysis = ? WHERE id = ?",
                (analysis, image_id),
            )
        return self.get_chat_image(image_id)

    def get_chat_image(self, image_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, task_id, event_id, created_at, filename, content_type,
                       question, analysis, image_base64
                FROM chat_images
                WHERE id = ?
                """,
                (image_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_chat_images(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, task_id, event_id, created_at, filename, content_type,
                       question, analysis, image_base64
                FROM chat_images
                WHERE task_id = ?
                ORDER BY id ASC
                """,
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_events(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, event_type, created_at, payload_json
                FROM events
                WHERE task_id = ?
                ORDER BY id ASC
                """,
                (task_id,),
            ).fetchall()
        events = []
        for row in rows:
            events.append(
                {
                    "event_id": int(row["id"]),
                    "type": row["event_type"],
                    "task_id": task_id,
                    "created_at": row["created_at"],
                    "payload": json.loads(row["payload_json"]),
                }
            )
        return events

    def get_context(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT task_id, summary, estimated_tokens, token_limit,
                       warning_threshold, compact_threshold, status,
                       compaction_count, last_compacted_event_id, updated_at
                FROM conversation_contexts
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
        return dict(row) if row else None

    def upsert_context(self, task_id: str, context: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO conversation_contexts (
                    task_id, summary, estimated_tokens, token_limit,
                    warning_threshold, compact_threshold, status,
                    compaction_count, last_compacted_event_id, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    summary = excluded.summary,
                    estimated_tokens = excluded.estimated_tokens,
                    token_limit = excluded.token_limit,
                    warning_threshold = excluded.warning_threshold,
                    compact_threshold = excluded.compact_threshold,
                    status = excluded.status,
                    compaction_count = excluded.compaction_count,
                    last_compacted_event_id = excluded.last_compacted_event_id,
                    updated_at = excluded.updated_at
                """,
                (
                    task_id,
                    context.get("summary", ""),
                    int(context.get("estimated_tokens", 0)),
                    int(context.get("token_limit", 0)),
                    int(context.get("warning_threshold", 0)),
                    int(context.get("compact_threshold", 0)),
                    context.get("status", "empty"),
                    int(context.get("compaction_count", 0)),
                    context.get("last_compacted_event_id"),
                    context["updated_at"],
                ),
            )
        saved = self.get_context(task_id)
        if saved is None:
            raise RuntimeError("Contexto salvo nao encontrado")
        return saved

    def upsert_source(self, task_id: str, source: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT id FROM sources WHERE task_id = ? AND url = ?",
                (task_id, source["url"]),
            ).fetchone()
            if existing:
                source_id = int(existing["id"])
                self._connection.execute(
                    """
                    UPDATE sources
                    SET title = COALESCE(?, title),
                        snippet = COALESCE(?, snippet),
                        extracted_text = COALESCE(?, extracted_text),
                        source_type = ?,
                        quality_score = ?,
                        used = ?,
                        created_at = ?
                    WHERE id = ?
                    """,
                    (
                        source.get("title"),
                        source.get("snippet"),
                        source.get("extracted_text"),
                        source.get("source_type", "web"),
                        int(source.get("quality_score", 0)),
                        1 if source.get("used") else 0,
                        source["created_at"],
                        source_id,
                    ),
                )
            else:
                cursor = self._connection.execute(
                    """
                    INSERT INTO sources (
                        task_id, url, title, snippet, extracted_text, source_type,
                        quality_score, used, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        source["url"],
                        source.get("title"),
                        source.get("snippet"),
                        source.get("extracted_text"),
                        source.get("source_type", "web"),
                        int(source.get("quality_score", 0)),
                        1 if source.get("used") else 0,
                        source["created_at"],
                    ),
                )
                source_id = int(cursor.lastrowid)
        saved = self.get_source(source_id)
        if saved is None:
            raise RuntimeError("Fonte salva nao encontrada")
        return saved

    def get_source(self, source_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, task_id, url, title, snippet, extracted_text, source_type,
                       quality_score, used, created_at
                FROM sources
                WHERE id = ?
                """,
                (source_id,),
            ).fetchone()
        if not row:
            return None
        source = dict(row)
        source["used"] = bool(source["used"])
        return source

    def list_sources(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, task_id, url, title, snippet, extracted_text, source_type,
                       quality_score, used, created_at
                FROM sources
                WHERE task_id = ?
                ORDER BY quality_score DESC, id ASC
                """,
                (task_id,),
            ).fetchall()
        sources = []
        for row in rows:
            source = dict(row)
            source["used"] = bool(source["used"])
            sources.append(source)
        return sources

    def close(self) -> None:
        with self._lock:
            self._connection.close()


database = Database()
