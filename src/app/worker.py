"""
Async worker that polls for crawl jobs and processes them.
Run with: uv run python -m app.worker
"""

import asyncio
import logging
import traceback
from typing import Optional

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from pydantic import BaseModel

from .bluesky.actor_feed import FetchBlueskyResult, fetch_actor_feed
from .database import (
    CrawlJob,
    get_cached_crawl_result,
    get_pending_crawl_job,
    save_crawl_result,
    update_crawl_job_status,
)
from .youtube.youtube_transcript import fetch_youtube_transcript

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FetchWebpageResult(BaseModel):
    success: bool
    error: Optional[str] = None
    markdown: Optional[str] = None
    html_length: Optional[int] = None
    final_url: Optional[str] = None


async def process_bluesky_job(job: CrawlJob):
    actor = job.request_url  # Assuming request_url holds the actor handle
    logger.info(f"Processing Bluesky job for actor: {actor}")

    # Run the crawler
    result: FetchBlueskyResult = await asyncio.to_thread(fetch_actor_feed, actor)

    if result.success:
        await save_crawl_result(
            job_id=job.id,
            final_url=result.profile_url,
            data=result.model_dump(),  # Convert Pydantic model to dict
            original_url=actor,
            success=True,
        )
    else:
        raise Exception(f"Bluesky crawl failed: {result.error}")


async def process_youtube_job(job: CrawlJob):
    url = job.request_url
    logger.info(f"Processing YouTube job for: {url}")

    # 1. Check Cache (12 hours = 43200 seconds)
    # User requested 6-12 hours for channels. Let's use 12 hours.
    # If it's a specific video, maybe we don't need to recrawl it ever?
    # But for simplicity, let's stick to the time-based cache.
    CACHE_DURATION = 12 * 60 * 60

    cached_result = await get_cached_crawl_result("youtube", url, CACHE_DURATION)
    if cached_result:
        logger.info(f"Found cached result for {url}. Skipping crawl.")
        await save_crawl_result(
            job_id=job.id,
            final_url=cached_result.final_url,
            data=cached_result.data,
            original_url=url,
            success=True,
            metadata={"cached_from": cached_result.metadata},
        )
        return

    # 2. Run Crawler
    # fetch_youtube_transcript is sync
    result = await asyncio.to_thread(fetch_youtube_transcript, url)

    if result.success:
        await save_crawl_result(
            job_id=job.id,
            final_url=result.video_url or url,
            data=result.model_dump(),  # Convert Pydantic model to dict
            original_url=url,
            success=True,
        )
    else:
        raise Exception(f"YouTube crawl failed: {result.error}")


async def process_crawl4ai_job(job: CrawlJob):
    url = job.request_url
    logger.info(f"Processing Crawl4AI job for URL: {url}")

    # 1. Check Cache (1 hour = 3600 seconds)
    CACHE_DURATION = 60 * 60

    cached_result = await get_cached_crawl_result("crawl4ai", url, CACHE_DURATION)
    if cached_result:
        logger.info(f"Found cached result for {url}. Skipping crawl.")
        await save_crawl_result(
            job_id=job.id,
            final_url=cached_result.final_url,
            data=cached_result.data,
            original_url=url,
            success=True,
            metadata={"cached_from": cached_result.metadata},
        )
        return

    browser_config = BrowserConfig(headless=True, verbose=True)
    crawler_config = CrawlerRunConfig(cache_mode=CacheMode.ENABLED)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        crawl_result = await crawler.arun(url=url, config=crawler_config)

        if crawl_result.success:
            result = FetchWebpageResult(
                success=True,
                markdown=crawl_result.markdown.raw_markdown
                if hasattr(crawl_result.markdown, "raw_markdown")
                else str(crawl_result.markdown),
                html_length=len(crawl_result.html) if crawl_result.html else 0,
                final_url=crawl_result.url,
            )
            await save_crawl_result(
                job_id=job.id,
                final_url=result.final_url,
                data=result.model_dump(),
                original_url=url,
                success=True,
            )
        else:
            raise Exception(f"Crawl failed: {crawl_result.error_message}")


async def run_worker():
    logger.info("Worker started. Polling for jobs...")
    while True:
        try:
            job = await get_pending_crawl_job()
            if job:
                logger.info(f"Picked up job: {job.id} ({job.worker})")
                await update_crawl_job_status(job.id, "processing")

                try:
                    if job.worker == "bluesky":
                        await process_bluesky_job(job)
                    elif job.worker == "youtube":
                        await process_youtube_job(job)
                    elif job.worker == "crawl4ai":
                        await process_crawl4ai_job(job)
                    else:
                        raise ValueError(f"Unknown worker type: {job.worker}")

                    await update_crawl_job_status(job.id, "completed")
                    logger.info(f"Job {job.id} completed successfully.")

                except Exception as e:
                    logger.error(f"Job {job.id} failed: {e}")
                    traceback.print_exc()
                    await update_crawl_job_status(
                        job.id, "failed", metadata={"error": str(e)}
                    )
            else:
                # No jobs, sleep
                await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"Worker loop error: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run_worker())
