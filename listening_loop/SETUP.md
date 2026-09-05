# Setup

This package has one canonical collection path: OpenCLI to keyword gate to Codex Everywhere LLM qualification to SQLite, with optional Notion sync.

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

All keyword candidates are stored in `social_listening.db` with classifier status and bounded failure details. Only `qualified` rows are eligible for Notion. The collector rejects obvious job-seeker, internal-recruiter, and resume-advice posts before calling the provider and deduplicates by post ID.

## Optional Notion sync

Set these variables in the project `.env`:

```text
NOTION_API_KEY=...
NOTION_DATABASE_ID=...
```

Without those values, collection still works and leads remain in SQLite. Use `--dry-run` to explicitly skip Notion sync for a run.

## Codex Everywhere qualifier

Set `CODEX_EVERYWHERE_API_KEY` in the project `.env`. Verified non-secret defaults are base URL `https://codex-easy.ai/v1` (chat URL `{base}/chat/completions`) and model `gpt-5.6-luna` (override with `CODEX_EVERYWHERE_BASE_URL` / `CODEX_EVERYWHERE_MODEL`). Provider timeouts, connection failures, HTTP failures, and malformed responses are retained locally as `provider_error` or `unclassified` with bounded diagnostics, attempt counts, and retry scheduling; no failure row is sent to Notion. Qualified rows are never downgraded and remain syncable.

`fetch_and_sync_real_leads.py` is an unchanged, separate RSS helper. Do not treat it as part of the canonical SQLite classifier pipeline.

## Scheduler

```bash
bash listening_loop/install-scheduler.sh
```

On macOS this installs one launchd job that runs every three hours. On Linux it prints one cron entry. The scheduler invokes the same OpenCLI pipeline as the one-time command.

## Tests

```bash
venv/bin/python -m pytest -q
```
