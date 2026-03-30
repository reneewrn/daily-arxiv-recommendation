import logging
import re
import time
import urllib.request
from datetime import datetime

from bs4 import BeautifulSoup

import database

logger = logging.getLogger(__name__)

ARXIV_NEW_URL = "https://arxiv.org/list/{channel}/new"


def _fetch_page(channel: str) -> str:
    url = ARXIV_NEW_URL.format(channel=channel)
    req = urllib.request.Request(url, headers={"User-Agent": "daily-arxiv/0.1"})
    resp = urllib.request.urlopen(req, timeout=30)
    return resp.read().decode()


def _parse_date(soup) -> str:
    """Extract announcement date from the page heading, e.g.
    'Showing new listings for Monday, 30 March 2026'"""
    h3 = soup.find("h3", string=re.compile(r"Showing new listings for"))
    if h3:
        match = re.search(r"(\w+, \d+ \w+ \d+)", h3.text)
        if match:
            return datetime.strptime(match.group(1), "%A, %d %B %Y").date().isoformat()
    return datetime.now().date().isoformat()


def _parse_papers(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    paper_date = _parse_date(soup)

    # Page has multiple <dl id="articles">: new submissions, cross-lists, replacements.
    # Each is preceded by an <h3> section header. Skip "Replacements".
    all_dls = soup.find_all("dl", id="articles")

    papers = []
    for dl in all_dls:
        prev_h3 = dl.find_previous_sibling("h3")
        if prev_h3 and "Replacement" in prev_h3.text:
            continue

        current_dt = None
        for element in dl.children:
            if element.name == "dt":
                current_dt = element
            elif element.name == "dd" and current_dt is not None:
                # Extract arxiv ID from dt
                link = current_dt.find("a", href=re.compile(r"/abs/"))
                if not link:
                    current_dt = None
                    continue
                arxiv_id = link["href"].replace("/abs/", "")
                url = f"https://arxiv.org/abs/{arxiv_id}"

                # Title
                title_div = element.find("div", class_="list-title")
                title = title_div.text.replace("Title:", "").strip() if title_div else ""

                # Abstract
                abstract_p = element.find("p", class_="mathjax")
                abstract = abstract_p.get_text(separator=" ").strip() if abstract_p else ""

                # Categories — extract codes like "cs.AI" from "(cs.AI)"
                subjects_div = element.find("div", class_="list-subjects")
                categories = re.findall(r"\(([^)]+)\)", subjects_div.text) if subjects_div else []

                papers.append({
                    "arxiv_id": arxiv_id,
                    "date": paper_date,
                    "title": title,
                    "abstract": abstract,
                    "url": url,
                    "categories": categories,
                })
                current_dt = None

    return papers


def _matches_keywords(title: str, abstract: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    text = (title + " " + abstract).lower()
    return any(kw.lower() in text for kw in keywords)


def fetch_and_store() -> dict:
    """Fetch papers for all configured channels, filter by keywords, store in DB.
    Returns a summary dict with counts."""
    settings = database.get_settings()
    channels: list[str] = settings["channels"]
    keywords: list[str] = settings["keywords"]

    if not channels:
        return {"fetched": 0, "stored": 0, "channels": 0}

    papers_to_store = []
    fetched_total = 0
    paper_date = None

    for i, channel in enumerate(channels):
        if i > 0:
            time.sleep(1)  # polite delay between requests
        try:
            html = _fetch_page(channel)
            parsed = _parse_papers(html)
        except Exception as e:
            logger.error("Failed to fetch %s: %s", channel, e)
            continue

        if parsed and paper_date is None:
            paper_date = parsed[0]["date"]

        for paper in parsed:
            fetched_total += 1
            if _matches_keywords(paper["title"], paper["abstract"], keywords):
                papers_to_store.append(paper)

    if paper_date:
        database.delete_papers_for_date(paper_date)

    stored = database.upsert_papers(papers_to_store)
    database.delete_old_papers(keep_days=7)

    return {
        "fetched": fetched_total,
        "stored": stored,
        "channels": len(channels),
    }
