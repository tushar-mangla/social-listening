import argparse
import json
import os
import random
import time
from datetime import datetime

from listening_loop import config
from listening_loop import classifier
from listening_loop import qualification
from listening_loop import database
from listening_loop import opencli_adapter
from listening_loop import notion_sync
from listening_loop.logger import logger
import sys

class LoggerWriter:
    def __init__(self, level):
        self.level = level

    def write(self, message):
        if message != '\n':
            self.level(message)

    def flush(self):
        pass

sys.stdout = LoggerWriter(logger.info)
sys.stderr = LoggerWriter(logger.error)


def is_qualified_candidate(lead: dict) -> bool:
    """Pass all discovered posts without keyword filtering (all posts forwarded to LLM & Notion)."""
    content = (lead.get("content") or "").strip()
    return bool(content)


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
        pid = str(post.get("post_id") or post.get("id") or "")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        unique.append(post)
    return unique


def _sleep_for(seconds: float) -> None:
    """Sleep in production; tests can patch this helper without waiting."""
    if "PYTEST_CURRENT_TEST" not in os.environ:
        time.sleep(seconds)


def _pace_between_attempts() -> None:
    _sleep_for(random.uniform(config.INTER_QUERY_SLEEP_MIN, config.INTER_QUERY_SLEEP_MAX))


def _rate_limit_cooldown(attempt: int, retry_after: int = None) -> float:
    cap = min(config.RATE_LIMIT_BACKOFF_MAX, config.RATE_LIMIT_BACKOFF_MIN * 2 ** (attempt - 1))
    cooldown = random.uniform(min(config.RATE_LIMIT_BACKOFF_MIN, cap), cap)
    if retry_after is not None:
        cooldown = max(float(retry_after), cooldown)
    _sleep_for(cooldown)
    return cooldown


def _retry_post_from_row(row: dict) -> dict:
    return {
        "post_id": str(row.get("post_id")),
        "source": row.get("source"),
        "content": row.get("content") or "",
        "url": row.get("url"),
        "posted_at": row.get("posted_at"),
        "author": row.get("author") if "author" in row else None,
        "author_bio": row.get("author_bio") or row.get("bio"),
    }


def classify_and_store(leads: list[dict], outcome_callback=None) -> int:
    """Stage 2 + persistence: classify survivors, degrade gracefully, store first.

    - Caps the per-run classification batch.
    - Applies lightweight deterministic noise filter for obvious job seekers/resume reviews.
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
    cap = getattr(config, "CLASSIFICATION_BATCH_CAP", 64)
    batch_size = getattr(config, "INTENT_BATCH_SIZE", 25)
    candidates = list(leads[:cap])
    if len(leads) > cap:
        print(f"Batch cap: processing {cap} of {len(leads)} candidates this run.")

    qualification.reset_consecutive_failures()
    inserted = 0
    classified_total = 0
    fallback_total = 0

    # Separate candidates: obvious deterministic noise vs LLM candidates
    to_llm: list[dict] = []
    for candidate in candidates:
        is_noise, reason = qualification.is_obvious_jobseeker_noise(candidate)
        if is_noise:
            outcome = {
                **candidate,
                "post_id": str(candidate.get("post_id") or candidate.get("id")),
                "classifier_status": "not_qualified",
                "icp": "no",
                "score": 0.0,
                "confidence": 0.0,
                "role": "job_seeker",
                "author_role": "job_seeker",
                "problem": "none",
                "intent": "none",
                "intent_type": "none",
                "reason": reason,
                "summary": reason,
                "one_line": reason,
                "rejection_reason": reason,
                "classifier_error_category": None,
                "classifier_error_message": None,
            }
            if outcome_callback:
                outcome_callback(outcome)
            classified_total += 1
            if database.add_lead(outcome):
                inserted += 1
        else:
            to_llm.append(candidate)

    for start in range(0, len(to_llm), batch_size):
        batch = to_llm[start : start + batch_size]
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
            if outcome.get("classifier_status") in ("provider_error", "classification_error"):
                print(
                    "[classification warning] Provider/Classifier error: "
                    f"{_safe_error(outcome.get('classifier_error_message'))} "
                    f"(post {_safe_error(outcome.get('post_id'))})"
                )
            if outcome.get("classifier_error_category") == "provider_fallback":
                fallback_total += 1
            if database.add_lead(outcome):
                inserted += 1

        if qualification.should_use_keyword_fallback():
            remaining = len(to_llm) - (start + batch_size)
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


def run_once(args):
    """Execute a single social listening and qualification run."""
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

    platforms_to_search = config.PLATFORMS if args.platform == "all" else [args.platform]

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
        "llm_needs_enrichment": 0,
        "llm_rejected": 0,
        "added_to_db": 0,
        "database_errors": 0,
        "classification_skipped_database_status": 0,
        "rejection_reasons": {},
    }

    def add_error(record: dict, exc: object) -> None:
        record["errors"] += 1
        print(f"Discovery query failed: {_safe_error(exc)}")

    consecutive_discovery_errors = 0
    max_consecutive_discovery_errors = 4
    halted_platforms: set[str] = set()

    for platform in platforms_to_search:
        if platform in halted_platforms:
            continue

        # ── Facebook: fetch news feed once ──────────────────────────────────────
        if platform == "facebook":
            feed_record = {
                "platform": "facebook",
                "community": None,
                "query_family": "feed",
                "exact_query": "feed",
                "posts_retrieved": 0,
                "duplicates_removed": 0,
                "stage_one_passed": 0,
                "luna_qualified": 0,
                "luna_rejected": 0,
                "errors": 0,
            }
            query_report.append(feed_record)
            fb_limit = getattr(config, "FACEBOOK_FEED_LIMIT", 25)
            try:
                fetched = opencli_adapter.fetch_facebook_feed(
                    lookback_hours=args.hours, limit=fb_limit
                )
                feed_record["posts_retrieved"] = len(fetched)
                run_metrics["raw_discovered"] += len(fetched)
                for lead in fetched:
                    pid = str(lead.get("post_id") or "")
                    if not pid or pid in seen_post_ids:
                        if pid:
                            feed_record["duplicates_removed"] += 1
                        continue
                    seen_post_ids.add(pid)
                    run_metrics["after_dedup"] += 1
                    if is_qualified_candidate(lead):
                        feed_record["stage_one_passed"] += 1
                        run_metrics["stage1_passed"] += 1
                        discovery_leads.append(lead)
            except opencli_adapter.OpenCLIAuthenticationError:
                print(
                    "\n[auth error] Facebook requires authentication. "
                    "Please run 'opencli facebook login'.\n"
                    "Halting facebook only and continuing other platforms."
                )
                halted_platforms.add("facebook")
                feed_record["errors"] += 1
            except (opencli_adapter.OpenCLIFetchError, opencli_adapter.OpenCLIExecutionError) as exc:
                print(f"[facebook feed error] {_safe_error(exc)}")
                feed_record["errors"] += 1
            _pace_between_attempts()
            continue

        queries_dict = config.DISCOVERY_QUERIES
        for query_family, queries in queries_dict.items():
            if platform in halted_platforms:
                break
            for exact_query in queries:
                if platform in halted_platforms:
                    break
                communities = config.REDDIT_COMMUNITIES if platform == "reddit" else [None]
                for community in communities:
                    if platform in halted_platforms:
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
                    attempts = 0
                    while True:
                        attempts += 1
                        try:
                            fetched = opencli_adapter.fetch_leads(
                                platform, exact_query, args.hours, community, query_family
                            )
                            _pace_between_attempts()
                            consecutive_discovery_errors = 0
                            break
                        except opencli_adapter.OpenCLIRateLimitError as exc:
                            _pace_between_attempts()
                            if attempts <= config.MAX_RATE_LIMIT_RETRIES:
                                retry_after = opencli_adapter._parse_retry_after(str(exc))
                                cooldown = _rate_limit_cooldown(attempts, retry_after)
                                logger.warning(
                                    f"Rate limited on {platform}. Waiting {cooldown:.1f}s cooldown before retry..."
                                )
                                print(
                                    f"[rate limit] platform={platform} family={query_family} "
                                    f"community={community or 'global'} retrying after cooldown"
                                )
                                continue
                            add_error(record, exc)
                            halted_platforms.add(platform)
                            print(
                                f"[rate limit] platform={platform} family={query_family} "
                                "retry exhausted; halting this platform"
                            )
                            fetched = None
                            break
                        except opencli_adapter.OpenCLIAuthenticationError as exc:
                            print(
                                f"\n[auth error] Platform {platform} requires authentication. "
                                f"Please run 'opencli {platform} login' or ensure session cookies (e.g. c_user) are present.\n"
                                f"Halting {platform} only and continuing other platforms."
                            )
                            halted_platforms.add(platform)
                            fetched = None
                            break
                        except opencli_adapter.OpenCLIFetchError as exc:
                            _pace_between_attempts()
                            if attempts <= getattr(config, "MAX_FETCH_RETRIES", 1):
                                cooldown = random.uniform(
                                    getattr(config, "FETCH_RETRY_BACKOFF_MIN", 15.0),
                                    getattr(config, "FETCH_RETRY_BACKOFF_MAX", 30.0),
                                )
                                _sleep_for(cooldown)
                                print(
                                    f"[fetch error] platform={platform} family={query_family} "
                                    f"community={community or 'global'} retrying after {cooldown:.1f}s..."
                                )
                                continue
                            add_error(record, exc)
                            consecutive_discovery_errors += 1
                            fetched = None
                            break
                        except Exception as exc:
                            _pace_between_attempts()
                            add_error(record, exc)
                            consecutive_discovery_errors += 1
                            fetched = None
                            break
                    if fetched is None:
                        if consecutive_discovery_errors >= max_consecutive_discovery_errors:
                            print(
                                f"\n[discovery warning] {consecutive_discovery_errors} consecutive queries failed for {platform}. "
                                f"Halting {platform} early to avoid worsening rate limits while continuing other platforms.\n"
                            )
                            halted_platforms.add(platform)
                        continue
                    try:
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

    try:
        stored = database.get_existing_status_map([str(l.get("post_id")) for l in discovery_leads])
    except Exception:
        print("Database status lookup unavailable; skipping unverified discovered posts.")
        run_metrics["database_errors"] += 1
        run_metrics["classification_skipped_database_status"] += len(discovery_leads)
        stored = {}

    # Candidates ready for classification: fresh posts or existing posts with pending status
    fresh_leads = [
        l
        for l in discovery_leads
        if stored.get(str(l.get("post_id"))) in (None, "", "pending", "unclassified")
    ]
    if len(discovery_leads) != len(fresh_leads):
        print(f"Skipping {len(discovery_leads) - len(fresh_leads)} already-stored post(s) with prior terminal status.")

    # Save all newly discovered leads into the database with classifier_status = 'pending'
    # so they form a durable pending queue and are never lost if beyond the batch cap.
    for disc_lead in discovery_leads:
        try:
            pid = str(disc_lead.get("post_id") or "")
            if pid and not database.lead_exists(pid):
                database.add_lead({**disc_lead, "classifier_status": "pending"})
        except Exception as exc:
            print(f"Warning: could not save pending raw lead: {_safe_error(exc)}")

    retry_posts: list[dict] = []
    try:
        remaining_cap = max(0, config.CLASSIFICATION_BATCH_CAP - len(fresh_leads))
        if remaining_cap > 0:
            retry_post_ids: set[str] = set()
            for row in database.get_due_for_retry(limit=remaining_cap):
                pid = str(row.get("post_id"))
                if not pid or pid in retry_post_ids:
                    continue
                retry_post_ids.add(pid)
                retry_posts.append(_retry_post_from_row(row))
    except Exception as exc:
        print(f"Retry selection unavailable, continuing with fresh candidates: {_safe_error(exc)}")

    all_candidates = _dedupe_posts(fresh_leads + retry_posts)
    leads = all_candidates[: config.CLASSIFICATION_BATCH_CAP]

    def record_outcome(outcome: dict) -> None:
        status = outcome.get("classifier_status")
        if status == "qualified":
            run_metrics["llm_qualified"] += 1
        elif status == "needs_enrichment":
            run_metrics["llm_needs_enrichment"] += 1
        elif status == "not_qualified":
            run_metrics["llm_rejected"] += 1
            reason = outcome.get("rejection_reason")
            if reason:
                run_metrics["rejection_reasons"][reason] = run_metrics["rejection_reasons"].get(reason, 0) + 1

        provenance = (
            outcome.get("platform"),
            outcome.get("community"),
            outcome.get("query_family"),
            outcome.get("exact_query"),
        )
        for record in query_report:
            if (
                record["platform"],
                record["community"],
                record["query_family"],
                record["exact_query"],
            ) == provenance:
                if status == "qualified":
                    record["luna_qualified"] += 1
                elif status == "not_qualified":
                    record["luna_rejected"] += 1
                return

    if leads:
        run_metrics["sent_to_llm"] += len(leads)
        print(f"Found {len(leads)} candidates for classification. Classifying and storing outcomes...")
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

    try:
        unsynced_leads = database.get_unsynced_leads()
    except Exception as exc:
        print(f"\nCould not load unsynced leads: {_safe_error(exc)}")
        return
    if not unsynced_leads:
        print("\nNo unsynced qualified leads to sync to Notion.")
        return

    print(f"\nFound {len(unsynced_leads)} unsynced qualified leads. Starting sync to Notion...")
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


def main():
    """Main entrypoint for the social listening loop."""
    parser = argparse.ArgumentParser(description="Social listening tool for recruitment leads.")
    parser.add_argument(
        "--hours",
        type=int,
        default=config.DEFAULT_LOOKBACK_HOURS,
        help="Lookback window in hours.",
    )
    parser.add_argument(
        "--platform",
        type=str,
        choices=config.PLATFORMS + ["all"],
        default="all",
        help="Platform to search on.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch leads and add to local DB, but do not sync to Notion.",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously in the foreground (repeats every --interval seconds).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=10800,
        help="Interval between runs in seconds when --loop is enabled (default: 10800 = 3h).",
    )
    args = parser.parse_args()

    if not getattr(args, "loop", False):
        run_once(args)
    else:
        interval_secs = getattr(args, "interval", 10800)
        print(
            f"Starting social listening loop (repeating every {interval_secs}s / "
            f"{interval_secs/3600:.1f}h). Press Ctrl+C to stop."
        )
        while True:
            try:
                run_once(args)
            except KeyboardInterrupt:
                print("\nStopping social listening loop.")
                break
            except Exception as e:
                print(f"Run cycle encountered an error: {_safe_error(e)}")

            print(f"\nSleeping for {interval_secs} seconds until next cycle...")
            try:
                time.sleep(interval_secs)
            except KeyboardInterrupt:
                print("\nStopping social listening loop.")
                break


if __name__ == "__main__":
    main()
