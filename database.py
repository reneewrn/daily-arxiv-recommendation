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


DEFAULT_CONFERENCES = [
    "NeurIPS", "ICML", "ICLR", "CVPR", "ICCV", "ECCV",
    "ACL", "EMNLP", "NAACL", "COLING", "COLM",
    "AAAI", "IJCAI", "AISTATS", "UAI", "COLT",
    "SIGIR", "KDD", "WWW", "CHI", "INTERSPEECH",
]


def init_db() -> None:
    with get_conn() as conn:
        # Create base tables (original schema)
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
        # Migrate: add new columns if missing
        for col, default in [
            ("authors", "'[]'"),
            ("comments", "''"),
            ("affiliations", "'{}'"),
            ("is_replacement", "0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE papers ADD COLUMN {col} TEXT NOT NULL DEFAULT {default}")
            except sqlite3.OperationalError:
                pass
        for col, default in [
            ("conferences", "'[]'"),
            ("author_whitelist", "'[]'"),
            ("author_blacklist", "'[]'"),
        ]:
            try:
                conn.execute(f"ALTER TABLE settings ADD COLUMN {col} TEXT NOT NULL DEFAULT {default}")
            except sqlite3.OperationalError:
                pass
        # Seed default conferences if empty
        row = conn.execute("SELECT conferences FROM settings WHERE id=1").fetchone()
        if row and json.loads(row["conferences"]) == []:
            conn.execute(
                "UPDATE settings SET conferences=? WHERE id=1",
                (json.dumps(DEFAULT_CONFERENCES),),
            )


# ---------- Settings ----------

def get_settings() -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT channels, keywords, conferences, author_whitelist, author_blacklist "
            "FROM settings WHERE id=1"
        ).fetchone()
    return {
        "channels": json.loads(row["channels"]),
        "keywords": json.loads(row["keywords"]),
        "conferences": json.loads(row["conferences"]),
        "author_whitelist": json.loads(row["author_whitelist"]),
        "author_blacklist": json.loads(row["author_blacklist"]),
    }


def save_settings(
    channels: list[str],
    keywords: list[str],
    conferences: list[str] | None = None,
    author_whitelist: list[str] | None = None,
    author_blacklist: list[str] | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE settings SET channels=?, keywords=?, conferences=?, "
            "author_whitelist=?, author_blacklist=? WHERE id=1",
            (
                json.dumps(channels),
                json.dumps(keywords),
                json.dumps(conferences if conferences is not None else []),
                json.dumps(author_whitelist if author_whitelist is not None else []),
                json.dumps(author_blacklist if author_blacklist is not None else []),
            ),
        )


# ---------- Papers ----------

def upsert_papers(papers: list[dict]) -> int:
    """Insert papers, skip duplicates. Returns count inserted."""
    inserted = 0
    with get_conn() as conn:
        for p in papers:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO papers(
                    arxiv_id, date, title, abstract, url, categories,
                    authors, comments, affiliations, is_replacement
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p["arxiv_id"],
                    p["date"],
                    p["title"],
                    p.get("abstract", ""),
                    p["url"],
                    json.dumps(p.get("categories", [])),
                    json.dumps(p.get("authors", [])),
                    p.get("comments", ""),
                    json.dumps(p.get("affiliations", {})),
                    1 if p.get("is_replacement") else 0,
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
        d["authors"] = json.loads(d.get("authors") or "[]")
        d["affiliations"] = json.loads(d.get("affiliations") or "{}")
        d["comments"] = d.get("comments") or ""
        d["is_replacement"] = d.get("is_replacement") in (1, "1", True)
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


