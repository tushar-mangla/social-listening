import os
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv
from notion_client import Client, APIResponseError
from collections import defaultdict

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables from .env file
load_dotenv()

# Initialize Notion client
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

if not NOTION_API_KEY or not NOTION_DATABASE_ID:
    logging.error("Error: NOTION_API_KEY and NOTION_DATABASE_ID must be set in the .env file.")
    exit(1)

notion = Client(auth=NOTION_API_KEY)

def get_all_pages_from_database():
    """
    Retrieves all pages from the Notion database using notion.search as a workaround.
    """
    all_pages = []
    has_more = True
    start_cursor = None
    logging.info(f"Retrieving pages from database ID: {NOTION_DATABASE_ID} using search workaround.")
    while has_more:
        try:
            response = notion.search(
                start_cursor=start_cursor,
                page_size=100,
            )
            results = response.get("results", [])
            
            # Filter results to be in the correct database
            db_pages = [
                page for page in results
                if page.get("parent", {}).get("database_id", "").replace("-", "") == NOTION_DATABASE_ID.replace("-", "")
            ]
            all_pages.extend(db_pages)
            
            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")
        except APIResponseError as e:
            logging.error(f"Error searching Notion: {e}")
            return []
    logging.info(f"Retrieved {len(all_pages)} pages from the database.")
    return all_pages

def archive_page(page_id):
    """Archives a Notion page."""
    try:
        notion.pages.update(page_id=page_id, archived=True)
        logging.info(f"Archived page with ID: {page_id}")
    except APIResponseError as e:
        logging.error(f"Error archiving page {page_id}: {e}")

def deduplicate_by_post_url():
    """
    Finds and archives duplicate pages based on the 'Post URL' property,
    keeping only the most recently edited page for each URL.
    """
    logging.info("Starting deduplication process based on 'Post URL'...")
    pages = get_all_pages_from_database()
    
    if not pages:
        logging.warning("No pages found in the database. Exiting deduplication.")
        return

    pages_by_url = defaultdict(list)
    for page in pages:
        try:
            post_url_property = page.get("properties", {}).get("Post URL", {})
            if post_url_property.get("url"):
                url = post_url_property["url"]
                pages_by_url[url].append(page)
        except (KeyError, IndexError):
            logging.warning(f"Page {page.get('id')} is missing 'Post URL' property or it's malformed.")

    archived_count = 0
    for url, duplicate_pages in pages_by_url.items():
        if len(duplicate_pages) > 1:
            logging.info(f"Found {len(duplicate_pages)} duplicates for URL: {url}")
            
            # Sort pages by last_edited_time, most recent first
            duplicate_pages.sort(
                key=lambda p: datetime.fromisoformat(p["last_edited_time"].replace('Z', '+00:00')), 
                reverse=True
            )
            
            # Keep the first page (the most recent one)
            page_to_keep = duplicate_pages.pop(0)
            logging.info(f"Keeping page: {page_to_keep['id']} (last edited: {page_to_keep['last_edited_time']})")
            
            # Archive the rest
            for page_to_archive in duplicate_pages:
                logging.info(f"Archiving page: {page_to_archive['id']} (last edited: {page_to_archive['last_edited_time']})")
                archive_page(page_to_archive["id"])
                archived_count += 1

    logging.info(f"Deduplication complete. Archived {archived_count} pages.")


if __name__ == "__main__":
    logging.info("--- Starting Notion CRM Cleanup Script ---")
    deduplicate_by_post_url()
    logging.info("--- Notion CRM Cleanup Script Finished ---")
