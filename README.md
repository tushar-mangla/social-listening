# RecruitmentOS Lead Collector

Collect recruitment-related posts from supported OpenCLI platforms, keep recent and likely qualified leads, store them locally in SQLite, and optionally sync them to Notion.

## Workflow

```text
OpenCLI -> 24-hour filter -> keyword gate -> Codex Everywhere LLM qualification -> SQLite -> optional Notion sync
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

Notion is optional. Set `NOTION_API_KEY` and `NOTION_DATABASE_ID` in `.env` to sync qualified leads after they are stored in SQLite. Set `CODEX_EVERYWHERE_API_KEY` in `.env` to enable LLM qualification; the verified defaults are base URL `https://codex-easy.ai/v1` and model `gpt-5.6-luna` (override with `CODEX_EVERYWHERE_BASE_URL` / `CODEX_EVERYWHERE_MODEL`). Only setting names and defaults are documented; never commit keys.

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

`--dry-run` still stores classified posts in SQLite but skips the optional Notion sync. The database is `social_listening.db` in the project root, and leads are deduplicated by OpenCLI post ID.

Each keyword candidate receives a durable classifier state: `qualified`, `not_qualified`, `unclassified`, or `provider_error`. Only qualified rows are eligible for Notion sync. Provider and malformed-response failures remain in SQLite with bounded error detail, attempt counts, and scheduled retry metadata; they are never treated as qualified. A qualified row is never downgraded by a later failure (monotonic retention) and stays syncable. After bounded consecutive provider failures, the run uses keyword-only fallback for remaining candidates.

## Schedule

On macOS, install the three-hour launchd job:

```bash
bash listening_loop/install-scheduler.sh
```

The scheduler runs the same `listening_loop.run` command as a one-time execution. It does not run separate digest, Telegram, YouTube, RSS, or local scraper jobs.

## Configuration and tests

Edit `listening_loop/config.py` to change platforms and recruitment-intent search terms. Obvious job-seeker, internal-recruiter, and resume-advice posts are excluded before classifier requests.

`listening_loop/fetch_and_sync_real_leads.py` is a separate legacy RSS-to-Notion utility. It is not part of the OpenCLI -> SQLite -> Codex Everywhere pipeline and remains unchanged.

```bash
venv/bin/python -m pytest -q
```
