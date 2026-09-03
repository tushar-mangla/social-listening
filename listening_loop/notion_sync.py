import os
from datetime import datetime
from notion_client import Client, APIResponseError
from dotenv import load_dotenv

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")


def _notion_date(value):
    """Return an ISO timestamp for datetime or SQLite string values."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)

def get_notion_client():
    """Initializes and returns a Notion client, or None if credentials are missing."""
    token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY")
    db_id = os.getenv("NOTION_DATABASE_ID") or NOTION_DATABASE_ID
    if not token or not db_id:
        print("Error: NOTION_TOKEN (or NOTION_API_KEY) and NOTION_DATABASE_ID environment variables must be set.")
        return None
    return Client(auth=token)

def build_notion_properties(lead: dict) -> dict:
    """
    Builds properties payload matching RecruitmentOS Leads CRM schema.
    Database Schema:
      - Lead Name (title)
      - Post URL (url)
      - Source (rich_text)
      - Status (status)
      - Summary (rich_text)
      - Company (rich_text, optional)
      - Author Role (rich_text, optional)
      - Score (number, optional)
      - Intent Type (select, optional)
      - Urgency (select, optional)
      - Cold Outreach Draft (rich_text, optional)
      - LinkedIn Search URL (url, optional)
    """
    lead_name = lead.get("author") or lead.get("lead_name")
    if not lead_name or lead_name == "Unknown":
        content = (lead.get("content") or "").strip()
        lead_name = content[:60] if content else f"Lead from {lead.get('source', 'Social')}"

    properties = {
        "Lead Name": {
            "title": [{"text": {"content": lead_name[:2000]}}]
        },
        "Source": {
            "rich_text": [{"text": {"content": (lead.get("source") or "Social")[:2000]}}]
        },
        "Status": {
            "status": {"name": lead.get("status") or "Not started"}
        }
    }

    url = lead.get("url") or lead.get("post_url")
    if url:
        properties["Post URL"] = {"url": url}

    posted_at_iso = _notion_date(lead.get("posted_at"))
    if posted_at_iso:
        properties["Posted At"] = {"date": {"start": posted_at_iso}}

    summary = lead.get("summary") or lead.get("content")
    if summary:
        properties["Summary"] = {"rich_text": [{"text": {"content": summary[:2000]}}]}

    if lead.get("company") and lead["company"] != "N/A":
        properties["Company"] = {"rich_text": [{"text": {"content": lead["company"][:2000]}}]}

    if lead.get("author_role") and lead["author_role"] != "N/A":
        properties["Author Role"] = {"rich_text": [{"text": {"content": lead["author_role"][:2000]}}]}

    if lead.get("score") is not None:
        properties["Score"] = {"number": lead["score"]}

    if lead.get("intent_type"):
        properties["Intent Type"] = {"select": {"name": lead["intent_type"]}}

    if lead.get("urgency"):
        properties["Urgency"] = {"select": {"name": lead["urgency"]}}

    if lead.get("outreach_draft"):
        properties["Cold Outreach Draft"] = {"rich_text": [{"text": {"content": lead["outreach_draft"][:2000]}}]}

    if lead.get("linkedin_search_url"):
        properties["LinkedIn Search URL"] = {"url": lead["linkedin_search_url"]}

    return properties

def save_lead_to_notion(lead: dict):
    """
    Saves a single lead to Notion CRM database.
    Returns created page ID or None.
    """
    notion = get_notion_client()
    if not notion:
        return None

    db_id = os.getenv("NOTION_DATABASE_ID") or NOTION_DATABASE_ID
    properties = build_notion_properties(lead)
    
    page = notion.pages.create(
        parent={"database_id": db_id},
        properties=properties
    )
    return page.get("id")

def sync_leads_to_notion(leads: list[dict]) -> list[int]:
    """
    Syncs a list of leads to a Notion database.

    Args:
        leads: A list of lead dictionaries to be synced.

    Returns:
        A list of the internal database IDs of the leads that were successfully synced.
    """
    notion = get_notion_client()
    if not notion:
        return []

    synced_lead_ids = []

    for lead in leads:
        lead_id = lead.get("id")
        try:
            save_lead_to_notion(lead)
            if lead_id is not None:
                synced_lead_ids.append(lead_id)
            print(f"Successfully synced lead {lead_id or lead.get('post_id')} to Notion.")
        except APIResponseError as e:
            print(f"Error syncing lead {lead_id}: {e}")
        except Exception as e:
            print(f"An unexpected error occurred while syncing lead {lead_id}: {e}")
            
    return synced_lead_ids
