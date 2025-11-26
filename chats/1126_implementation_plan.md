# Database & Worker Architecture Implementation Plan

## 1. Architecture Overview

We are building a **Producer-Consumer** architecture to handle web crawling tasks. This decouples the "Request" (User wants a page) from the "Execution" (Browser opens page), allowing for better stability, retries, and concurrency control.

### The Components
1.  **Producer (Main App)**: Accepts user requests and inserts a "Job" into the database.
2.  **Broker (SQLite)**: Acts as the persistent queue and result store.
3.  **Consumers (Workers)**: Background processes that poll the DB for pending jobs, execute them, and save results.

### Tech Stack
*   **Language**: Python 3.13+
*   **Database**: SQLite (Simple, file-based, sufficient for MVP).
*   **Async Driver**: `aiosqlite` (Non-blocking DB I/O).
*   **Resilience**: `tenacity` (Retry logic).
*   **Validation**: `pydantic` (Data schemas).

---

## 2. Database Schema Design

We use a **Minimal Schema** approach. Instead of creating specific tables for every crawler type (e.g., `youtube_results`, `web_results`), we use a generic schema that handles all types via a flexible JSON payload.

### Table 1: `crawl_jobs` (The Queue)
Represents a unit of work to be done.

```sql
CREATE TABLE IF NOT EXISTS crawl_jobs (
    id TEXT PRIMARY KEY,                  -- UUID
    status TEXT NOT NULL,                 -- 'pending', 'processing', 'completed', 'failed'
    worker TEXT NOT NULL,                 -- 'crawl4ai', 'youtube', 'bluesky', 'extension'
    
    request_url TEXT,                     -- The URL/Query requested by the user
    
    metadata TEXT,                        -- JSON: { "error": "Timeout", "retry_count": 0 }
    
    created_at TEXT NOT NULL,             -- ISO8601
    updated_at TEXT NOT NULL
);

-- Index for Workers to find jobs fast
CREATE INDEX IF NOT EXISTS idx_crawl_jobs_status_worker 
ON crawl_jobs (status, worker);
```

### Table 2: `crawl_results` (The Library)
Stores the immutable output of a job.

```sql
CREATE TABLE IF NOT EXISTS crawl_results (
    id TEXT PRIMARY KEY,                  -- UUID
    job_id TEXT NOT NULL,                 -- FK to crawl_jobs
    
    original_url TEXT,                    -- The URL we tried to fetch
    final_url TEXT NOT NULL,              -- The actual URL found (handles redirects)
    
    data TEXT NOT NULL,                   -- JSON Payload (Markdown, Transcript, etc.)
    
    success BOOLEAN DEFAULT 1,            -- 1=Success, 0=Failed (Partial failure). Details in metadata.
    
    metadata TEXT,                        -- JSON: { "error": "404 Not Found", "http_status": 404 }
    
    created_at TEXT NOT NULL,             -- ISO8601
    
    FOREIGN KEY (job_id) REFERENCES crawl_jobs(id) ON DELETE CASCADE
);

-- Index for Cache Lookups
CREATE INDEX IF NOT EXISTS idx_crawl_results_urls 
ON crawl_results (final_url, created_at DESC);
```

---

## 3. Key Design Decisions & Discussions

### A. Unified Job Queue
**Decision**: Use a single table (`crawl_jobs`) with a `worker` discriminator.
**Reasoning**: Allows adding new fetchers (e.g., Reddit, Bluesky) without running database migrations. The Main App logic remains identical for all types.

### B. Generic `data` Column
**Decision**: Store content in a generic `data` TEXT column (JSON) instead of specific columns like `markdown` or `html`.
**Reasoning**:
*   A **Web Crawler** produces Markdown.
*   A **YouTube Crawler** produces a Transcript.
*   A **File Crawler** might produce a PDF path.
*   A generic JSON column `{ "markdown": "...", "transcript": "..." }` accommodates all without schema changes.

### C. No `session_id` in Database
**Decision**: The `crawl_jobs` table does **not** store the Chat Session ID.
**Reasoning**: Decoupling. The Crawler Service is a pure utility. It should not know about "Chats" or "Users". The Main App is responsible for mapping `job_id` -> `session_id` in its own application database.

### D. Handling Redirects (The "Two URL" Problem)
**Decision**: Store both `original_url` (requested) and `final_url` (resolved).
**Reasoning**:
*   User requests `http://google.com`.
*   Crawler lands on `https://www.google.com/`.
*   If we only stored the final URL, a future request for `http://google.com` would miss the cache. Storing both allows robust cache lookups.

---

## 4. Q&A (Context & Rationale)

**Q: Can `url` be null in results?**
**A:** No. `final_url` is mandatory. Every result must map to a concrete resource. However, `original_url` can be null if the job wasn't URL-based (e.g., a search query).

**Q: Should we store HTML?**
**A:** No. For LLM/Agent workflows, HTML is noise and bloats the DB. We only store the processed/extracted content (Markdown, JSON).

**Q: How does the Main App know a job is finished?**
**A:** Polling. Since SQLite doesn't support event listeners, the Main App polls `SELECT status FROM crawl_jobs WHERE id = ?` every few seconds.

**Q: Why `aiosqlite`?**
**A:** Standard `sqlite3` is blocking. If a crawler takes 10 seconds to save a large result, it would freeze the entire worker. `aiosqlite` allows concurrent operations.

---

## 5. Implementation Steps

### Step 1: Dependencies
Install the required libraries for the Async Worker stack.
```bash
uv add aiosqlite tenacity pydantic
```

### Step 2: Database Module (`src/database.py`)
*   Implement `init_db()` to create tables if they don't exist.
*   Implement `get_db()` context manager for `aiosqlite` connections.
*   Implement helper functions: `create_job()`, `get_pending_job()`, `save_result()`.

### Step 3: Worker Module (`src/worker.py`)
*   Implement the `run_worker()` loop.
*   **Polling Logic**:
    1.  Check DB for `status='pending'`.
    2.  If found, mark as `processing`.
    3.  Dispatch to specific crawler function based on `worker`.
    4.  Save output to `crawl_results`.
    5.  Mark job as `completed`.
*   **Error Handling**: Use `try/except` blocks to catch failures and update job status to `failed` with an error message.

### Step 4: Integration
*   Update `src/main.py` (or create a script) to launch the worker in the background (`asyncio.create_task(run_worker())`).
