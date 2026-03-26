import re
from datetime import date

import feedparser

import database

ARXIV_RSS_URL = "https://export.arxiv.org/rss/{channel}"


def _extract_arxiv_id(entry_id: str) -> str:
    # "oai:arXiv.org:2603.23506v1" format (arxiv RSS feeds)
    match = re.search(r"oai:arXiv\.org:([^\s]+)", entry_id, re.IGNORECASE)
    if match:
        return re.sub(r"v\d+$", "", match.group(1))
    # "http://arxiv.org/abs/2301.12345v1" format
    match = re.search(r"arxiv\.org/abs/([^\s/]+)", entry_id)
    if match:
        return re.sub(r"v\d+$", "", match.group(1))
    return entry_id


def _extract_categories(entry) -> list[str]:
    tags = getattr(entry, "tags", [])
    return [t.term for t in tags if hasattr(t, "term")]


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
    today = date.today().isoformat()

    if not channels:
        return {"fetched": 0, "stored": 0, "channels": 0}

    database.delete_papers_for_date(today)

    papers_to_store = []
    fetched_total = 0

    for channel in channels:
        url = ARXIV_RSS_URL.format(channel=channel)
        feed = feedparser.parse(url)
        entries = feed.entries

        for entry in entries:
            fetched_total += 1
            title = entry.get("title", "").strip()
            abstract = entry.get("summary", "").strip()

            if not _matches_keywords(title, abstract, keywords):
                continue

            arxiv_id = _extract_arxiv_id(entry.get("id", ""))
            link = entry.get("link") or f"https://arxiv.org/abs/{arxiv_id}"
            categories = _extract_categories(entry)

            papers_to_store.append({
                "arxiv_id": arxiv_id,
                "date": today,
                "title": title,
                "abstract": abstract,
                "url": link,
                "categories": categories,
            })

    stored = database.upsert_papers(papers_to_store)
    database.delete_old_papers(keep_days=7)

    return {
        "fetched": fetched_total,
        "stored": stored,
        "channels": len(channels),
    }
