# Implementation Plan: Multi-Platform Social Listening Engine

**Date:** 2026-09-03

## 1. Goal

This plan outlines the implementation of three major enhancements for the RecruitmentOS Social Listening project:
1.  **CRM Cleanup:** Purge invalid and duplicate test data from the Notion CRM.
2.  **Deduplication & Freshness:** Implement robust deduplication at both the local cache and CRM level, and enforce a strict 24-hour data freshness window for all incoming leads.
3.  **Multi-Platform Ingestion:** Expand lead sourcing from Reddit to include Twitter/X, Facebook, and YouTube/Podcasts, unifying them into a single, orchestrated ingestion pipeline.

The final outcome will be a reliable, automated system that populates the Notion CRM with fresh, unique, and qualified leads from multiple social platforms.

## 2. Assumptions

*   The Notion API key and Database ID are correctly configured in the environment.
*   The Mattermost webhook URL is correctly configured for alerting.
*   The current project structure (`digest.py`, `notion_sync.py`, scrapers) serves as the baseline.
*   Access to external platforms (Twitter, Facebook, YouTube) via APIs, scrapers, or RSS feeds is feasible. We will rely on tools like `twscrape` or public RSS feeds, which may have their own reliability constraints.
*   The OpenAI API key is available and configured for the AI qualification step in `digest.py`.
*   The developer has the necessary permissions to install Python packages and command-line tools (e.g., `twscrape`).

## 3. User Journeys

*   **Data Operator/Admin:**
    1.  The operator runs the main `digest.py` script from the command line.
    2.  The script activates all platform-specific scrapers (Reddit, Twitter, Facebook, YouTube).
    3.  Each scraper gathers posts/mentions created within the last 24 hours.
    4.  The collected posts are passed through a local cache (`seen.json`) to filter out any posts processed in previous runs.
    5.  The unified, fresh, and locally unique posts are sent to the AI for qualification and scoring.
    6.  Qualified leads are passed to the `notion_sync.py` module.
    7.  `notion_sync.py` queries the Notion database by "Post URL" to ensure the lead does not already exist.
    8.  Unique, qualified leads are inserted into the Notion CRM.
    9.  A notification for each new lead is sent to the configured Mattermost channel.
    10. The operator can inspect the Notion database and see only high-quality, unique leads from the last 24 hours.

*   **CRM Cleanup (One-time):**
    1.  The operator runs a new `cleanup_notion.py` script.
    2.  The script identifies and archives all entries with the title "Test Lead".
    3.  The script identifies all entries for "UseImaginary2759", keeps the most recent one, and archives the duplicates.
    4.  The operator verifies in the Notion UI that the specified entries are gone, leaving a clean database.

## 4. Acceptance Criteria

### AC1: Notion CRM Cleanup
*   A standalone script (`cleanup_notion.py`) is created.
*   When run, the script successfully archives the two specified `Test Lead` entries.
*   When run, the script successfully identifies all duplicate `UseImaginary2759` entries based on the title, keeps one, and archives the rest.
*   The script does not affect any other valid entries in the database.
*   The script logs its actions clearly to the console (e.g., "Archived Test Lead page [ID]", "Archived duplicate UseImaginary2759 page [ID]").

### AC2: Deduplication & 24h Freshness Guard
*   **Freshness:** All scrapers and `digest.py` must only process posts with a `published_at` timestamp within the last 24 hours from the time of execution (`datetime.now(timezone.utc)`).
*   **Local Deduplication:** The `digest.py` script must maintain and check against a `seen.json` file. Any post URL present in `seen.json` must be skipped.
*   **CRM-Level Deduplication:** Before inserting a new lead, `notion_sync.py` must query the Notion database's `Post URL` property. If a page with that URL already exists, the new lead must be skipped, and a log message should be printed.
*   No duplicate lead (as defined by "Post URL") ever appears in the Notion database.

### AC3: Multi-Platform Ingestion Engine
*   **Twitter/X Scraper:**
    *   A new scraper module (`twitter_scraper.py`) is created.
    *   It uses a reliable method (`twscrape` or an alternative) to search for tweets matching keywords like `"hiring recruiter"`, `"need an agency"`, etc.
    *   It extracts the tweet text, author, URL, and publication date for each relevant tweet.
*   **Facebook Scraper:**
    *   A new scraper module (`facebook_scraper.py`) is created.
    *   It fetches posts from specified public hiring-related Facebook groups or pages.
    *   It extracts the post text, author, URL, and publication date.
*   **YouTube/Podcast Monitor:**
    *   A new monitor module (`youtube_monitor.py`) is created.
    *   It searches for recent YouTube videos (e.g., podcasts about sales, startups, hiring) based on channel or keywords.
    *   It retrieves video metadata and, if possible, transcripts.
    *   It analyzes the content for mentions of hiring needs or agency searches.
    *   It formats findings as actionable "leads" with the video URL, timestamp, and relevant quote.
*   **Unified Pipeline:**
    *   `digest.py` is refactored to import and run all scraper modules (Reddit, Twitter, Facebook, YouTube).
    *   The main execution block in `digest.py` orchestrates the full flow: scrape -> filter (24h) -> deduplicate (local) -> qualify (AI) -> deduplicate (CRM) -> sync (Notion) -> alert (Mattermost).
    *   A single execution of `python digest.py` runs the entire multi-platform pipeline.

## 5. Affected Components/Files

*   **New Files:**
    *   `scripts/cleanup_notion.py`: The one-time CRM cleanup script.
    *   `scrapers/twitter_scraper.py`: Twitter/X scraping logic.
    *   `scrapers/facebook_scraper.py`: Facebook scraping logic.
    *   `scrapers/youtube_monitor.py`: YouTube/Podcast monitoring logic.
    *   `seen.json`: Local cache for deduplication (if not already present).
*   **Modified Files:**
    *   `notion_sync.py`: Add CRM-level deduplication query before insertion.
    *   `digest.py`: Major refactoring to orchestrate the multi-platform pipeline, enforce 24h freshness, and manage local deduplication.
    *   `scrapers/reddit_scraper.py`: Ensure it adheres to the 24h freshness contract.
    *   `requirements.txt`: Add new dependencies (e.g., `twscrape`, `yt-dlp`, Facebook scraping libraries).

## 6. API & Data Contracts

*   **Notion API:**
    *   **Cleanup:** Use the `search` and `update page` (to set `archived: true`) endpoints.
    *   **Deduplication:** Use the `query database` endpoint with a filter on the `Post URL` property (`type: "url"`, `equals: <post_url>`).
    *   **Insertion:** Use the `create page` endpoint.
*   **Internal Data Contract (Scraper -> Digest):**
    *   All scraper modules must return a list of dictionaries, each with a consistent schema:
      ```json
      {
        "source": "Twitter" | "Facebook" | "Reddit" | "YouTube",
        "text": "The full text of the post/comment/video description.",
        "url": "https://... (permanent URL to the content)",
        "author": "username or author name",
        "published_at": "ISO 8601 datetime string with timezone"
      }
      ```
*   **`seen.json` Format:**
    *   A simple JSON file containing a list of post URLs that have been processed.
      ```json
      ["url1", "url2", "url3"]
      ```

## 7. Implementation Sequence

### Phase 1: Cleanup and Fortification (The Guards)

1.  **Create Cleanup Script:**
    *   Develop `scripts/cleanup_notion.py`.
    *   Implement logic to find pages by title ("Test Lead", "UseImaginary2759").
    *   Use the Notion API client to archive them.
    *   Manually run and verify the script against the dev database.
2.  **Implement CRM Deduplication:**
    *   Modify `notion_sync.py`.
    *   Create a function `check_if_exists(url)`.
    *   This function will query the Notion DB where `Post URL` equals the given URL.
    *   In the main sync function, call `check_if_exists` before calling the `create page` endpoint.
3.  **Implement 24h Freshness Filter:**
    *   In `digest.py`, create a utility function `is_fresh(published_at_string)`.
    *   This function will parse the ISO 8601 string, make it timezone-aware, and compare it with `datetime.now(timezone.utc) - timedelta(hours=24)`.
    *   Apply this filter to the lists of posts received from all scrapers.
4.  **Implement Local Caching:**
    *   In `digest.py`, create functions to `load_seen_urls()` from `seen.json` and `save_seen_urls()`.
    *   Before AI qualification, filter out any posts whose URL is in the set of seen URLs.
    *   After a successful run, add all newly processed URLs to the seen set and save it.

### Phase 2: Platform Expansion (The Scrapers)

5.  **Implement Twitter/X Scraper:**
    *   Create `scrapers/twitter_scraper.py`.
    *   Install and configure `twscrape` or a similar library.
    *   Implement search logic for the specified keywords.
    *   Transform the output to match the internal data contract.
6.  **Implement Facebook Scraper:**
    *   Create `scrapers/facebook_scraper.py`.
    *   Research and choose a library for scraping public Facebook groups (e.g., `facebook-scraper` or direct RSS if available).
    *   Implement logic to pull recent posts from a predefined list of group URLs.
    *   Transform the output to match the internal data contract.
7.  **Implement YouTube Monitor:**
    *   Create `scrapers/youtube_monitor.py`.
    *   Use `yt-dlp` or the YouTube Data API to search for recent videos.
    *   Implement logic to download transcripts where available.
    *   Perform keyword analysis on titles, descriptions, and transcripts to find leads.
    *   Transform findings into the internal data contract format.

### Phase 3: Unification and Orchestration

8.  **Refactor `digest.py`:**
    *   Modify the main script to import all new scraper modules.
    *   Create a main `run_pipeline()` function.
    *   Inside this function, call each scraper, aggregate the results into a single list.
    *   Pass the aggregated list through the freshness and deduplication filters from Phase 1.
    *   Process the final list with the existing AI qualification, Notion sync, and Mattermost alerting logic.
9.  **Final Testing and Documentation:**
    *   Perform a full end-to-end test of the `digest.py` script.
    *   Update the `README.md` with instructions on how to install new dependencies and run the unified system.
    *   Document the one-time cleanup script.

## 8. Test Plan

*   **Unit Tests:**
    *   Test the `is_fresh()` function in `digest.py` with timestamps that are too old, too new, and exactly on the edge.
    *   Test the Notion query logic in `notion_sync.py` to ensure it correctly identifies existing URLs.
    *   Test the data transformation logic in each new scraper to ensure it produces the correct data contract.
*   **Integration Tests:**
    *   Test the flow from a single scraper through `digest.py` to `notion_sync.py`, mocking the Notion API to verify that deduplication checks are called correctly.
    *   Test the `seen.json` functionality by running `digest.py` twice with the same input data and ensuring leads are processed only once.
*   **End-to-End (E2E) Verification:**
    1.  **Cleanup:** Manually add "Test Lead" and duplicate "UseImaginary2759" entries to a test Notion DB. Run `cleanup_notion.py` and verify in the UI that they are archived.
    2.  **Full Pipeline:**
        *   Clear the test Notion DB and `seen.json`.
        *   Run `python digest.py`.
        *   **Verify:**
            *   New, unique leads from all platforms appear in the Notion DB.
            *   Mattermost alerts are received for these leads.
            *   `seen.json` is populated with the URLs of the new leads.
    3.  **Deduplication Test:**
        *   Run `python digest.py` a second time immediately.
        *   **Verify:**
            *   No new leads are added to Notion.
            *   Console logs show that leads are being skipped due to local and CRM-level deduplication checks.

## 9. Risks & Mitigation

*   **Risk:** Social media platforms block scrapers or change their APIs/frontends.
    *   **Mitigation:** Use libraries with active maintenance (`twscrape`). Implement robust error handling and logging to detect failures quickly. Have fallback search queries ready. For Facebook, focus on public groups that are less likely to be restricted.
*   **Risk:** Notion API rate limits are exceeded.
    *   **Mitigation:** Introduce small delays (`time.sleep`) between Notion API calls, especially in the cleanup script and the sync loop. Ensure the deduplication check is efficient.
*   **Risk:** YouTube transcript quality is low or unavailable, making lead qualification difficult.
    *   **Mitigation:** Focus on analyzing titles and descriptions first. Treat transcript analysis as an enhancement. Log when transcripts are unavailable to monitor the success rate.
*   **Risk:** The project becomes complex to manage.
    *   **Mitigation:** Adhere strictly to the defined data contracts between modules. Keep scrapers isolated and focused on one task: gathering data. Centralize all business logic and orchestration in `digest.py`.

## 10. Rollback Notes

*   All changes will be managed via Git. In case of critical failure, the previous commit can be checked out to restore the last working version.
*   The `cleanup_notion.py` script archives entries, which is a soft delete. If a mistake is made, entries can be manually restored from the "Trash" in the Notion UI.
*   If the new `digest.py` pipeline fails, individual scrapers can still be run manually (if they are designed to be runnable standalone) to isolate issues.

## 11. Definition of Done

*   [ ] The `cleanup_notion.py` script is created, tested, and has successfully cleaned the target Notion database.
*   [ ] All scrapers and `digest.py` enforce the 24-hour freshness rule.
*   [ ] `notion_sync.py` performs a successful deduplication check against the Notion API before every insertion.
*   [ ] `digest.py` successfully uses `seen.json` for local deduplication.
*   [ ] Scrapers for Twitter/X, Facebook, and YouTube are implemented and integrated.
*   [ ] `digest.py` is successfully refactored to run the full multi-platform pipeline in a single command.
*   [ ] All acceptance criteria are met and verified through the test plan.
*   [ ] The `README.md` is updated with new setup and execution instructions.
*   [ ] The feature branch is merged into the main branch.
