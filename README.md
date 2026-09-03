# RecruitmentOS Lead Collector

Collect recruitment-related posts from supported OpenCLI platforms, keep recent and likely qualified leads, store them locally in SQLite, and optionally sync them to Notion.

## Workflow

```text
OpenCLI -> 24-hour filter -> recruitment qualification -> SQLite deduplication -> optional Notion sync
```

There are no local platform scrapers. OpenCLI is the only collection interface.

## Setup

```bash
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
npm install -g opencli
```

Log in to each OpenCLI platform you want to use:

```bash
opencli reddit login
opencli twitter login
opencli facebook login
```

Notion is optional. Set `NOTION_API_KEY` and `NOTION_DATABASE_ID` in `.env` to sync newly collected leads after they are stored in SQLite.

## Run Once

```bash
venv/bin/python -m listening_loop.run
```

Useful options:

```bash
venv/bin/python -m listening_loop.run --hours 5
venv/bin/python -m listening_loop.run --platform reddit
venv/bin/python -m listening_loop.run --dry-run
```

`--dry-run` still stores new leads in SQLite but skips the optional Notion sync. The database is `social_listening.db` in the project root, and leads are deduplicated by OpenCLI post ID.

## Schedule

On macOS, install the three-hour launchd job:

```bash
bash listening_loop/install-scheduler.sh
```

The scheduler runs the same `listening_loop.run` command as a one-time execution. It does not run separate digest, Telegram, YouTube, RSS, or local scraper jobs.

## Configuration and tests

Edit `listening_loop/config.py` to change platforms and recruitment-intent search terms. Obvious job-seeker posts are excluded before database insertion.

```bash
venv/bin/python -m pytest -q
```
