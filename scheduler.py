import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import fetcher

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler()


def _daily_job():
    logger.info("Running scheduled arxiv fetch...")
    result = fetcher.fetch_and_store()
    logger.info("Fetch complete: %s", result)


def start(run_now_if_empty: bool = False):
    _scheduler.add_job(
        _daily_job,
        trigger=CronTrigger(hour=8, minute=0),
        id="daily_fetch",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started. Daily fetch at 08:00 local time.")

    if run_now_if_empty:
        import database
        if not database.has_papers_for_today():
            logger.info("No papers for today — fetching now...")
            _daily_job()


def stop():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
