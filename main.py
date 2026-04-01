import logging
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
):
    ch = [c.strip() for c in channels.split(",") if c.strip()]
    kw = [k.strip() for k in keywords.split(",") if k.strip()]
    database.save_settings(ch, kw)
    return RedirectResponse("/settings", status_code=303)


@app.post("/fetch")
async def trigger_fetch():
    fetcher.fetch_and_store()
    return RedirectResponse("/", status_code=303)
