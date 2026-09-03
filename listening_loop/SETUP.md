# Setup

This package has one collection path: OpenCLI to SQLite, with optional Notion sync.

## Install

From the project root:

```bash
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
npm install -g opencli
cp .env.example .env
```

Authenticate only the platforms you plan to search:

```bash
opencli reddit login
opencli twitter login
opencli facebook login
```

## One-time run

```bash
venv/bin/python -m listening_loop.run
```

The default lookback is 24 hours. Override it with `--hours 5` or another positive number. Restrict collection with `--platform reddit`, `twitter`, `facebook`, or `linkedin`.

New qualified posts are stored in `social_listening.db`. The collector rejects obvious job-seeker posts and deduplicates by post ID.

## Optional Notion sync

Set these variables in the project `.env`:

```text
NOTION_API_KEY=...
NOTION_DATABASE_ID=...
```

Without those values, collection still works and leads remain in SQLite. Use `--dry-run` to explicitly skip Notion sync for a run.

## Scheduler

```bash
bash listening_loop/install-scheduler.sh
```

On macOS this installs one launchd job that runs every three hours. On Linux it prints one cron entry. The scheduler invokes the same OpenCLI pipeline as the one-time command.

## Tests

```bash
venv/bin/python -m pytest -q
```
