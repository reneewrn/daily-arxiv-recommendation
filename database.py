import json
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "papers.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS papers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                arxiv_id   TEXT NOT NULL,
                date       TEXT NOT NULL,
                title      TEXT NOT NULL,
                abstract   TEXT,
                url        TEXT NOT NULL,
                categories TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_arxiv_date
                ON papers(arxiv_id, date);

            CREATE TABLE IF NOT EXISTS settings (
                id       INTEGER PRIMARY KEY CHECK (id = 1),
                channels TEXT NOT NULL DEFAULT '[]',
                keywords TEXT NOT NULL DEFAULT '[]'
            );
            INSERT OR IGNORE INTO settings(id, channels, keywords)
                VALUES (1, '[]', '[]');
        """)


# ---------- Settings ----------

def get_settings() -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT channels, keywords FROM settings WHERE id=1").fetchone()
    return {
        "channels": json.loads(row["channels"]),
        "keywords": json.loads(row["keywords"]),
    }


def save_settings(channels: list[str], keywords: list[str]) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE settings SET channels=?, keywords=? WHERE id=1",
            (json.dumps(channels), json.dumps(keywords)),
        )


# ---------- Papers ----------

def upsert_papers(papers: list[dict]) -> int:
    """Insert papers, skip duplicates. Returns count inserted."""
    inserted = 0
    with get_conn() as conn:
        for p in papers:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO papers(arxiv_id, date, title, abstract, url, categories)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    p["arxiv_id"],
                    p["date"],
                    p["title"],
                    p.get("abstract", ""),
                    p["url"],
                    json.dumps(p.get("categories", [])),
                ),
            )
            inserted += cur.rowcount
    return inserted


def get_papers_for_date(date_str: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM papers WHERE date=? ORDER BY id",
            (date_str,),
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["categories"] = json.loads(d["categories"] or "[]")
        result.append(d)
    return result


def get_date_counts(days: int = 7) -> list[dict]:
    """Return list of {date, count} for the last `days` days."""
    today = date.today()
    dates = [(today - timedelta(days=i)).isoformat() for i in range(days)]
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT date, COUNT(*) as count FROM papers WHERE date IN ({','.join('?'*len(dates))}) GROUP BY date",
            dates,
        ).fetchall()
    counts = {row["date"]: row["count"] for row in rows}
    return [{"date": d, "count": counts.get(d, 0)} for d in dates]


def delete_papers_for_date(date_str: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM papers WHERE date = ?", (date_str,))


def delete_old_papers(keep_days: int = 7) -> None:
    cutoff = (date.today() - timedelta(days=keep_days)).isoformat()
    with get_conn() as conn:
        conn.execute("DELETE FROM papers WHERE date < ?", (cutoff,))


