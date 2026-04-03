import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from tzlocal import get_localzone

import database
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


def reschedule():
    """Update the daily fetch schedule from current settings."""
    settings = database.get_settings()
    hour = settings["fetch_hour"]
    minute = settings["fetch_minute"]
    _scheduler.add_job(
        _daily_job,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="daily_fetch",
        replace_existing=True,
    )
    logger.info("Daily fetch scheduled at %02d:%02d (tz=%s).", hour, minute, _scheduler.timezone)


def start():
    reschedule()
    _scheduler.start()
    _daily_job()  # always fetch on startup


def stop():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
