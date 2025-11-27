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


async def create_crawl_job(
    worker: str,
    request_url: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> CrawlJob:
    now = datetime.utcnow()
    job = CrawlJob(
        id=str(uuid.uuid4()),
        status="pending",
        worker=worker,
        request_url=request_url,
        metadata=metadata,
        created_at=now,
        updated_at=now,
    )

    meta_json = json.dumps(job.metadata) if job.metadata else None

    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO crawl_jobs (id, status, worker, request_url, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                job.id,
                job.status,
                job.worker,
                job.request_url,
                meta_json,
                job.created_at.isoformat(),
                job.updated_at.isoformat(),
            ),
        )
        await db.commit()
    return job


async def get_pending_crawl_job(
    worker_type: Optional[str] = None,
) -> Optional[CrawlJob]:
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
                return CrawlJob(
                    id=row["id"],
                    status=row["status"],
                    worker=row["worker"],
                    request_url=row["request_url"],
                    metadata=json.loads(row["metadata"]) if row["metadata"] else None,
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
    return None


async def update_crawl_job_status(
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


async def save_crawl_result(
    job_id: str,
    final_url: str,
    data: Dict[str, Any],
    original_url: Optional[str] = None,
    success: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
) -> CrawlResult:
    now = datetime.utcnow()
    result = CrawlResult(
        id=str(uuid.uuid4()),
        job_id=job_id,
        original_url=original_url,
        final_url=final_url,
        data=data,
        success=success,
        metadata=metadata,
        created_at=now,
    )

    data_json = json.dumps(result.data)
    meta_json = json.dumps(result.metadata) if result.metadata else None

    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO crawl_results (id, job_id, original_url, final_url, data, success, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.id,
                result.job_id,
                result.original_url,
                result.final_url,
                data_json,
                result.success,
                meta_json,
                result.created_at.isoformat(),
            ),
        )
        await db.commit()
    return result


async def get_cached_crawl_result(
    worker: str, request_url: str, cache_duration_seconds: int
) -> Optional[CrawlResult]:
    """
    Check if there is a recent successful crawl for the given worker and URL.
    Returns the CrawlResult from the most recent result if found and within the cache duration.
    """
    async with get_db() as db:
        # Calculate the cutoff time
        cutoff_time = datetime.utcnow().timestamp() - cache_duration_seconds

        # We need to join crawl_jobs and crawl_results to check worker type and success
        # We select the most recent one
        query = """
            SELECT r.id, r.job_id, r.original_url, r.final_url, r.data, r.success, r.metadata, r.created_at
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
                # Check time - use job created_at for cache expiry
                # We need to fetch the job's created_at separately or include it in query
                result_time = datetime.fromisoformat(row["created_at"])
                if result_time.timestamp() > cutoff_time:
                    return CrawlResult(
                        id=row["id"],
                        job_id=row["job_id"],
                        original_url=row["original_url"],
                        final_url=row["final_url"],
                        data=json.loads(row["data"]),
                        success=bool(row["success"]),
                        metadata=json.loads(row["metadata"]) if row["metadata"] else None,
                        created_at=result_time,
                    )
    return None
