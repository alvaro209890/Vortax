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
                    user_id TEXT,
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

                CREATE TABLE IF NOT EXISTS generated_projects (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    root_path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    project_type TEXT NOT NULL DEFAULT 'generic',
                    main_file TEXT,
                    file_count INTEGER NOT NULL DEFAULT 0,
                    total_size INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    UNIQUE(task_id, root_path)
                );

                CREATE INDEX IF NOT EXISTS idx_generated_projects_task_id_root ON generated_projects(task_id, root_path);

                CREATE TABLE IF NOT EXISTS generated_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    extension TEXT NOT NULL DEFAULT '',
                    modified_at REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY(project_id) REFERENCES generated_projects(id) ON DELETE CASCADE,
                    UNIQUE(task_id, path)
                );

                CREATE INDEX IF NOT EXISTS idx_generated_files_task_id_project ON generated_files(task_id, project_id, path);

                CREATE TABLE IF NOT EXISTS task_steps (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    tool_hint TEXT,
                    acceptance_criteria_json TEXT NOT NULL DEFAULT '[]',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    UNIQUE(task_id, position)
                );

                CREATE INDEX IF NOT EXISTS idx_task_steps_task_id_position ON task_steps(task_id, position);
                """
            )
            columns = {
                str(row["name"])
                for row in self._connection.execute("PRAGMA table_info(tasks)").fetchall()
            }
            if "user_id" not in columns:
                self._connection.execute("ALTER TABLE tasks ADD COLUMN user_id TEXT")
            if "title" not in columns:
                self._connection.execute("ALTER TABLE tasks ADD COLUMN title TEXT")
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_user_id_created_at ON tasks(user_id, created_at DESC)"
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS code_snippets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tags TEXT NOT NULL DEFAULT '[]',
                    language TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    content_hash TEXT NOT NULL DEFAULT '',
                    use_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_code_snippets_language ON code_snippets(language)"
            )

            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL DEFAULT 'context',
                    key TEXT NOT NULL,
                    content TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 5,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_memories_user_type ON user_memories(user_id, memory_type)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_memories_user_priority ON user_memories(user_id, priority DESC)"
            )

            # Adicionar checkpoint_json ao conversation_contexts se nao existir
            cc_cols = {
                str(row["name"])
                for row in self._connection.execute("PRAGMA table_info(conversation_contexts)").fetchall()
            }
            if "checkpoint_json" not in cc_cols:
                self._connection.execute(
                    "ALTER TABLE conversation_contexts ADD COLUMN checkpoint_json TEXT NOT NULL DEFAULT '{}'"
                )

    def add_snippet(self, tags: list[str], language: str, description: str, content: str) -> int:
        import hashlib
        from datetime import datetime, timezone
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT id FROM code_snippets WHERE content_hash = ?", (content_hash,)
            ).fetchone()
            if existing:
                return int(existing["id"])
            cursor = self._connection.execute(
                "INSERT INTO code_snippets (tags, language, description, content, content_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    json.dumps(tags, ensure_ascii=False),
                    language,
                    description,
                    content,
                    content_hash,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def search_snippets(self, query: str, language: str | None = None, limit: int = 3) -> list[dict[str, Any]]:
        terms = [w.lower() for w in query.split() if len(w) >= 3]
        if not terms:
            return []
        with self._lock:
            if language:
                rows = self._connection.execute(
                    "SELECT * FROM code_snippets WHERE language = ? ORDER BY use_count DESC LIMIT 100",
                    (language,),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT * FROM code_snippets ORDER BY use_count DESC LIMIT 200"
                ).fetchall()
        scored: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            row_dict = dict(row)
            haystack = (str(row_dict.get("description") or "") + " " + str(row_dict.get("tags") or "")).lower()
            score = sum(1 for t in terms if t in haystack)
            if score > 0:
                scored.append((score, row_dict))
        scored.sort(key=lambda x: (-x[0], -x[1].get("use_count", 0)))
        return [r for _, r in scored[:limit]]

    def increment_snippet_use(self, snippet_id: int) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE code_snippets SET use_count = use_count + 1 WHERE id = ?", (snippet_id,)
            )

    def add_user_memory(self, user_id: str, memory_type: str, key: str, content: str, priority: int = 5) -> int:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO user_memories (user_id, memory_type, key, content, priority, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, memory_type, key[:200], content, priority, now, now),
            )
            return int(cursor.lastrowid)

    def update_user_memory(self, memory_id: int, user_id: str, content: str, priority: int | None = None) -> bool:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connection:
            if priority is not None:
                cursor = self._connection.execute(
                    "UPDATE user_memories SET content = ?, priority = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                    (content, priority, now, memory_id, user_id),
                )
            else:
                cursor = self._connection.execute(
                    "UPDATE user_memories SET content = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                    (content, now, memory_id, user_id),
                )
            return cursor.rowcount > 0

    def delete_user_memory(self, memory_id: int, user_id: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM user_memories WHERE id = ? AND user_id = ?", (memory_id, user_id)
            )
            return cursor.rowcount > 0

    def list_user_memories(self, user_id: str, memory_type: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            if memory_type:
                rows = self._connection.execute(
                    """
                    SELECT id, user_id, memory_type, key, content, priority, created_at, updated_at
                    FROM user_memories
                    WHERE user_id = ?
                    ORDER BY priority DESC, updated_at DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    """
                    SELECT id, user_id, memory_type, key, content, priority, created_at, updated_at
                    FROM user_memories
                    WHERE user_id = ?
                    ORDER BY priority DESC, updated_at DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def search_user_memories(self, user_id: str, terms: list[str], limit: int = 5) -> list[dict[str, Any]]:
        terms = [t.lower() for t in terms if len(t) >= 2]
        if not terms:
            return self.list_user_memories(user_id, limit=limit)
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, user_id, memory_type, key, content, priority, created_at, updated_at FROM user_memories WHERE user_id = ? ORDER BY priority DESC, updated_at DESC LIMIT 500",
                (user_id,),
            ).fetchall()
        scored: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            row_dict = dict(row)
            haystack = (str(row_dict.get("key") or "") + " " + str(row_dict.get("content") or "")).lower()
            score = sum(1 for t in terms if t in haystack)
            if score > 0:
                scored.append((score, row_dict))
        scored.sort(key=lambda x: (-x[0], -x[1].get("priority", 0)))
        return [r for _, r in scored[:limit]]

    def list_running_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, description FROM tasks WHERE status = 'running'"
            ).fetchall()
        return [dict(row) for row in rows]

    def create_task(self, task: dict[str, Any]) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO tasks (id, user_id, description, status, created_at, updated_at, result)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task["id"],
                    task.get("user_id"),
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
                "SELECT id, user_id, description, title, status, created_at, updated_at, result FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_tasks(self, user_id: str | None = None) -> list[dict[str, Any]]:
        if user_id is None:
            return []
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, user_id, description, title, status, created_at, updated_at, result
                FROM tasks
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_task_title(self, task_id: str, title: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE tasks SET title = ? WHERE id = ? AND (title IS NULL OR title = '')",
                (title[:120], task_id),
            )

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
        # Screenshot insert movido para fora da secao critica
        if event_type == "screen_frame" and payload.get("image_base64"):
            self.insert_screenshot(task_id, event_id, created_at, payload)
        return event_id

    def insert_events_batch(
        self,
        task_id: str,
        events: list[tuple[str, str, dict[str, Any]]],
    ) -> list[int]:
        """Insere multiplos eventos em uma unica transacao.
        Cada item em events deve ser (event_type, created_at, payload).
        Retorna a lista de event_id gerados.
        """
        if not events:
            return []
        with self._lock, self._connection:
            cursor = self._connection.executemany(
                """
                INSERT INTO events (task_id, event_type, created_at, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (task_id, event_type, created_at, json.dumps(payload, ensure_ascii=False))
                    for event_type, created_at, payload in events
                ],
            )
            first_id = int(cursor.lastrowid)
        event_ids = list(range(first_id, first_id + len(events)))
        # Insere screenshots fora da secao critica
        for event_id, (event_type, created_at, payload) in zip(event_ids, events):
            if event_type == "screen_frame" and payload.get("image_base64"):
                self.insert_screenshot(task_id, event_id, created_at, payload)
        return event_ids

    def insert_screenshot(
        self,
        task_id: str,
        event_id: int,
        created_at: str,
        payload: dict[str, Any],
    ) -> None:
        with self._lock, self._connection:
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
                       compaction_count, last_compacted_event_id, updated_at,
                       checkpoint_json
                FROM conversation_contexts
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        try:
            result["checkpoint_json"] = json.loads(str(result.get("checkpoint_json") or "{}"))
        except (json.JSONDecodeError, TypeError):
            result["checkpoint_json"] = {}
        return result

    def upsert_context(self, task_id: str, context: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO conversation_contexts (
                    task_id, summary, estimated_tokens, token_limit,
                    warning_threshold, compact_threshold, status,
                    compaction_count, last_compacted_event_id, updated_at,
                    checkpoint_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    summary = excluded.summary,
                    estimated_tokens = excluded.estimated_tokens,
                    token_limit = excluded.token_limit,
                    warning_threshold = excluded.warning_threshold,
                    compact_threshold = excluded.compact_threshold,
                    status = excluded.status,
                    compaction_count = excluded.compaction_count,
                    last_compacted_event_id = excluded.last_compacted_event_id,
                    updated_at = excluded.updated_at,
                    checkpoint_json = excluded.checkpoint_json
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
                    json.dumps(context.get("checkpoint_json") or {}, ensure_ascii=False),
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

    def sync_generated_projects(self, task_id: str, projects: list[dict[str, Any]], files: list[dict[str, Any]]) -> None:
        project_ids = {str(project["id"]) for project in projects}
        file_paths = {str(file["path"]) for file in files}
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM generated_files WHERE task_id = ? AND path NOT IN (%s)" % ",".join("?" for _ in file_paths)
                if file_paths
                else "DELETE FROM generated_files WHERE task_id = ?",
                (task_id, *file_paths) if file_paths else (task_id,),
            )
            self._connection.execute(
                "DELETE FROM generated_projects WHERE task_id = ? AND id NOT IN (%s)" % ",".join("?" for _ in project_ids)
                if project_ids
                else "DELETE FROM generated_projects WHERE task_id = ?",
                (task_id, *project_ids) if project_ids else (task_id,),
            )
            for project in projects:
                self._connection.execute(
                    """
                    INSERT INTO generated_projects (
                        id, task_id, root_path, name, project_type, main_file,
                        file_count, total_size, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        root_path = excluded.root_path,
                        name = excluded.name,
                        project_type = excluded.project_type,
                        main_file = excluded.main_file,
                        file_count = excluded.file_count,
                        total_size = excluded.total_size,
                        updated_at = excluded.updated_at
                    """,
                    (
                        project["id"],
                        task_id,
                        project["root_path"],
                        project["name"],
                        project.get("project_type", "generic"),
                        project.get("main_file"),
                        int(project.get("file_count", 0)),
                        int(project.get("total_size", 0)),
                        project["created_at"],
                        project["updated_at"],
                    ),
                )
            for file in files:
                self._connection.execute(
                    """
                    INSERT INTO generated_files (
                        task_id, project_id, path, size_bytes, extension,
                        modified_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task_id, path) DO UPDATE SET
                        project_id = excluded.project_id,
                        size_bytes = excluded.size_bytes,
                        extension = excluded.extension,
                        modified_at = excluded.modified_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        task_id,
                        file["project_id"],
                        file["path"],
                        int(file.get("size_bytes", file.get("size", 0))),
                        file.get("extension", ""),
                        float(file.get("modified_at", 0)),
                        file["created_at"],
                        file["updated_at"],
                    ),
                )

    def list_generated_projects(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, task_id, root_path, name, project_type, main_file,
                       file_count, total_size, created_at, updated_at
                FROM generated_projects
                WHERE task_id = ?
                ORDER BY root_path ASC
                """,
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_generated_files(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT f.id, f.task_id, f.project_id, f.path, f.size_bytes,
                       f.extension, f.modified_at, f.created_at, f.updated_at,
                       p.name AS project_name, p.root_path AS project_root,
                       p.project_type AS project_type
                FROM generated_files f
                JOIN generated_projects p ON p.id = f.project_id
                WHERE f.task_id = ?
                ORDER BY p.root_path ASC, f.path ASC
                """,
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def replace_task_steps(self, task_id: str, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM task_steps WHERE task_id = ?", (task_id,))
            for step in steps:
                self._connection.execute(
                    """
                    INSERT INTO task_steps (
                        id, task_id, position, label, detail, status, tool_hint,
                        acceptance_criteria_json, evidence_json, started_at,
                        finished_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        step["id"],
                        task_id,
                        int(step["position"]),
                        step["label"],
                        step.get("detail", ""),
                        step.get("status", "pending"),
                        step.get("tool_hint"),
                        json.dumps(step.get("acceptance_criteria", []), ensure_ascii=False),
                        json.dumps(step.get("evidence", []), ensure_ascii=False),
                        step.get("started_at"),
                        step.get("finished_at"),
                        step["updated_at"],
                    ),
                )
        return self.list_task_steps(task_id)

    def list_task_steps(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, task_id, position, label, detail, status, tool_hint,
                       acceptance_criteria_json, evidence_json, started_at,
                       finished_at, updated_at
                FROM task_steps
                WHERE task_id = ?
                ORDER BY position ASC
                """,
                (task_id,),
            ).fetchall()
        steps = []
        for row in rows:
            step = dict(row)
            step["acceptance_criteria"] = json.loads(step.pop("acceptance_criteria_json") or "[]")
            step["evidence"] = json.loads(step.pop("evidence_json") or "[]")
            steps.append(step)
        return steps

    def get_task_step(self, step_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, task_id, position, label, detail, status, tool_hint,
                       acceptance_criteria_json, evidence_json, started_at,
                       finished_at, updated_at
                FROM task_steps
                WHERE id = ?
                """,
                (step_id,),
            ).fetchone()
        if not row:
            return None
        step = dict(row)
        step["acceptance_criteria"] = json.loads(step.pop("acceptance_criteria_json") or "[]")
        step["evidence"] = json.loads(step.pop("evidence_json") or "[]")
        return step

    def update_task_step(self, step_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        if not updates:
            return self.get_task_step(step_id)

        allowed = {
            "status",
            "detail",
            "tool_hint",
            "acceptance_criteria",
            "evidence",
            "started_at",
            "finished_at",
            "updated_at",
        }
        fields = []
        values = []
        for key, value in updates.items():
            if key not in allowed:
                continue
            if key == "acceptance_criteria":
                fields.append("acceptance_criteria_json = ?")
                values.append(json.dumps(value or [], ensure_ascii=False))
            elif key == "evidence":
                fields.append("evidence_json = ?")
                values.append(json.dumps(value or [], ensure_ascii=False))
            else:
                fields.append(f"{key} = ?")
                values.append(value)

        if not fields:
            return self.get_task_step(step_id)

        with self._lock, self._connection:
            self._connection.execute(
                f"UPDATE task_steps SET {', '.join(fields)} WHERE id = ?",
                (*values, step_id),
            )
        return self.get_task_step(step_id)

    def close(self) -> None:
        with self._lock:
            self._connection.close()


database = Database()
