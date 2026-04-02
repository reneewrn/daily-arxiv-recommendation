import logging
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
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
        is_replacement = bool(prev_h3 and "Replacement" in prev_h3.text)

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

                # Authors
                authors_div = element.find("div", class_="list-authors")
                authors = [a.get_text().strip() for a in authors_div.find_all("a")] if authors_div else []

                # Comments (optional field)
                comments_div = element.find("div", class_="list-comments")
                comments = comments_div.get_text(separator=" ").strip() if comments_div else ""
                if comments.lower().startswith("comments:"):
                    comments = comments[len("comments:"):].strip()

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
                    "authors": authors,
                    "comments": comments,
                    "is_replacement": is_replacement,
                })
                current_dt = None

    return papers


ARXIV_API_URL = "http://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


def _fetch_affiliations(arxiv_ids: list[str]) -> dict[str, dict[str, str]]:
    """Batch-fetch author affiliations via the arXiv API.
    Returns {arxiv_id: {author_name: affiliation}}."""
    if not arxiv_ids:
        return {}

    result: dict[str, dict[str, str]] = {}
    batch_size = 100

    for start in range(0, len(arxiv_ids), batch_size):
        if start > 0:
            time.sleep(3)  # arXiv API rate limit
        batch = arxiv_ids[start : start + batch_size]
        id_list = ",".join(batch)
        url = f"{ARXIV_API_URL}?id_list={id_list}&max_results={len(batch)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "daily-arxiv/0.1"})
            resp = urllib.request.urlopen(req, timeout=30)
            xml_data = resp.read().decode()
        except Exception as e:
            logger.error("arXiv API request failed: %s", e)
            continue

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as e:
            logger.error("Failed to parse arXiv API XML: %s", e)
            continue

        for entry in root.findall(f"{ATOM_NS}entry"):
            entry_id = entry.findtext(f"{ATOM_NS}id", "")
            # Extract arxiv_id from URL like http://arxiv.org/abs/2403.12345v1
            aid = entry_id.rsplit("/", 1)[-1]
            aid = re.sub(r"v\d+$", "", aid)  # strip version suffix

            affiliations: dict[str, str] = {}
            for author_el in entry.findall(f"{ATOM_NS}author"):
                name = author_el.findtext(f"{ATOM_NS}name", "").strip()
                aff_el = author_el.find(f"{ARXIV_NS}affiliation")
                if name and aff_el is not None and aff_el.text:
                    affiliations[name] = aff_el.text.strip()

            if affiliations:
                result[aid] = affiliations

    return result


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
