import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, Optional

import aiosqlite
from pydantic import BaseModel

DB_PATH = "crawl_data.db"


# Database Models
class CrawlJob(BaseModel):
    id: str
    status: str
    worker: str
    request_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class CrawlResult(BaseModel):
    id: str
    job_id: str
    original_url: Optional[str] = None
    final_url: str
    data: Dict[str, Any]
    success: bool = True
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime


@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db():
    async with get_db() as db:
        # Table: crawl_jobs
        await db.execute("""
            CREATE TABLE IF NOT EXISTS crawl_jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                worker TEXT NOT NULL,
                request_url TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_crawl_jobs_status_worker 
            ON crawl_jobs (status, worker);
        """)

        # Table: crawl_results
        await db.execute("""
            CREATE TABLE IF NOT EXISTS crawl_results (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                original_url TEXT,
                final_url TEXT NOT NULL,
                data TEXT NOT NULL,
                success BOOLEAN DEFAULT 1,
                metadata TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES crawl_jobs(id) ON DELETE CASCADE
            );
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_crawl_results_urls 
            ON crawl_results (final_url, created_at DESC);
        """)
        await db.commit()


async def create_job(
    worker: str,
    request_url: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    job_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    meta_json = json.dumps(metadata) if metadata else None

    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO crawl_jobs (id, status, worker, request_url, metadata, created_at, updated_at)
            VALUES (?, 'pending', ?, ?, ?, ?, ?)
        """,
            (job_id, worker, request_url, meta_json, now, now),
        )
        await db.commit()
    return job_id


async def get_pending_job(
    worker_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    async with get_db() as db:
        query = "SELECT * FROM crawl_jobs WHERE status = 'pending'"
        params = []

        if worker_type:
            query += " AND worker = ?"
            params.append(worker_type)

        query += " ORDER BY created_at ASC LIMIT 1"

        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
    return None


async def update_job_status(
    job_id: str, status: str, metadata: Optional[Dict[str, Any]] = None
):
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        if metadata:
            # Merge existing metadata if needed, but for now just overwrite or update specific fields logic could be added.
            # Simpler: just update the metadata column if provided.
            # To do it properly, we might need to read first. For MVP, let's assume we pass full metadata or just error info.
            # Let's read existing first to be safe if we want to merge, but for now let's just update.
            meta_json = json.dumps(metadata)
            await db.execute(
                """
                UPDATE crawl_jobs 
                SET status = ?, updated_at = ?, metadata = ?
                WHERE id = ?
            """,
                (status, now, meta_json, job_id),
            )
        else:
            await db.execute(
                """
                UPDATE crawl_jobs 
                SET status = ?, updated_at = ?
                WHERE id = ?
            """,
                (status, now, job_id),
            )
        await db.commit()


async def save_result(
    job_id: str,
    final_url: str,
    data: Dict[str, Any],
    original_url: Optional[str] = None,
    success: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
):
    result_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    data_json = json.dumps(data)
    meta_json = json.dumps(metadata) if metadata else None

    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO crawl_results (id, job_id, original_url, final_url, data, success, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                result_id,
                job_id,
                original_url,
                final_url,
                data_json,
                success,
                meta_json,
                now,
            ),
        )
        await db.commit()


async def get_cached_result(
    worker: str, request_url: str, cache_duration_seconds: int
) -> Optional[Dict[str, Any]]:
    """
    Check if there is a recent successful crawl for the given worker and URL.
    Returns the data from the most recent result if found and within the cache duration.
    """
    async with get_db() as db:
        # Calculate the cutoff time
        cutoff_time = datetime.utcnow().timestamp() - cache_duration_seconds

        # We need to join crawl_jobs and crawl_results to check worker type and success
        # We select the most recent one
        query = """
            SELECT r.data, r.final_url, r.metadata, j.created_at
            FROM crawl_results r
            JOIN crawl_jobs j ON r.job_id = j.id
            WHERE j.worker = ? 
              AND j.request_url = ? 
              AND r.success = 1
            ORDER BY j.created_at DESC
            LIMIT 1
        """

        async with db.execute(query, (worker, request_url)) as cursor:
            row = await cursor.fetchone()
            if row:
                # Check time
                # created_at is stored as ISO string
                job_time = datetime.fromisoformat(row["created_at"])
                if job_time.timestamp() > cutoff_time:
                    return {
                        "data": json.loads(row["data"]),
                        "final_url": row["final_url"],
                        "metadata": json.loads(row["metadata"])
                        if row["metadata"]
                        else None,
                    }
    return None
