import argparse
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


def classify_and_store(leads: list[dict]) -> int:
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
                fallback_total += 1
                classified_total += 1
                if database.add_lead(outcome):
                    inserted += 1
            continue
        outcomes = qualification.classify_posts(batch)
        for outcome in outcomes:
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
    for platform in platforms_to_search:
        print(f"\nFetching leads from {platform}...")
        try:
            leads = opencli_adapter.fetch_leads(platform, config.KEYWORDS, args.hours)
        except Exception as exc:
            print(f"Error fetching from {platform}: {_safe_error(exc)}. Continuing with remaining platforms.")
            continue
        leads = [lead for lead in leads if is_qualified_candidate(lead)]

        # Deduplicate within this platform and across the whole run so the
        # same post is never sent to the paid LLM provider twice.
        deduped_fresh: list[dict] = []
        for lead in leads:
            pid = str(lead.get("post_id") or "")
            if not pid or pid in seen_post_ids or pid in {str(l.get("post_id")) for l in deduped_fresh}:
                continue
            deduped_fresh.append(lead)

        # Skip posts already stored in SQLite: only fresh posts (not yet in
        # SQLite) and due retries may reach classify_and_store. In
        # particular, terminal statuses (qualified / not_qualified) are never
        # re-classified here.
        try:
            stored = database.get_existing_status_map([str(l.get("post_id")) for l in deduped_fresh])
        except Exception:
            stored = {}
        fresh_leads = [l for l in deduped_fresh if str(l.get("post_id")) not in stored]
        skipped_stored = len(deduped_fresh) - len(fresh_leads)
        if skipped_stored:
            print(f"Skipping {skipped_stored} already-stored post(s) with prior status.")

        # Include due error/unclassified retries within the same batch cap.
        retry_posts: list[dict] = []
        try:
            remaining_cap = max(0, config.CLASSIFICATION_BATCH_CAP - len(fresh_leads))
            if remaining_cap > 0:
                due_rows = database.get_due_for_retry(limit=remaining_cap)
                seen_ids = {str(l.get("post_id")) for l in fresh_leads} | seen_post_ids
                for row in due_rows:
                    pid = str(row.get("post_id"))
                    if pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    retry_posts.append(_retry_post_from_row(row))
                if retry_posts:
                    print(f"Including {len(retry_posts)} due retry candidate(s) within batch cap.")
        except Exception as exc:
            print(f"Retry selection unavailable, continuing with fresh candidates: {_safe_error(exc)}")

        leads = _dedupe_posts((fresh_leads + retry_posts)[:config.CLASSIFICATION_BATCH_CAP])
        for lead in leads:
            seen_post_ids.add(str(lead.get("post_id")))

        if not leads:
            print(f"No new leads found on {platform} in the last {args.hours} hours.")
            continue

        print(f"Found {len(leads)} keyword candidates on {platform}. Classifying and storing outcomes...")
        try:
            new_leads_count += classify_and_store(leads)
        except Exception as exc:
            print(f"Error classifying candidates from {platform}: {_safe_error(exc)}. Continuing with remaining platforms.")
            continue

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
