import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

DB_FILE = str(Path(__file__).resolve().parent.parent / "social_listening.db")

# Qualification evidence fields that must never be overwritten once
# established on a qualified row; later classifications may only fill
# previously missing (None) values.
QUALIFICATION_EVIDENCE_FIELDS = (
    "icp",
    "author_role",
    "role",
    "intent_type",
    "intent",
    "problem",
    "reason",
    "score",
    "lead_priority",
    "urgency",
    "confidence",
    "summary",
    "one_line",
    "keyword_score",
    "icp_score",
    "intent_score",
    "rejection_reason",
    "outreach_draft",
    "author_bio",
)


def sanitize_db_error(value: object) -> Optional[str]:
    """Canonical redaction + bound for persisted error messages."""
    if value is None:
        return None
    try:
        from listening_loop.qualification import sanitize_error_message as _sanitize

        text = _sanitize(value)
    except Exception:
        text = str(value).replace("\n", " ").replace("\r", " ")[:300]
    text = text[:300]
    return text or None


def _utcnow() -> datetime:
    return datetime.utcnow()


def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db():
    """Idempotent migration: create base table, then add enrichment/state columns."""
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
        columns = {row[1] for row in cursor.execute("PRAGMA table_info(leads)")}
        additions = {
            "classifier_status": "TEXT NOT NULL DEFAULT 'unclassified'",
            "icp": "TEXT",
            "author_role": "TEXT",
            "role": "TEXT",
            "intent_type": "TEXT",
            "intent": "TEXT",
            "problem": "TEXT",
            "reason": "TEXT",
            "urgency": "TEXT",
            "score": "REAL",
            "lead_priority": "INTEGER",
            "confidence": "REAL",
            "icp_score": "REAL",
            "intent_score": "REAL",
            "summary": "TEXT",
            "one_line": "TEXT",
            "keyword_score": "REAL",
            "rejection_reason": "TEXT",
            "outreach_draft": "TEXT",
            "author_bio": "TEXT",
            "classification_attempts": "INTEGER NOT NULL DEFAULT 0",
            "last_classification_attempt_at": "DATETIME",
            "classified_at": "DATETIME",
            "classifier_error_category": "TEXT",
            "classifier_error_message": "TEXT",
            "next_classification_retry_at": "DATETIME",
            "classifier_provider": "TEXT",
        }
        for name, definition in additions.items():
            if name not in columns:
                cursor.execute("ALTER TABLE leads ADD COLUMN " + name + " " + definition)
        conn.commit()


def lead_exists(post_id: str) -> bool:
    """Checks if a lead with the given post_id already exists."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM leads WHERE post_id = ?", (post_id,))
        return cursor.fetchone() is not None


def _retry_delay_seconds(attempts: int) -> int:
    try:
        from listening_loop import config as _config

        base = _config.RETRY_BASE_DELAY_SECONDS
        cap = _config.RETRY_MAX_DELAY_SECONDS
    except Exception:
        base, cap = 60, 3600
    delay = base * (2 ** max(0, attempts - 1))
    return max(base, min(cap, delay))


def _compute_next_retry(status: Optional[str], attempts: int, now: datetime) -> Optional[datetime]:
    if status in ("provider_error", "unclassified", "classification_error", "pending"):
        try:
            from listening_loop import config as _config

            max_attempts = _config.MAX_CLASSIFICATION_ATTEMPTS
        except Exception:
            max_attempts = 5
        if attempts >= max_attempts:
            return None
        return now + timedelta(seconds=_retry_delay_seconds(attempts))
    return None


def add_lead(lead: dict) -> bool:
    """Insert or monotonically upsert a lead.

    Monotonic retention invariant: a row that is already ``qualified``
    (synced or unsynced) can never be downgraded to a negative/error
    status by a later attempt. Later failures only increment attempt and
    error metadata. Valid enrichment may fill missing values without
    erasing qualified evidence or ``synced_to_notion_at``.

    Returns True when the post_id was newly inserted, False on update.
    """
    if not lead.get("post_id"):
        return False

    post_id = str(lead["post_id"])
    now = _utcnow()

    incoming_status = lead.get("classifier_status") or "unclassified"
    # Normalize summary/one_line/reason
    summary_val = lead.get("summary") or lead.get("one_line") or lead.get("reason")
    one_line_val = lead.get("one_line") or lead.get("summary") or lead.get("reason")
    reason_val = lead.get("reason") or lead.get("one_line") or lead.get("summary")
    role_val = lead.get("role") or lead.get("author_role")
    intent_val = lead.get("intent") or lead.get("intent_type")
    score_val = lead.get("score") if lead.get("score") is not None else lead.get("confidence")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        existing_row = cursor.execute(
            "SELECT * FROM leads WHERE post_id = ?", (post_id,)
        ).fetchone()
        existing = dict(existing_row) if existing_row else None
        inserted = existing is None

        existing_attempts = 0
        if existing and existing.get("classification_attempts") is not None:
            try:
                existing_attempts = int(existing["classification_attempts"])
            except (TypeError, ValueError):
                existing_attempts = 0
        attempts = existing_attempts + 1
        next_retry = _compute_next_retry(incoming_status, attempts, now)

        classified_at = now if incoming_status not in ("pending", "unclassified") else None
        if existing and existing.get("classified_at") and incoming_status == "qualified":
            # Preserve original qualification timestamp.
            classified_at = existing["classified_at"]

        if existing and existing.get("classifier_status") == "qualified" and incoming_status != "qualified":
            # Monotonic guard: preserve qualified evidence; update metadata only.
            cursor.execute(
                """UPDATE leads SET
                    source=COALESCE(?, source),
                    content=COALESCE(?, content),
                    url=COALESCE(?, url),
                    posted_at=COALESCE(?, posted_at),
                    classification_attempts=?,
                    last_classification_attempt_at=?,
                    classifier_error_category=?,
                    classifier_error_message=?,
                    next_classification_retry_at=?,
                    classifier_provider=COALESCE(?, classifier_provider),
                    author_bio=COALESCE(?, author_bio)
                   WHERE post_id=?""",
                (
                    lead.get("source"),
                    lead.get("content"),
                    lead.get("url"),
                    lead.get("posted_at"),
                    attempts,
                    now,
                    lead.get("classifier_error_category"),
                    sanitize_db_error(lead.get("classifier_error_message")),
                    next_retry,
                    lead.get("classifier_provider"),
                    lead.get("author_bio") or lead.get("bio"),
                    post_id,
                ),
            )
            conn.commit()
            return False

        # Qualified + qualified re-affirmation: preserve every established non-null evidence field
        if existing and existing.get("classifier_status") == "qualified" and incoming_status == "qualified":
            def _keep(field: str):
                current = existing.get(field)
                if current is not None:
                    return current
                if field == "summary":
                    return summary_val
                if field == "one_line":
                    return one_line_val
                if field == "reason":
                    return reason_val
                if field in ("role", "author_role"):
                    return role_val
                if field in ("intent", "intent_type"):
                    return intent_val
                if field in ("score", "confidence", "icp_score"):
                    return score_val
                return lead.get(field)

            cursor.execute(
                """UPDATE leads SET
                    source=?, content=?, url=?, posted_at=?,
                    classifier_status=?, icp=?, author_role=?, role=?, intent_type=?, intent=?, problem=?, reason=?, urgency=?,
                    confidence=?, icp_score=?, intent_score=?, score=?, lead_priority=?, summary=?, one_line=?, keyword_score=?, rejection_reason=?, outreach_draft=?, author_bio=?,
                    classification_attempts=?, last_classification_attempt_at=?,
                    classified_at=?, classifier_error_category=?, classifier_error_message=?,
                    next_classification_retry_at=?, classifier_provider=?
                    WHERE post_id=?""",
                (
                    lead.get("source") or existing.get("source"),
                    lead.get("content") if lead.get("content") is not None else existing.get("content"),
                    lead.get("url") if lead.get("url") is not None else existing.get("url"),
                    lead.get("posted_at") if lead.get("posted_at") is not None else existing.get("posted_at"),
                    "qualified",
                    _keep("icp"),
                    _keep("author_role"),
                    _keep("role"),
                    _keep("intent_type"),
                    _keep("intent"),
                    _keep("problem"),
                    _keep("reason"),
                    _keep("urgency"),
                    _keep("confidence"),
                    _keep("icp_score"),
                    _keep("intent_score"),
                    _keep("score"),
                    _keep("lead_priority"),
                    _keep("summary"),
                    _keep("one_line"),
                    _keep("keyword_score"),
                    _keep("rejection_reason"),
                    _keep("outreach_draft"),
                    _keep("author_bio"),
                    attempts,
                    now,
                    existing.get("classified_at") or classified_at,
                    None,
                    None,
                    None,
                    lead.get("classifier_provider") or existing.get("classifier_provider"),
                    post_id,
                ),
            )
            conn.commit()
            return False

        if inserted:
            cursor.execute(
                """INSERT INTO leads (
                    post_id, source, content, url, posted_at,
                    classifier_status, icp, author_role, role, intent_type, intent, problem, reason, urgency,
                    confidence, icp_score, intent_score, score, lead_priority, summary, one_line, keyword_score, rejection_reason, outreach_draft, author_bio,
                    classification_attempts, last_classification_attempt_at,
                    classified_at, classifier_error_category, classifier_error_message,
                    next_classification_retry_at, classifier_provider
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    post_id,
                    lead.get("source"),
                    lead.get("content"),
                    lead.get("url"),
                    lead.get("posted_at"),
                    incoming_status,
                    lead.get("icp"),
                    role_val,
                    role_val,
                    intent_val,
                    intent_val,
                    lead.get("problem"),
                    reason_val,
                    lead.get("urgency"),
                    score_val,
                    score_val,
                    lead.get("intent_score"),
                    score_val,
                    lead.get("lead_priority"),
                    summary_val,
                    one_line_val,
                    lead.get("keyword_score"),
                    lead.get("rejection_reason"),
                    lead.get("outreach_draft"),
                    lead.get("author_bio") or lead.get("bio"),
                    attempts,
                    now,
                    classified_at,
                    lead.get("classifier_error_category"),
                    sanitize_db_error(lead.get("classifier_error_message")),
                    next_retry,
                    lead.get("classifier_provider"),
                ),
            )
        else:
            assert existing is not None
            def _pick(field: str):
                incoming = lead.get(field)
                if field == "summary":
                    incoming = summary_val
                elif field == "one_line":
                    incoming = one_line_val
                elif field == "reason":
                    incoming = reason_val
                elif field in ("role", "author_role"):
                    incoming = role_val
                elif field in ("intent", "intent_type"):
                    incoming = intent_val
                elif field in ("score", "confidence", "icp_score"):
                    incoming = score_val
                elif field == "author_bio":
                    incoming = lead.get("author_bio") or lead.get("bio")
                if incoming is None and existing:
                    return existing.get(field)
                return incoming

            cursor.execute(
                """UPDATE leads SET
                    source=?, content=?, url=?, posted_at=?,
                    classifier_status=?, icp=?, author_role=?, role=?, intent_type=?, intent=?, problem=?, reason=?, urgency=?,
                    confidence=?, icp_score=?, intent_score=?, score=?, lead_priority=?, summary=?, one_line=?, keyword_score=?, rejection_reason=?, outreach_draft=?, author_bio=?,
                    classification_attempts=?, last_classification_attempt_at=?,
                    classified_at=?, classifier_error_category=?, classifier_error_message=?,
                    next_classification_retry_at=?, classifier_provider=?
                   WHERE post_id=?""",
                (
                    lead.get("source") or (existing.get("source") if existing else None),
                    lead.get("content") if lead.get("content") is not None else (existing.get("content") if existing else None),
                    lead.get("url") if lead.get("url") is not None else (existing.get("url") if existing else None),
                    lead.get("posted_at") if lead.get("posted_at") is not None else (existing.get("posted_at") if existing else None),
                    incoming_status,
                    _pick("icp"),
                    _pick("author_role"),
                    _pick("role"),
                    _pick("intent_type"),
                    _pick("intent"),
                    _pick("problem"),
                    _pick("reason"),
                    _pick("urgency"),
                    _pick("confidence"),
                    _pick("icp_score"),
                    _pick("intent_score"),
                    _pick("score"),
                    _pick("lead_priority"),
                    _pick("summary"),
                    _pick("one_line"),
                    _pick("keyword_score"),
                    _pick("rejection_reason"),
                    _pick("outreach_draft"),
                    _pick("author_bio"),
                    attempts,
                    now,
                    classified_at,
                    lead.get("classifier_error_category"),
                    sanitize_db_error(lead.get("classifier_error_message")),
                    next_retry,
                    lead.get("classifier_provider") or (existing.get("classifier_provider") if existing else None),
                    post_id,
                ),
            )
        conn.commit()
    return inserted


def get_existing_status_map(post_ids: list[str]) -> dict[str, str]:
    """Batch lookup of post_id -> classifier_status for dedup filtering."""
    ids = [str(pid) for pid in post_ids if pid]
    if not ids:
        return {}
    initialize_db()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        placeholders = ", ".join("?" for _ in ids)
        rows = cursor.execute(
            f"SELECT post_id, classifier_status FROM leads WHERE post_id IN ({placeholders})",
            ids,
        ).fetchall()
        return {str(row["post_id"]): (row["classifier_status"] or "") for row in rows}


def get_unsynced_leads() -> list[dict]:
    """Retrieves all qualified unsynced leads (durable before Notion)."""
    initialize_db()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE classifier_status = 'qualified' AND synced_to_notion_at IS NULL")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_pending_leads(limit: int = 64) -> list[dict]:
    """Return pending leads awaiting initial classification."""
    initialize_db()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM leads
               WHERE classifier_status IN ('pending', 'unclassified')
               ORDER BY id ASC
               LIMIT ?""",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_due_for_retry(limit: int = 64) -> list[dict]:
    """Return provider_error/classification_error/unclassified rows due for bounded retry."""
    try:
        from listening_loop import config as _config

        max_attempts = _config.MAX_CLASSIFICATION_ATTEMPTS
    except Exception:
        max_attempts = 5
    now = _utcnow()
    initialize_db()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM leads
               WHERE classifier_status IN ('provider_error', 'classification_error', 'unclassified', 'pending')
                 AND COALESCE(classification_attempts, 0) < ?
                 AND (next_classification_retry_at IS NULL OR next_classification_retry_at <= ?)
               ORDER BY next_classification_retry_at ASC NULLS FIRST, id ASC
               LIMIT ?""",
            (max_attempts, now, limit),
        )
        return [dict(row) for row in cursor.fetchall()]


def mark_as_synced(lead_ids: list[int]):
    """Marks a list of leads as synced to Notion by updating their 'synced_to_notion_at' timestamp."""
    if not lead_ids:
        return

    now = _utcnow()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        placeholders = ', '.join('?' for _ in lead_ids)
        query = f"UPDATE leads SET synced_to_notion_at = ? WHERE id IN ({placeholders})"

        params = [now] + lead_ids
        cursor.execute(query, params)
        conn.commit()


# Initialize the database when this module is imported
initialize_db()
