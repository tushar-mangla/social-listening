
import re
import random
import urllib.request
import xml.etree.ElementTree as ET
import html
import time
import logging
import requests # For quoting linkedin url
from .notion_sync import save_lead_to_notion

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SUBREDDITS = [
    "hiring",
    "forhire",
    "startups",
    "recruiting",
    "sales",
    "smallbusiness",
    "RecruitmentAgencies"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
}

# Simple keyword-based analysis
INTENT_KEYWORDS = {
    "Agency_Seeking": ["looking for recruiter", "hiring agency", "recruitment agency", "help with hiring"],
    "Vendor_Replacement_Pain": ["frustrated with", "current recruiter", "switching from", "unhappy with"],
    "Hiring_Surge": ["hiring multiple", "scaling up", "growing team", "hiring surge"],
    "Recruitment_Tech_Pain": ["ats recommendation", "recruitment software", "hiring tool", "crm for recruiting"]
}

URGENCY_KEYWORDS = {
    "High": ["urgent", "immediately", "asap", "need to hire now"],
    "Medium": ["in the next quarter", "planning to hire", "exploring options"],
    "Low": ["future needs", "thinking about", "long-term"]
}

def analyze_post(post):
    """
    Analyzes a Reddit post from RSS feed to determine if it's a real lead and extracts relevant information.
    Returns a lead dictionary or None.
    """
    text_content = post.get('text', '').lower()
    title = post.get('title', '').lower()
    full_text = title + " " + text_content

    score = 0
    intent_type = "General Inquiry"
    urgency = "Low"
    company = "N/A"
    author_role = "N/A"

    for intent, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in full_text:
                score += 10
                intent_type = intent

    if score < 10:
        return None # Not a strong enough signal

    for urgency_level, keywords in URGENCY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in full_text:
                urgency = urgency_level
                if urgency_level == "High":
                    score += 10
                elif urgency_level == "Medium":
                    score += 5

    # Enhanced company and role detection
    company_match = re.search(r"(?i)(?:company|hiring at|working at|at)\s*([a-z0-9\s,]+)", full_text)
    if company_match:
        company = company_match.group(1).strip().title()

    role_match = re.search(r"(?i)(I'm a|I am a|my role is|founder|ceo|cto|hiring manager|recruiter)", full_text)
    if role_match:
        author_role = role_match.group(1).strip().title()

    author = post.get("author", "Unknown").replace("/u/", "")
    
    pain_summary = f"Seems to be experiencing challenges with {intent_type}."
    value_prop = "Our agency specializes in connecting growing companies with top-tier talent, potentially saving you significant time and resources in your hiring process."
    outreach_draft = f"Hi {author},\n\nI saw your post on Reddit regarding your hiring needs. {pain_summary} It sounds like you're looking for support with {intent_type}.\n\n{value_prop}\n\nWould you be open to a brief chat next week to explore how we can help you achieve your hiring goals?\n\nBest,"

    lead = {
        "author": author,
        "company": company,
        "summary": post.get('text', '')[:2000],
        "url": post.get("url"),
        "source": "Reddit",
        "author_role": author_role,
        "score": score,
        "intent_type": intent_type,
        "urgency": urgency,
        "outreach_draft": outreach_draft,
        "linkedin_search_url": f"https://www.linkedin.com/search/results/all/?keywords={requests.utils.quote(author)}",
        "status": "Not started"
    }
    return lead


def fetch_reddit_posts(subreddit):
    """
    Fetches posts from a single subreddit using its RSS feed.
    """
    all_posts = []
    retries = 3
    delay = 2

    for i in range(retries):
        try:
            url = f"https://www.reddit.com/r/{subreddit}/new.rss"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req) as response:
                if response.status == 200:
                    rss_feed = response.read().decode('utf-8')
                    root = ET.fromstring(rss_feed)
                    for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
                        content_html = entry.find('{http://www.w3.org/2005/Atom}content').text
                        # Basic HTML parsing to get text
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(content_html, 'html.parser')
                        post_text = soup.get_text()

                        post = {
                            "id": entry.find('{http://www.w3.org/2005/Atom}id').text,
                            "title": entry.find('{http://www.w3.org/2005/Atom}title').text,
                            "timestamp": entry.find('{http://www.w3.org/2005/Atom}updated').text,
                            "source": "Reddit",
                            "url": entry.find('{http://www.w3.org/2005/Atom}link').get('href'),
                            "author": entry.find('{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name').text,
                            "text": html.unescape(post_text)
                        }
                        all_posts.append(post)
                    return all_posts
        except urllib.error.HTTPError as e:
            if e.code == 429:
                logging.warning(f"Rate limited on r/{subreddit}. Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2
            else:
                logging.error(f"HTTP Error fetching posts from r/{subreddit}: {e}")
                return []
        except Exception as e:
            logging.error(f"Error fetching posts from r/{subreddit}: {e}")
            return []
    return all_posts


def fetch_and_process_leads():
    """
    Fetches posts from specified subreddits, analyzes them, and saves real leads to Notion.
    """
    # Need to install beautifulsoup4
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logging.error("BeautifulSoup4 is not installed. Please install it with 'pip install beautifulsoup4'")
        return []

    real_leads = []
    for subreddit in SUBREDDITS:
        logging.info(f"Fetching posts from r/{subreddit}...")
        posts = fetch_reddit_posts(subreddit)
        
        for post in posts:
            lead = analyze_post(post)
            if lead:
                logging.info(f"Found potential lead: {lead['author']} from r/{subreddit}")
                try:
                    save_lead_to_notion(lead)
                    real_leads.append(lead)
                except Exception as e:
                    logging.error(f"Failed to save lead to Notion: {e}")

        time.sleep(random.uniform(1.0, 1.5)) # Polite delay

    return real_leads

if __name__ == "__main__":
    logging.info("Starting lead fetching and syncing process...")
    leads = fetch_and_process_leads()
    if leads:
        print("\n--- Summary of Real Leads Added to Notion ---")
        for lead in leads:
            print(f"  Lead Name: {lead['author']}")
            print(f"  Post URL: {lead['url']}")
            print(f"  Intent: {lead['intent_type']}")
            print(f"  Urgency: {lead['urgency']}")
            print("-" * 20)
    else:
        print("No new real leads found.")

    logging.info("Process finished.")
