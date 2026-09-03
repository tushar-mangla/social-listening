import argparse
from datetime import datetime

from listening_loop import config
from listening_loop import database
from listening_loop import opencli_adapter
from listening_loop import notion_sync


def is_qualified_candidate(lead: dict) -> bool:
    """Keep recruitment needs while excluding obvious job-seeker posts."""
    content = (lead.get("content") or "").lower()
    if not content or any(term in content for term in config.EXCLUDED_KEYWORDS):
        return False
    return any(term in content for term in config.QUALIFYING_KEYWORDS)

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

    platforms_to_search = config.PLATFORMS if args.platform == 'all' else [args.platform]
    
    new_leads_count = 0
    for platform in platforms_to_search:
        print(f"\nFetching leads from {platform}...")
        leads = opencli_adapter.fetch_leads(platform, config.KEYWORDS, args.hours)
        leads = [lead for lead in leads if is_qualified_candidate(lead)]
        
        if not leads:
            print(f"No new leads found on {platform} in the last {args.hours} hours.")
            continue

        print(f"Found {len(leads)} potential leads on {platform}. Adding new ones to the database...")
        
        for lead in leads:
            if database.add_lead(lead):
                new_leads_count += 1
                print(f"  - Added new lead: {lead['url']}")

    print(f"\nAdded a total of {new_leads_count} new leads to the database.")

    if args.dry_run:
        print("\nDry run enabled. Skipping Notion sync.")
        return

    if new_leads_count == 0:
        print("\nNo new leads to sync to Notion.")
        # Still check for previously unsynced leads
    
    unsynced_leads = database.get_unsynced_leads()
    if not unsynced_leads:
        print("\nNo unsynced leads to sync to Notion.")
        return

    print(f"\nFound {len(unsynced_leads)} unsynced leads. Starting sync to Notion...")
    synced_ids = notion_sync.sync_leads_to_notion(unsynced_leads)

    if synced_ids:
        database.mark_as_synced(synced_ids)
        print(f"\nSuccessfully synced {len(synced_ids)} leads to Notion and updated local database.")
    else:
        print("\nNo leads were synced to Notion in this run.")

    print(f"\nSocial listening run finished at {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
