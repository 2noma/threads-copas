from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_metric(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


class WorkbenchStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    product_url TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    image_url TEXT NOT NULL DEFAULT '',
                    memo TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    draft TEXT NOT NULL DEFAULT '',
                    sns_draft TEXT NOT NULL DEFAULT '',
                    image_brief TEXT NOT NULL DEFAULT '',
                    blog_final TEXT NOT NULL DEFAULT '',
                    sns_final TEXT NOT NULL DEFAULT '',
                    generated_image_url TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]',
                    publish_url TEXT NOT NULL DEFAULT '',
                    error_message TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS logs (
                    id TEXT PRIMARY KEY,
                    job_id TEXT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS media_candidates (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_url TEXT NOT NULL DEFAULT '',
                    image_url TEXT NOT NULL DEFAULT '',
                    timestamp_label TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    creator TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    no_captions INTEGER NOT NULL DEFAULT 0,
                    no_tts INTEGER NOT NULL DEFAULT 0,
                    product_visible INTEGER NOT NULL DEFAULT 0,
                    permission_reviewed INTEGER NOT NULL DEFAULT 0,
                    review_status TEXT NOT NULL DEFAULT 'CANDIDATE',
                    approved_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );

                CREATE TABLE IF NOT EXISTS threads_profiles (
                    profile_key TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    threads_user_id TEXT NOT NULL DEFAULT '',
                    username TEXT NOT NULL DEFAULT '',
                    access_token TEXT NOT NULL DEFAULT '',
                    expires_at TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(conn, "jobs", "image_url", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "jobs", "sns_draft", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "jobs", "image_brief", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "jobs", "blog_final", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "jobs", "sns_final", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "jobs", "generated_image_url", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "jobs", "threads_profile_key", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "jobs", "threads_post_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "jobs", "threads_reply_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "jobs", "threads_permalink", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "jobs", "threads_published_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "jobs", "threads_views", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "jobs", "threads_likes", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "jobs", "threads_replies", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "jobs", "threads_reposts", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "jobs", "threads_quotes", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "jobs", "threads_shares", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "jobs", "threads_insights_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "jobs", "threads_insights_error", "TEXT NOT NULL DEFAULT ''")

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        definition: str,
    ) -> None:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        if column_name not in {row["name"] for row in rows}:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def get_settings(self) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def set_settings(self, settings: dict[str, Any]) -> dict[str, str]:
        now = utc_now()
        with self._connect() as conn:
            for key, value in settings.items():
                conn.execute(
                    """
                    INSERT INTO settings (key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (key, "" if value is None else str(value), now),
                )
        return self.get_settings()

    def add_job(
        self,
        product_url: str,
        product_name: str,
        memo: str = "",
        image_url: str = "",
    ) -> dict[str, Any]:
        now = utc_now()
        job_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, product_url, product_name, image_url, memo, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'READY', ?, ?)
                """,
                (
                    job_id,
                    product_url.strip(),
                    product_name.strip(),
                    image_url.strip(),
                    memo.strip(),
                    now,
                    now,
                ),
            )
        self.add_log(job_id, "INFO", "Job queued")
        job = self.get_job(job_id)
        if job is None:
            raise RuntimeError("Queued job could not be loaded")
        return job

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [self._row_to_job(row) for row in rows]

    def get_known_product_context(self, product_url: str) -> dict[str, str]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT product_name, image_url
                FROM jobs
                WHERE product_url = ?
                  AND product_name != ''
                  AND product_name != '상품명 자동 확인 필요'
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (product_url.strip(),),
            ).fetchone()
        if row is None:
            return {}
        return {"product_name": row["product_name"], "image_url": row["image_url"]}

    def get_known_campaign_context(self, product_url: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT title, sns_draft, image_brief, blog_final, sns_final, tags, image_url
                FROM jobs
                WHERE product_url = ?
                  AND status = 'CAMPAIGN_READY'
                  AND sns_draft != ''
                  AND sns_draft NOT LIKE '%상품 상세를 자동으로 충분히 읽지 못했습니다%'
                  AND product_name != '상품명 자동 확인 필요'
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (product_url.strip(),),
            ).fetchone()
        if row is None:
            return {}
        context = dict(row)
        try:
            context["tags"] = json.loads(context.get("tags") or "[]")
        except json.JSONDecodeError:
            context["tags"] = []
        return context

    def update_job_draft(
        self,
        job_id: str,
        title: str,
        draft: str,
        tags: list[str] | None = None,
        image_url: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            if image_url is None:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'DRAFTED',
                        title = ?,
                        draft = ?,
                        tags = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (title, draft, json.dumps(tags or [], ensure_ascii=False), now, job_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'DRAFTED',
                        title = ?,
                        draft = ?,
                        tags = ?,
                        image_url = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (title, draft, json.dumps(tags or [], ensure_ascii=False), image_url, now, job_id),
                )
        self.add_log(job_id, "INFO", "Draft generated")
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def update_job_campaign(
        self,
        job_id: str,
        sns_draft: str,
        image_brief: str,
        blog_final: str,
        sns_final: str,
        title: str,
        tags: list[str] | None = None,
        image_url: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            if image_url is None:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'CAMPAIGN_READY',
                        title = ?,
                        draft = ?,
                        sns_draft = ?,
                        image_brief = ?,
                        blog_final = ?,
                        sns_final = ?,
                        tags = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        title,
                        blog_final,
                        sns_draft,
                        image_brief,
                        blog_final,
                        sns_final,
                        json.dumps(tags or [], ensure_ascii=False),
                        now,
                        job_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'CAMPAIGN_READY',
                        title = ?,
                        draft = ?,
                        sns_draft = ?,
                        image_brief = ?,
                        blog_final = ?,
                        sns_final = ?,
                        image_url = ?,
                        tags = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        title,
                        blog_final,
                        sns_draft,
                        image_brief,
                        blog_final,
                        sns_final,
                        image_url.strip(),
                        json.dumps(tags or [], ensure_ascii=False),
                        now,
                        job_id,
                    ),
                )
        self.add_log(job_id, "INFO", "Campaign generated")
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def update_job_generated_image(self, job_id: str, generated_image_url: str) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET generated_image_url = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (generated_image_url.strip(), now, job_id),
            )
        self.add_log(job_id, "INFO", "Generated ad image saved")
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def update_job_threads_draft(
        self,
        job_id: str,
        text: str,
        comment_text: str = "",
        title: str = "",
        tags: list[str] | None = None,
        image_url: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            if image_url is None:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'THREADS_DRAFT_READY',
                        title = ?,
                        sns_draft = ?,
                        sns_final = ?,
                        tags = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        title.strip(),
                        text,
                        comment_text.strip() or text,
                        json.dumps(tags or [], ensure_ascii=False),
                        now,
                        job_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'THREADS_DRAFT_READY',
                        title = ?,
                        sns_draft = ?,
                        sns_final = ?,
                        image_url = ?,
                        tags = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        title.strip(),
                        text,
                        comment_text.strip() or text,
                        image_url.strip(),
                        json.dumps(tags or [], ensure_ascii=False),
                        now,
                        job_id,
                    ),
                )
        self.add_log(job_id, "INFO", "Threads draft generated")
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def add_media_candidate(
        self,
        job_id: str,
        source: str,
        source_url: str = "",
        image_url: str = "",
        timestamp_label: str = "",
        title: str = "",
        creator: str = "",
        notes: str = "",
        no_captions: bool = False,
        no_tts: bool = False,
        product_visible: bool = False,
        permission_reviewed: bool = False,
    ) -> dict[str, Any]:
        if self.get_job(job_id) is None:
            raise KeyError(job_id)
        now = utc_now()
        candidate_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO media_candidates (
                    id, job_id, source, source_url, image_url, timestamp_label,
                    title, creator, notes, no_captions, no_tts, product_visible,
                    permission_reviewed, review_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'CANDIDATE', ?, ?)
                """,
                (
                    candidate_id,
                    job_id,
                    source.strip().lower(),
                    source_url.strip(),
                    image_url.strip(),
                    timestamp_label.strip(),
                    title.strip(),
                    creator.strip(),
                    notes.strip(),
                    int(no_captions),
                    int(no_tts),
                    int(product_visible),
                    int(permission_reviewed),
                    now,
                    now,
                ),
            )
        self.add_log(job_id, "INFO", "Media candidate added")
        candidate = self.get_media_candidate(candidate_id)
        if candidate is None:
            raise RuntimeError("Media candidate could not be loaded")
        return candidate

    def get_media_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM media_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
        return self._row_to_media_candidate(row) if row else None

    def list_media_candidates(self, job_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM media_candidates
                WHERE job_id = ?
                ORDER BY created_at DESC
                """,
                (job_id,),
            ).fetchall()
        return [self._row_to_media_candidate(row) for row in rows]

    def approve_media_candidate(self, candidate_id: str) -> dict[str, Any]:
        candidate = self.get_media_candidate(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        image_url = candidate["image_url"].strip()
        if not image_url:
            raise ValueError("image_url is required before approving a media candidate")
        if candidate["product_visible"]:
            raise ValueError("상품이 보이는 이미지는 사용할 수 없습니다")
        if not candidate["permission_reviewed"]:
            raise ValueError("무료/오픈 이미지 권한 검토가 필요합니다")
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE media_candidates
                SET review_status = CASE WHEN id = ? THEN 'APPROVED' ELSE 'REJECTED' END,
                    approved_at = CASE WHEN id = ? THEN ? ELSE approved_at END,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (candidate_id, candidate_id, now, now, candidate["job_id"]),
            )
            conn.execute(
                """
                UPDATE jobs
                SET image_url = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (image_url, now, candidate["job_id"]),
            )
        self.add_log(candidate["job_id"], "INFO", "Media candidate approved")
        approved = self.get_media_candidate(candidate_id)
        if approved is None:
            raise KeyError(candidate_id)
        return approved

    def reject_media_candidate(self, candidate_id: str) -> dict[str, Any]:
        candidate = self.get_media_candidate(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE media_candidates
                SET review_status = 'REJECTED',
                    updated_at = ?
                WHERE id = ?
                """,
                (now, candidate_id),
            )
        self.add_log(candidate["job_id"], "INFO", "Media candidate rejected")
        rejected = self.get_media_candidate(candidate_id)
        if rejected is None:
            raise KeyError(candidate_id)
        return rejected

    def upsert_threads_profile(
        self,
        profile_key: str,
        display_name: str,
        notes: str = "",
    ) -> dict[str, Any]:
        clean_key = profile_key.strip()
        clean_name = display_name.strip()
        if not clean_key or not clean_name:
            raise ValueError("profile_key and display_name are required")
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO threads_profiles (
                    profile_key, display_name, notes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(profile_key) DO UPDATE SET
                    display_name = excluded.display_name,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                (clean_key, clean_name, notes.strip(), now, now),
            )
        profile = self.get_threads_profile(clean_key)
        if profile is None:
            raise RuntimeError("Threads profile could not be loaded")
        return profile

    def list_threads_profiles(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM threads_profiles
                WHERE threads_user_id != ''
                  AND access_token != ''
                ORDER BY display_name, profile_key
                """
            ).fetchall()
        return [self._row_to_threads_profile(row) for row in rows]

    def list_threads_publish_records(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    jobs.id AS job_id,
                    jobs.product_name,
                    jobs.product_url,
                    jobs.threads_profile_key AS profile_key,
                    jobs.threads_post_id,
                    jobs.threads_reply_id,
                    jobs.threads_permalink,
                    jobs.threads_published_at,
                    jobs.threads_views,
                    jobs.threads_likes,
                    jobs.threads_replies,
                    jobs.threads_reposts,
                    jobs.threads_quotes,
                    jobs.threads_shares,
                    jobs.threads_insights_at,
                    jobs.threads_insights_error,
                    jobs.sns_final AS published_text,
                    threads_profiles.display_name,
                    threads_profiles.username
                FROM jobs
                LEFT JOIN threads_profiles
                  ON threads_profiles.profile_key = jobs.threads_profile_key
                WHERE jobs.status = 'THREADS_PUBLISHED'
                  AND jobs.threads_post_id != ''
                ORDER BY jobs.threads_published_at DESC, jobs.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_threads_publish_record(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    jobs.id AS job_id,
                    jobs.product_name,
                    jobs.product_url,
                    jobs.threads_profile_key AS profile_key,
                    jobs.threads_post_id,
                    jobs.threads_reply_id,
                    jobs.threads_permalink,
                    jobs.threads_published_at,
                    jobs.threads_views,
                    jobs.threads_likes,
                    jobs.threads_replies,
                    jobs.threads_reposts,
                    jobs.threads_quotes,
                    jobs.threads_shares,
                    jobs.threads_insights_at,
                    jobs.threads_insights_error,
                    jobs.sns_final AS published_text,
                    threads_profiles.display_name,
                    threads_profiles.username
                FROM jobs
                LEFT JOIN threads_profiles
                  ON threads_profiles.profile_key = jobs.threads_profile_key
                WHERE jobs.id = ?
                  AND jobs.status = 'THREADS_PUBLISHED'
                  AND jobs.threads_post_id != ''
                """,
                (job_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete_threads_publish_record(self, job_id: str) -> bool:
        clean_job_id = job_id.strip()
        if not clean_job_id:
            return False
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM jobs
                WHERE id = ?
                  AND status = 'THREADS_PUBLISHED'
                  AND threads_post_id != ''
                """,
                (clean_job_id,),
            ).fetchone()
            if row is None:
                return False
            conn.execute("DELETE FROM media_candidates WHERE job_id = ?", (clean_job_id,))
            conn.execute("DELETE FROM logs WHERE job_id = ?", (clean_job_id,))
            conn.execute("DELETE FROM jobs WHERE id = ?", (clean_job_id,))
        return True

    def get_threads_profile(
        self,
        profile_key: str,
        include_token: bool = False,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM threads_profiles WHERE profile_key = ?",
                (profile_key.strip(),),
            ).fetchone()
        return self._row_to_threads_profile(row, include_token=include_token) if row else None

    def save_threads_profile_token(
        self,
        profile_key: str,
        threads_user_id: str,
        username: str,
        access_token: str,
        expires_in: int | None = None,
    ) -> dict[str, Any]:
        clean_key = profile_key.strip()
        expires_at = ""
        if expires_in:
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat(timespec="seconds")
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO threads_profiles (
                    profile_key, display_name, threads_user_id, username,
                    access_token, expires_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_key) DO UPDATE SET
                    threads_user_id = excluded.threads_user_id,
                    username = excluded.username,
                    access_token = excluded.access_token,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (
                    clean_key,
                    clean_key,
                    threads_user_id.strip(),
                    username.strip(),
                    access_token.strip(),
                    expires_at,
                    now,
                    now,
                ),
            )
        profile = self.get_threads_profile(clean_key)
        if profile is None:
            raise RuntimeError("Threads profile could not be loaded")
        return profile

    def disconnect_threads_profile(self, profile_key: str) -> dict[str, Any] | None:
        clean_key = profile_key.strip()
        now = utc_now()
        with self._connect() as conn:
            result = conn.execute(
                """
                UPDATE threads_profiles
                SET threads_user_id = '',
                    username = '',
                    access_token = '',
                    expires_at = '',
                    updated_at = ?
                WHERE profile_key = ?
                """,
                (now, clean_key),
            )
            if result.rowcount == 0:
                return None
        profile = self.get_threads_profile(clean_key)
        if profile is None:
            raise RuntimeError("Threads profile could not be loaded")
        return profile

    def mark_threads_published(
        self,
        job_id: str,
        profile_key: str,
        threads_post_id: str,
        threads_reply_id: str = "",
        threads_permalink: str = "",
        published_text: str = "",
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'THREADS_PUBLISHED',
                    threads_profile_key = ?,
                    threads_post_id = ?,
                    threads_reply_id = ?,
                    threads_permalink = ?,
                    threads_published_at = ?,
                    sns_final = CASE WHEN ? != '' THEN ? WHEN sns_final = '' THEN sns_draft ELSE sns_final END,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    profile_key.strip(),
                    threads_post_id.strip(),
                    threads_reply_id.strip(),
                    threads_permalink.strip(),
                    now,
                    published_text.strip(),
                    published_text.strip(),
                    now,
                    job_id,
                ),
            )
        self.add_log(job_id, "INFO", f"Threads published via {profile_key.strip()}")
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def update_threads_permalink(self, job_id: str, permalink: str) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET threads_permalink = ?,
                    updated_at = ?
                WHERE id = ?
                  AND status = 'THREADS_PUBLISHED'
                """,
                (permalink.strip(), now, job_id),
            )
        self.add_log(job_id, "INFO", "Threads permalink refreshed")
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def update_threads_insights(
        self,
        job_id: str,
        insights: dict[str, Any],
        error: str = "",
    ) -> dict[str, Any]:
        now = utc_now()
        clean_error = error.strip()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET threads_views = ?,
                    threads_likes = ?,
                    threads_replies = ?,
                    threads_reposts = ?,
                    threads_quotes = ?,
                    threads_shares = ?,
                    threads_insights_at = ?,
                    threads_insights_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    _safe_metric(insights.get("views")),
                    _safe_metric(insights.get("likes")),
                    _safe_metric(insights.get("replies")),
                    _safe_metric(insights.get("reposts")),
                    _safe_metric(insights.get("quotes")),
                    _safe_metric(insights.get("shares")),
                    now if not clean_error else "",
                    clean_error,
                    now,
                    job_id,
                ),
            )
        self.add_log(job_id, "ERROR" if clean_error else "INFO", clean_error or "Threads insights refreshed")
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def mark_publish_handoff(self, job_id: str, message: str) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'NEEDS_BROWSER_REVIEW',
                    error_message = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (message, now, job_id),
            )
        self.add_log(job_id, "INFO", message)
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def add_log(self, job_id: str | None, level: str, message: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO logs (id, job_id, level, message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), job_id, level, message, utc_now()),
            )

    def list_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM logs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _row_to_job(self, row: sqlite3.Row) -> dict[str, Any]:
        job = dict(row)
        try:
            job["tags"] = json.loads(job.get("tags") or "[]")
        except json.JSONDecodeError:
            job["tags"] = []
        return job

    def _row_to_media_candidate(self, row: sqlite3.Row) -> dict[str, Any]:
        candidate = dict(row)
        for key in ("no_captions", "no_tts", "product_visible", "permission_reviewed"):
            candidate[key] = bool(candidate[key])
        return candidate

    def _row_to_threads_profile(
        self,
        row: sqlite3.Row,
        include_token: bool = False,
    ) -> dict[str, Any]:
        profile = dict(row)
        token = profile.get("access_token", "")
        profile["is_connected"] = bool(profile.get("threads_user_id") and token)
        profile["token_preview"] = _token_preview(token)
        if not include_token:
            profile.pop("access_token", None)
        return profile


def _token_preview(token: str) -> str:
    clean = token.strip()
    if not clean:
        return ""
    if len(clean) <= 8:
        return "****"
    return f"{clean[:4]}...{clean[-4:]}"
