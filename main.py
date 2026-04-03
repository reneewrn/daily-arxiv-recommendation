import logging
import re
from contextlib import asynccontextmanager
from datetime import date as _date

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import database
import fetcher
import scheduler

logging.basicConfig(level=logging.INFO)


def _detect_conference(comments: str, conferences: list[str]) -> str | None:
    """Check if comments mention acceptance at a recognized conference."""
    if not comments or not conferences:
        return None
    for conf in conferences:
        # Match patterns like "Accepted at NeurIPS 2025" or "Published in ICML 2024"
        pattern = re.compile(
            rf"(?:accepted|published|appear(?:ing)?)\s+(?:at|in|to|by)\s+[^.]*?\b{re.escape(conf)}\b\s*(\d{{4}})?",
            re.IGNORECASE,
        )
        m = pattern.search(comments)
        if m:
            year = m.group(1) or ""
            return f"{conf} {year}".strip()
        # Fallback: conference name followed by year (common in comments field)
        pattern2 = re.compile(rf"\b{re.escape(conf)}\s+(\d{{4}})\b", re.IGNORECASE)
        m2 = pattern2.search(comments)
        if m2:
            return f"{conf} {m2.group(1)}"
    return None

templates = Jinja2Templates(directory="templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, date: str | None = None):
    selected_date = date or _date.today().isoformat()
    papers = database.get_papers_for_date(selected_date)
    date_counts = database.get_date_counts(days=7)
    settings = database.get_settings()

    whitelist_names = {n.lower() for n in settings["author_whitelist"]}
    blacklist_names = {n.lower() for n in settings["author_blacklist"]}

    for p in papers:
        p["conference"] = _detect_conference(p.get("comments", ""), settings["conferences"])
        author_names_lower = [a.lower() for a in p.get("authors", [])]
        p["is_whitelisted"] = any(a in whitelist_names for a in author_names_lower)
        p["is_blacklisted"] = any(a in blacklist_names for a in author_names_lower)

    papers.sort(key=lambda p: (0 if p["is_whitelisted"] else 2 if p["is_blacklisted"] else 1))

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "papers": papers,
            "date_counts": date_counts,
            "selected_date": selected_date,
            "settings": settings,
        },
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    settings = database.get_settings()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"settings": settings},
    )


@app.post("/settings")
async def save_settings(
    channels: str = Form(default=""),
    keywords: str = Form(default=""),
    conferences: str = Form(default=""),
    author_whitelist: str = Form(default=""),
    author_blacklist: str = Form(default=""),
    fetch_time: str = Form(default="08:00"),
):
    ch = [c.strip() for c in channels.split(",") if c.strip()]
    kw = [k.strip() for k in keywords.split(",") if k.strip()]
    conf = [c.strip() for c in conferences.split(",") if c.strip()]
    wl = [a.strip() for a in author_whitelist.split(",") if a.strip()]
    bl = [a.strip() for a in author_blacklist.split(",") if a.strip()]
    # Parse HH:MM time string
    try:
        parts = fetch_time.split(":")
        hour, minute = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        hour, minute = 8, 0
    database.save_settings(ch, kw, conf, wl, bl, hour, minute)
    scheduler.reschedule()
    return RedirectResponse("/settings", status_code=303)


@app.post("/fetch")
async def trigger_fetch():
    fetcher.fetch_and_store()
    return RedirectResponse("/", status_code=303)
