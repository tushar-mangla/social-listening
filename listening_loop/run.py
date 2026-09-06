import argparse
import json
import os
import time
from datetime import datetime

from listening_loop import config
from listening_loop import classifier
from listening_loop import qualification
from listening_loop import database
from listening_loop import opencli_adapter
from listening_loop import notion_sync


def is_qualified_candidate(lead: dict) -> bool:
    """Stage 1: fast keyword pre-filter. Rejected posts never invoke the LLM."""
    content = (lead.get("content") or "").lower()
    if not content or any(term in content for term in config.EXCLUDED_KEYWORDS):
        return False
    return any(term in content for term in config.QUALIFYING_KEYWORDS)


def _safe_error(exc: object) -> str:
    """Route exception text through the canonical sanitizer for logs."""
    try:
        from listening_loop.qualification import sanitize_error_message

        return sanitize_error_message(exc)
    except Exception:
        return str(exc)[:300].replace("\n", " ").replace("\r", " ")


def _dedupe_posts(posts: list[dict]) -> list[dict]:
    """Deduplicate posts by post_id, preserving first-seen order."""
    seen: set[str] = set()
    unique: list[dict] = []
    for post in posts:
        pid = str(post.get("post_id") or "")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        unique.append(post)
    return unique


def _retry_post_from_row(row: dict) -> dict:
    return {
        "post_id": str(row.get("post_id")),
        "source": row.get("source"),
        "content": row.get("content") or "",
        "url": row.get("url"),
        "posted_at": row.get("posted_at"),
        "author": row.get("author") if "author" in row else None,
    }


def classify_and_store(leads: list[dict], outcome_callback=None) -> int:
    """Stage 2 + persistence: classify survivors, degrade gracefully, store first.

    - Caps the per-run classification batch.
    - Resets per-run consecutive-failure tracking, then after bounded
      consecutive provider failures uses keyword-only fallback for the
      remaining candidates without calling the provider.
    - Persists every outcome to SQLite before any Notion call.
    - Returns the count of newly inserted post_ids.
    """
    if not leads:
        return 0
    # Deduplicate within this call so the same post is never sent to the
    # paid LLM provider twice in one batch.
    leads = _dedupe_posts(leads)
    if not leads:
        return 0
    cap = config.CLASSIFICATION_BATCH_CAP
    batch_size = config.INTENT_BATCH_SIZE
    candidates = list(leads[:cap])
    if len(leads) > cap:
        print(f"Batch cap: processing {cap} of {len(leads)} candidates this run.")

    qualification.reset_consecutive_failures()
    inserted = 0
    classified_total = 0
    fallback_total = 0

    for start in range(0, len(candidates), batch_size):
        batch = candidates[start:start + batch_size]
        if qualification.should_use_keyword_fallback():
            for post in batch:
                outcome = qualification.build_keyword_fallback(post)
                if outcome_callback:
                    outcome_callback(outcome)
                fallback_total += 1
                classified_total += 1
                if database.add_lead(outcome):
                    inserted += 1
            continue
        outcomes = qualification.classify_posts(batch)
        for outcome in outcomes:
            if outcome_callback:
                outcome_callback(outcome)
            classified_total += 1
            if outcome.get("classifier_status") == "provider_error":
                # classify_posts already bumped the consecutive counter per batch;
                # fallback for subsequent batches is handled at loop top.
                # Sanitized diagnostic so stdout visibly shows provider error status.
                print(
                    "[classification warning] Provider error: "
                    f"{_safe_error(outcome.get('classifier_error_message'))} "
                    f"(post {_safe_error(outcome.get('post_id'))})"
                )
            if outcome.get("classifier_error_category") == "provider_fallback":
                fallback_total += 1
            if database.add_lead(outcome):
                inserted += 1
        if qualification.should_use_keyword_fallback():
            remaining = len(candidates) - (start + batch_size)
            if remaining > 0:
                print(
                    "Provider failures reached the bounded limit; "
                    f"using keyword-only fallback for {remaining} remaining candidate(s)."
                )

    print(
        f"Classification complete: {classified_total} outcome(s), "
        f"{inserted} new post(s), {fallback_total} fallback(s). "
        f"post_ids={[_safe_error(l.get('post_id')) for l in candidates[:5]]}"
    )
    return inserted

def main():
    """Main entrypoint for the social listening loop."""
    parser = argparse.ArgumentParser(description="Social listening tool for recruitment leads.")
    parser.add_argument(
        "--hours",
        type=int,
        default=config.DEFAULT_LOOKBACK_HOURS,
        help="Lookback window in hours."
    )
    parser.add_argument(
        "--platform",
        type=str,
        choices=config.PLATFORMS + ['all'],
        default="all",
        help="Platform to search on."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch leads and add to local DB, but do not sync to Notion."
    )
    args = parser.parse_args()

    print(f"Starting social listening run at {datetime.now().isoformat()}")
    print(f"Configuration: hours={args.hours}, platform={args.platform}, dry_run={args.dry_run}")
    try:
        diagnostics = qualification.get_provider_diagnostics()
        print(
            "Provider: {provider} model={model} base_url={base_url} "
            "timeout={timeout_seconds}s batch={batch_size} cap={batch_cap}".format(**diagnostics)
        )
    except Exception as exc:
        print(f"Provider diagnostics unavailable: {_safe_error(exc)}")

    platforms_to_search = config.PLATFORMS if args.platform == 'all' else [args.platform]

    new_leads_count = 0
    seen_post_ids: set[str] = set()
    query_report: list[dict] = []
    discovery_leads: list[dict] = []
    run_metrics = {
        "raw_discovered": 0,
        "after_dedup": 0,
        "stage1_passed": 0,
        "sent_to_llm": 0,
        "llm_qualified": 0,
        "llm_rejected": 0,
        "added_to_db": 0,
        "database_errors": 0,
        "classification_skipped_database_status": 0,
    }

    def add_error(record: dict, exc: object) -> None:
        record["errors"] += 1
        print(f"Discovery query failed: {_safe_error(exc)}")

    # Keep each query/community invocation observable and independently
    # recoverable. First-seen provenance wins when posts overlap.
    consecutive_discovery_errors = 0
    max_consecutive_discovery_errors = 4
    discovery_halted = False

    for query_family, queries in config.DISCOVERY_QUERIES.items():
        if discovery_halted:
            break
        for exact_query in queries:
            if discovery_halted:
                break
            for platform in platforms_to_search:
                if discovery_halted:
                    break
                communities = config.LEAD_SUBREDDITS if platform == "reddit" else [None]
                for community in communities:
                    if discovery_halted:
                        break
                    record = {
                        "platform": platform,
                        "community": community,
                        "query_family": query_family,
                        "exact_query": exact_query,
                        "posts_retrieved": 0,
                        "duplicates_removed": 0,
                        "stage_one_passed": 0,
                        "luna_qualified": 0,
                        "luna_rejected": 0,
                        "errors": 0,
                    }
                    query_report.append(record)
                    try:
                        fetched = opencli_adapter.fetch_leads(
                            platform, exact_query, args.hours, community, query_family
                        )
                        consecutive_discovery_errors = 0
                        record["posts_retrieved"] = len(fetched)
                        run_metrics["raw_discovered"] += len(fetched)
                        for lead in fetched:
                            pid = str(lead.get("post_id") or "")
                            if not pid or pid in seen_post_ids:
                                if pid:
                                    record["duplicates_removed"] += 1
                                continue
                            seen_post_ids.add(pid)
                            run_metrics["after_dedup"] += 1
                            if is_qualified_candidate(lead):
                                record["stage_one_passed"] += 1
                                run_metrics["stage1_passed"] += 1
                                discovery_leads.append(lead)
                    except Exception as exc:
                        add_error(record, exc)
                        consecutive_discovery_errors += 1
                        if consecutive_discovery_errors >= max_consecutive_discovery_errors:
                            print(
                                f"\n[discovery warning] {consecutive_discovery_errors} consecutive queries failed. "
                                "Platform is likely rate-limiting (HTTP 429) or session unavailable. "
                                "Halting discovery early to avoid worsening rate limits.\n"
                            )
                            discovery_halted = True
                            break
                    delay = getattr(config, "DISCOVERY_QUERY_DELAY_SECONDS", 1.5)
                    if delay > 0 and "PYTEST_CURRENT_TEST" not in os.environ:
                        time.sleep(delay)

    try:
        stored = database.get_existing_status_map([str(l.get("post_id")) for l in discovery_leads])
    except Exception:
        # Status verification protects terminal rows from being reclassified.
        # Do not expose database exception details in run logs.
        print("Database status lookup unavailable; skipping unverified discovered posts.")
        run_metrics["database_errors"] += 1
        run_metrics["classification_skipped_database_status"] += len(discovery_leads)
        fresh_leads = []
    else:
        fresh_leads = [l for l in discovery_leads if str(l.get("post_id")) not in stored]
    if len(fresh_leads) != len(discovery_leads):
        print(f"Skipping {len(discovery_leads) - len(fresh_leads)} already-stored post(s) with prior status.")

    retry_posts: list[dict] = []
    try:
        remaining_cap = max(0, config.CLASSIFICATION_BATCH_CAP - len(fresh_leads))
        if remaining_cap > 0:
            # A discovered post can be an existing retryable row. Its presence
            # in discovery must not suppress the due retry row.
            retry_post_ids: set[str] = set()
            for row in database.get_due_for_retry(limit=remaining_cap):
                pid = str(row.get("post_id"))
                if not pid or pid in retry_post_ids:
                    continue
                retry_post_ids.add(pid)
                retry_posts.append(_retry_post_from_row(row))
    except Exception as exc:
        print(f"Retry selection unavailable, continuing with fresh candidates: {_safe_error(exc)}")

    leads = _dedupe_posts((fresh_leads + retry_posts)[:config.CLASSIFICATION_BATCH_CAP])

    def record_outcome(outcome: dict) -> None:
        status = outcome.get("classifier_status")
        if status == "qualified":
            run_metrics["llm_qualified"] += 1
        elif status == "not_qualified":
            run_metrics["llm_rejected"] += 1
            
        provenance = (outcome.get("platform"), outcome.get("community"),
                      outcome.get("query_family"), outcome.get("exact_query"))
        for record in query_report:
            if (record["platform"], record["community"], record["query_family"], record["exact_query"]) == provenance:
                if status == "qualified":
                    record["luna_qualified"] += 1
                elif status == "not_qualified":
                    record["luna_rejected"] += 1
                return

    if leads:
        run_metrics["sent_to_llm"] += len(leads)
        print(f"Found {len(leads)} keyword candidates. Classifying and storing outcomes...")
        try:
            new_leads_count += classify_and_store(leads, outcome_callback=record_outcome)
            run_metrics["added_to_db"] += new_leads_count
        except Exception as exc:
            print(f"Error classifying candidates: {_safe_error(exc)}. Continuing to reporting.")

    print("Query performance report: " + json.dumps(query_report, default=str, sort_keys=True))
    print("Run metrics: " + json.dumps(run_metrics, sort_keys=True))

    print(f"\nAdded a total of {new_leads_count} new leads to the database.")

    if args.dry_run:
        print("\nDry run enabled. Skipping Notion sync.")
        return

    if new_leads_count == 0:
        print("\nNo new leads to sync to Notion.")
        # Still check for previously unsynced leads

    try:
        unsynced_leads = database.get_unsynced_leads()
    except Exception as exc:
        print(f"\nCould not load unsynced leads: {_safe_error(exc)}")
        return
    if not unsynced_leads:
        print("\nNo unsynced leads to sync to Notion.")
        return

    print(f"\nFound {len(unsynced_leads)} unsynced leads. Starting sync to Notion...")
    try:
        synced_ids = notion_sync.sync_leads_to_notion(unsynced_leads)
    except Exception as exc:
        print(f"\nNotion sync failed: {_safe_error(exc)}. Qualified rows remain unsynced for a later run.")
        return

    if synced_ids:
        try:
            database.mark_as_synced(synced_ids)
        except Exception as exc:
            print(f"\nCould not mark synced rows: {_safe_error(exc)}")
            return
        print(f"\nSuccessfully synced {len(synced_ids)} leads to Notion and updated local database.")
    else:
        print("\nNo leads were synced to Notion in this run.")

    print(f"\nSocial listening run finished at {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
