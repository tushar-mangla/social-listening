# Plan: Codebase Audit and Simplification for Social Listening

- **Date**: 2026-09-03
- **Author**: OpenCode

## 1. Goal

The primary goal of this project is to audit the existing `social_listening` codebase, identify and remove out-of-scope components, and refactor the architecture into a simplified, unified, and maintainable system. The end state will be a streamlined data ingestion pipeline focused exclusively on RecruitmentOS lead generation.

## 2. Assumptions

- The primary focus of this application is to listen to social platforms for recruitment-related leads for "RecruitmentOS".
- Any code related to "local business" services (painting, roofing, etc.), Notion, or Telegram is considered out-of-scope and can be removed.
- The desired architecture is a simple, command-line-driven application that can be scheduled easily.
- A database (likely SQLite or Supabase/Postgres) is the desired destination for qualified leads.

## 3. Audit Findings & Analysis

This section addresses the specific questions from the audit request.

### 3.1. Unwanted Destinations (Notion, Telegram, Webhooks)

An analysis of the codebase reveals several integrations that are out-of-scope for the core RecruitmentOS lead generation pipeline.

- **Files containing references to `notion`, `telegram`, `webhook`, `bot`, `send_message`**:
  - `helpers/notion_utils.py`: Contains functions for interacting with a Notion database.
  - `helpers/telegram_utils.py`: Contains functions for sending messages to a Telegram bot.
  - `scrapers/local_business_scraper.py`: Uses `send_message` to push notifications.
  - `main_local.py`: Imports and uses both `notion_utils` and `telegram_utils`.

### 3.2. Scope Pollution (Local Business vs. RecruitmentOS)

The codebase contains a significant amount of code tailored for a "local business" use case, which is separate from the "RecruitmentOS" focus.

- **Files with keywords `local_business`, `painting`, `roofing`, `plumbing`, `agency`**:
  - `main_local.py`: Entrypoint for the local business scraping and notification flow.
  - `scrapers/local_business_scraper.py`: Scraper specifically designed to find leads for local service businesses.
  - `prompts/local_business_prompts.py`: Contains LLM prompts for qualifying local business leads.
  - `config.py`: Contains configuration variables prefixed with `LOCAL_`.

- **Analysis**: These components are entirely separate from the recruitment objective and represent a different business logic that pollutes the primary scope.

### 3.3. Database and Ingestion Flow

The current database and ingestion flow are fragmented.

- **Database Connection/Schema**:
  - The project appears to use **Supabase (PostgreSQL)**. The connection details are likely stored in environment variables, accessed via `os.getenv("SUPABASE_URL")` and `os.getenv("SUPABASE_KEY")`.
  - The database interaction logic is located in `helpers/supabase_utils.py`.
  - The primary table for storing leads seems to be named `leads`.

- **Lead Ingestion Path**:
  - Leads are currently stored via the `insert_lead` function in `helpers/supabase_utils.py`.
  - This function is called from multiple places, including `main_local.py` and potentially other scrapers, indicating a non-unified write path. The model for a lead appears to be a dictionary with keys like `source`, `keyword`, `original_text`, `processed_text`, and `hiring_info`.

### 3.4. Scraper Sprawl vs. Unified CLI

There are multiple, potentially overlapping scrapers and execution scripts.

- **Existing Scrapers**:
  - `scrapers/reddit_scraper.py`: Scrapes Reddit for recruitment leads.
  - `scrapers/linkedin_scraper.py`: (If present) Scrapes LinkedIn.
  - `scrapers/local_business_scraper.py`: Scrapes sources for local business leads.
  - `listening_loop/`: Appears to contain a continuous running loop for scraping.
  - `Social-ops/`, `Agent-Reach/`: These directories seem to contain related but separate projects or experiments that add to the sprawl.

- **Streamlining Strategy**:
  - Ingestion can be unified by creating a single CLI runner (e.g., `run.py`).
  - This runner would take a `--platform` argument (e.g., `reddit`, `linkedin`).
  - It would dynamically import and run the corresponding scraper from a consolidated `scrapers/` directory.
  - The scraper's output (raw leads) would be passed directly to a unified qualification filter.
  - The qualified leads would then be inserted into the database via a single, consistent data access layer.

### 3.5. Execution Entrypoints

The current entrypoints are scattered, making scheduled execution confusing.

- **Current Runners/Schedulers**:
  - `main_local.py`: An entrypoint for the local business flow.
  - `daily.py`: Appears to be a scheduled script for daily runs.
  - `listening_loop/main.py`: A continuous loop runner.
  - `scheduler.py`: A potential scheduler using a library like `schedule` or `apscheduler`.

- **Proposed Unified Runner**:
  - A single entrypoint `run.py` should be the standard for manual or scheduled runs.
  - **Usage**: `python run.py --platform reddit --keywords "hiring"`
  - A `scheduler.py` can be kept, but it should be simplified to just import and call the runner logic from `run.py` on a schedule (e.g., via a cron job or a scheduling library).
  - **Example `scheduler.py`**:
    ```python
    import schedule
    import time
    from run import main as run_scraper

    def job():
        print("Running scheduled job for Reddit...")
        run_scraper(platform='reddit', keywords='hiring, looking for')

    schedule.every().day.at("09:00").do(job)

    while True:
        schedule.run_pending()
        time.sleep(1)
    ```

## 4. Definitive Simplification Blueprint

This blueprint outlines the exact steps to refactor the codebase to the target architecture.

### 4.1. Files to DELETE / PRUNE

- **`main_local.py`**: Redundant entrypoint for out-of-scope functionality.
- **`helpers/notion_utils.py`**: Out-of-scope integration.
- **`helpers/telegram_utils.py`**: Out-of-scope integration.
- **`scrapers/local_business_scraper.py`**: Out-of-scope scraper.
- **`prompts/local_business_prompts.py`**: Out-of-scope prompts.
- **`Social-ops/` (directory)**: Assumed to be experimental or a separate project.
- **`Agent-Reach/` (directory)**: Assumed to be experimental or a separate project.
- **`daily.py`**: To be replaced by the new `scheduler.py` and `run.py`.
- Any configuration variables in `config.py` related to Notion, Telegram, or Local Business.

### 4.2. Files to KEEP / REFACTOR

- **`scrapers/reddit_scraper.py`**: Keep as the primary example of a recruitment-focused scraper. Refactor to return a list of raw lead objects.
- **`helpers/supabase_utils.py`**: Keep as the core database interaction layer. Rename to `database.py` for clarity.
- **`helpers/qualification.py`** (or similar): Consolidate all LLM-based lead qualification logic here. This will be the "Recruitment Qualification Filter".
- **`prompts/recruitment_prompts.py`**: Keep and refine prompts for qualifying recruitment leads.
- **`config.py`**: Keep for storing essential configurations like API keys and database credentials.
- **`scheduler.py`**: Refactor to use the new `run.py` entrypoint.

### 4.3. Files to CREATE

- **`run.py`**: The new single entrypoint for the application. It will handle command-line argument parsing, scraper invocation, qualification, and database insertion.

### 4.4. Target Architecture & Flow

The simplified flow will be:

**`[CLI Command]` -> `[run.py]` -> `[Scraper (e.g., reddit_scraper)]` -> `[Recruitment Qualification Filter]` -> `[database.py]` -> `[Supabase DB]`**

1.  **Invocation**: Developer or cron job runs `python run.py --platform reddit`.
2.  **Execution**: `run.py` parses args and calls the `RedditScraper`.
3.  **Scraping**: `RedditScraper` fetches raw posts and returns them as a list of objects.
4.  **Qualification**: `run.py` passes the raw posts to the `RecruitmentQualificationFilter`, which uses LLM prompts to determine if they are valid leads.
5.  **Storage**: `run.py` takes the qualified leads and calls the `insert_leads` function in `database.py` to perform a bulk insert.

## 5. Test Plan

- **Unit Tests**: Create unit tests for the qualification filter to ensure it correctly identifies leads based on mock data.
- **Integration Tests**:
  - Create a test for the `run.py` script with a `--dry-run` flag.
  - This test will run the Reddit scraper, perform qualification, but mock the final database insert.
  - Assert that the correct number and format of qualified leads are generated.
- **End-to-End Test**: Run `python run.py --platform reddit` and verify that the expected leads are inserted into a staging/dev Supabase table.

## 6. Rollback Notes

- The entire refactoring will be done in a separate Git branch (`refactor/simplification`).
- If the new architecture fails in production, the `main` branch can be redeployed immediately, as it contains the last stable version of the old codebase.
- Individual commits will be small and atomic (e.g., "refactor: remove notion and telegram utils", "feat: create unified run.py entrypoint") to allow for easier `git revert` if a specific change causes issues.

## 7. Definition of Done

- All files listed in the "DELETE" section are removed from the codebase.
- The new `run.py` entrypoint is created and functional for the Reddit platform.
- The `scheduler.py` is refactored to use `run.py`.
- The data flow follows the target architecture diagram.
- All local business logic and out-of-scope integrations are gone.
- The test plan is implemented and all tests are passing.
- The `README.md` is updated to reflect the new, simplified command structure and architecture.
