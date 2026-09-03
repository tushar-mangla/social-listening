import sqlite3
from datetime import datetime
import os
from pathlib import Path

DB_FILE = str(Path(__file__).resolve().parent.parent / "social_listening.db")

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_db():
    """Initializes the database and creates the 'leads' table if it doesn't exist."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT UNIQUE NOT NULL,
                source TEXT NOT NULL,
                content TEXT,
                url TEXT,
                posted_at DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                synced_to_notion_at DATETIME
            )
        """)
        conn.commit()

def lead_exists(post_id: str) -> bool:
    """Checks if a lead with the given post_id already exists."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM leads WHERE post_id = ?", (post_id,))
        return cursor.fetchone() is not None

def add_lead(lead: dict) -> bool:
    """Adds a new lead to the database if it doesn't already exist.

    Args:
        lead: A dictionary containing lead data ('post_id', 'source', 'content', 'url', 'posted_at').

    Returns:
        True if the lead was added, False if it already existed.
    """
    if not lead.get("post_id") or lead_exists(lead["post_id"]):
        return False

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO leads (post_id, source, content, url, posted_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            lead.get("post_id"),
            lead.get("source"),
            lead.get("content"),
            lead.get("url"),
            lead.get("posted_at")
        ))
        conn.commit()
    return True

def get_unsynced_leads() -> list[dict]:
    """Retrieves all leads that have not been synced to Notion."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE synced_to_notion_at IS NULL")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def mark_as_synced(lead_ids: list[int]):
    """Marks a list of leads as synced to Notion by updating their 'synced_to_notion_at' timestamp."""
    if not lead_ids:
        return
    
    now = datetime.utcnow()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        placeholders = ', '.join('?' for _ in lead_ids)
        query = f"UPDATE leads SET synced_to_notion_at = ? WHERE id IN ({placeholders})"
        
        params = [now] + lead_ids
        cursor.execute(query, params)
        conn.commit()

# Initialize the database when this module is imported
initialize_db()
