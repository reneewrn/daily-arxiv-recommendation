import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from tzlocal import get_localzone

import fetcher

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler(timezone=get_localzone())


def _daily_job():
    try:
        logger.info("Running scheduled arxiv fetch...")
        result = fetcher.fetch_and_store()
        logger.info("Fetch complete: %s", result)
    except Exception:
        logger.exception("Scheduled fetch failed")


def start():
    _scheduler.add_job(
        _daily_job,
        trigger=CronTrigger(hour=8, minute=0),
        id="daily_fetch",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started (tz=%s). Daily fetch at 08:00.", _scheduler.timezone)
    _daily_job()  # always fetch on startup


def stop():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
