# Daily ArXiv Recommendation

A self-hosted web tool that fetches daily arXiv papers, filters them by your configured channels and keywords, and presents them in a clean local UI.

## Features

- **Daily auto-fetch** at 08:00 AM local time via a background scheduler
- **Filter by channel** (arXiv category) and **keywords** in title/abstract
- **7-day cache** — browse papers from the past week even if you missed a day
- **Persistent settings** — channels and keywords are saved across restarts
- **Clean UI** — clickable paper titles link directly to arXiv

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

## Getting Started

```bash
# Clone or download this repo, then:
./start.sh
```

Open [http://localhost:9999](http://localhost:9999) in your browser.

### Custom host/port

```bash
HOST=0.0.0.0 PORT=8080 ./start.sh
```

## Usage

### 1. Configure channels and keywords

Go to **Settings** (top-right) and add:

- **Channels** — arXiv category identifiers, e.g. `cs.AI`, `cs.LG`, `stat.ML`.
  Browse the full list at [arxiv.org/category_taxonomy](https://arxiv.org/category_taxonomy).
- **Keywords** — words to filter by (case-insensitive match against title and abstract).
  Type one keyword at a time and press **Enter** or click **Add** (e.g. `diffusion`, then `LLM`, then `transformer`).
  Leave empty to show all papers from the selected channels.

### 2. Fetch papers

- **Fetch Now** button (top-right nav bar) — immediately fetches papers for all configured channels and applies your current keyword filters. Use this after first-time setup or whenever you want to pull the latest papers on demand.
- **Scheduled fetch** — the app automatically fetches new papers every day at **08:00 AM** local time while the server is running. If the server was not running at 08:00, use **Fetch Now** to catch up manually.

> Note: arXiv RSS feeds reflect the day's new submissions. Running **Fetch Now** multiple times on the same day is safe — duplicate papers are skipped.

### 3. Browse

Use the date tabs on the home page to switch between the last 7 days. Click any paper title to open it on arXiv.

### 4. Reading with translation

It is recommended to open the app in **[Doubao Explorer](https://www.doubao.com/browser)**, which has a built-in AI translation feature. You can select any abstract text and translate it instantly without leaving the page, which is handy for skimming a large number of papers quickly.

## Project Structure

```
daily-arxiv-recommendation/
├── main.py          # FastAPI app and routes
├── database.py      # SQLite storage (papers + settings)
├── fetcher.py       # arXiv RSS fetching and keyword filtering
├── scheduler.py     # APScheduler daily job
├── start.sh         # Startup script
├── pyproject.toml   # Dependencies (managed by uv)
└── templates/
    ├── base.html    # Shared layout
    ├── index.html   # Papers list
    └── settings.html
```

## Data

Papers are stored in `papers.db` (SQLite) in the project directory. Entries older than 7 days are automatically deleted on each fetch.
