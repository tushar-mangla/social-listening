# Plan: Scraper Cleanup and Consolidation

**Date:** 2026-09-03

## 1. Goal

The goal of this plan is to perform a minimal, low-churn cleanup of the `social_listening` repository. This involves consolidating scraper scripts to a single canonical version per platform, removing redundant and obsolete files, and ensuring that scraper outputs and temporary artifacts are correctly ignored by Git to prevent repository pollution.

## 2. Assumptions

- The primary, working scrapers are located in `scrapers/reddit_scraper/`, `scrapers/youtube_scraper/`, and `scrapers/linkedin_scraper/`.
- Folders like `scrapers/reddit_scraper_2/`, `scrapers/reddit_scraper_loop/`, and `scrapers/youtube_scraper_2/` are considered redundant or obsolete.
- Files like `reddit_output.html` and the `output/` directory are scraper-generated artifacts that should not be tracked in the repository.
- The core logic is executed via `main.py`, which orchestrates the scrapers.

## 3. User Journeys

This change primarily affects the developer workflow.

- **As a developer**, I want to easily locate the correct scraper for a specific platform without confusion from multiple versions.
- **As a developer**, I want to run scrapers without worrying about generated output files cluttering the Git status.
- **As an operations user**, I expect the cleanup to have no impact on the functionality of the primary scrapers.

## 4. Acceptance Criteria

- All redundant scraper folders and files are removed from the repository.
- The `.gitignore` file is updated to exclude scraper output directories and common artifact file types (`.html`, `.pdf`).
- The canonical scrapers (`reddit_scraper.py`, `youtube_scraper.py`, `linkedin_scraper.py`) remain fully functional and execute without errors after the cleanup.
- A `git status` check after running the scrapers shows no untracked output files.

## 5. Affected Components/Files

### To Be Kept (Canonical):
- `main.py`
- `test_main.py`
- `requirements.txt`
- `.gitignore` (will be modified)
- `scrapers/__init__.py`
- `scrapers/linkedin_scraper/linkedin_scraper.py`
- `scrapers/reddit_scraper/reddit_scraper.py`
- `scrapers/youtube_scraper/youtube_scraper.py`

### To Be Deleted/Removed:
- `output/` (entire directory)
- `reddit_output.html`
- `scrapers/reddit_scraper_2/` (entire directory)
- `scrapers/reddit_scraper_loop/` (entire directory)
- `scrapers/youtube_scraper_2/` (entire directory)

### To Be Modified:
- `.gitignore`

## 6. Frontend/API/Database Contract

Not applicable. This is a code-level cleanup.

## 7. Schema or Migration Approach

Not applicable.

## 8. Implementation Sequence

The following steps should be executed in order.

**Step 1: Remove Redundant Scraper Output and Artifacts**
Execute the following commands from the project root to remove tracked artifacts.

```bash
rm -rf output/
rm -f reddit_output.html
```

**Step 2: Remove Redundant Scraper Directories**
Execute the following commands to remove the duplicate scraper folders.

```bash
rm -rf scrapers/reddit_scraper_2/
rm -rf scrapers/reddit_scraper_loop/
rm -rf scrapers/youtube_scraper_2/
```

**Step 3: Update `.gitignore`**
Append the following rules to the `.gitignore` file to prevent future artifacts from being committed.

```
# Scraper output
output/
*.html
*.pdf
```

## 9. Test Plan

The purpose of the test plan is to verify that the canonical scrapers still function as expected after the cleanup.

1.  **Environment Setup:**
    -   Ensure all dependencies are installed: `pip install -r requirements.txt`
    -   Ensure necessary environment variables (e.g., API keys) are set.

2.  **Execution Verification:**
    -   Run each canonical scraper individually or through the main application entry point (`main.py`).
    -   **Reddit Scraper:** Execute the script. Verify it completes without raising exceptions and that expected output (if any) is generated in the now-ignored `output/` directory.
    -   **YouTube Scraper:** Execute the script. Verify it completes without exceptions.
    -   **LinkedIn Scraper:** Execute the script. Verify it completes without exceptions.

3.  **Git Status Verification:**
    -   After running the scrapers, execute `git status`.
    -   The command should report `nothing to commit, working tree clean`. No generated files (e.g., from the `output/` directory) should appear as untracked.

## 10. Risks

- **Accidental Deletion:** The primary risk is the accidental deletion of a scraper that was thought to be redundant but contained unique, valuable logic.
    -   **Mitigation:** The file analysis was based on clear naming duplication. A local backup of the repository before starting work is recommended.
- **Broken Imports:** Removing folders could potentially break imports if there are cross-dependencies.
    -   **Mitigation:** The scrapers appear to be self-contained modules. The test plan, which involves running each scraper, will immediately identify any such issues.

## 11. Rollback Notes

In case of failure, the cleanup can be reverted easily using Git:

1.  Discard all changes in the working directory:
    ```bash
    git restore .
    git clean -fd
    ```
2.  If the changes have already been committed, revert the commit:
    ```bash
    git revert HEAD --no-edit
    ```

## 12. Definition of Done

- [ ] All commands in the **Implementation Sequence** have been successfully executed.
- [ ] The specified files and folders for deletion no longer exist in the repository.
- [ ] The `.gitignore` file has been updated with the new rules.
- [ ] All tests in the **Test Plan** pass successfully.
- [ ] The final changes are committed to the repository.
