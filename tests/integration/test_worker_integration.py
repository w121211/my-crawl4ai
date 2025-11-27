import asyncio
import logging

from app.database import create_crawl_job, get_db, init_db
from app.worker import run_worker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_integration():
    # 1. Init DB
    await init_db()
    logger.info("DB Initialized")

    # 2. Create a job
    job = await create_crawl_job(
        worker="crawl4ai", request_url="https://example.com", metadata={"test": "true"}
    )
    logger.info(f"Created job: {job.id}")

    # 3. Run worker in background
    worker_task = asyncio.create_task(run_worker())

    # 4. Wait for job completion
    # We poll the DB to check status
    for _ in range(30):  # Wait up to 60 seconds
        await asyncio.sleep(2)
        async with get_db() as db:
            async with db.execute(
                "SELECT status FROM crawl_jobs WHERE id = ?", (job.id,)
            ) as cursor:
                row = await cursor.fetchone()
                status = row["status"]
                logger.info(f"Job status: {status}")

                if status == "completed":
                    logger.info("Job completed successfully!")

                    # Verify result
                    async with db.execute(
                        "SELECT * FROM crawl_results WHERE job_id = ?", (job.id,)
                    ) as res_cursor:
                        result = await res_cursor.fetchone()
                        if result:
                            logger.info(f"Result found: {result['final_url']}")
                            logger.info(f"Data length: {len(result['data'])}")
                        else:
                            logger.error("No result found!")
                    break
                elif status == "failed":
                    logger.error("Job failed!")
                    break

    # Stop worker
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    logger.info("Test finished")


if __name__ == "__main__":
    asyncio.run(test_integration())
