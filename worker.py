import os
import sentry_sdk

SENTRY_DSN = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,
    )

import asyncio
import logging
from server.scheduler import create_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("worker")

async def run_worker():
    logger.info("Starting background worker (APScheduler)...")
    scheduler = create_scheduler()
    scheduler.start()
    
    try:
        # Keep the event loop running forever
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down background worker...")
        scheduler.shutdown()

if __name__ == "__main__":
    asyncio.run(run_worker())
