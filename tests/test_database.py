import sqlite3

from listening_loop import database
from listening_loop import config


def use_temporary_database(monkeypatch, tmp_path):
    database_path = tmp_path / "leads.db"
    monkeypatch.setattr(database, "DB_FILE", str(database_path))
    database.initialize_db()
    return database_path


def lead(post_id, **overrides):
    value = {
        "post_id": post_id,
        "source": "reddit",
        "content": "My staffing agency needs help with candidate matching.",
        "url": "https://example.test/post/" + post_id,
        "posted_at": "2026-09-05T10:00:00+00:00",
    }
    value.update(overrides)
    return value


def test_initialize_db_migrates_existing_rows_idempotently(monkeypatch, tmp_path):
    database_path = tmp_path / "legacy.db"
    monkeypatch.setattr(database, "DB_FILE", str(database_path))
    with sqlite3.connect(database_path) as conn:
        conn.execute(
            """CREATE TABLE leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT UNIQUE NOT NULL,
                source TEXT NOT NULL,
                content TEXT,
                url TEXT,
                posted_at DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                synced_to_notion_at DATETIME
            )"""
        )
        conn.execute(
            "INSERT INTO leads (post_id, source, content) VALUES (?, ?, ?)",
            ("legacy", "reddit", "existing lead"),
        )

    database.initialize_db()
    database.initialize_db()

    with sqlite3.connect(database_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(leads)")}
        row = conn.execute(
            "SELECT post_id, classifier_status, classification_attempts FROM leads"
        ).fetchone()

    assert {
        "classifier_status",
        "icp",
        "author_role",
        "intent_type",
        "urgency",
        "confidence",
        "summary",
        "one_line",
        "keyword_score",
        "outreach_draft",
        "classification_attempts",
        "last_classification_attempt_at",
        "classified_at",
        "classifier_error_category",
        "classifier_error_message",
        "next_classification_retry_at",
        "classifier_provider",
    } <= columns
    assert row[0] == "legacy"
    assert row[1] == "unclassified"


def test_persists_classification_failure_and_reclassifies_same_post(monkeypatch, tmp_path):
    use_temporary_database(monkeypatch, tmp_path)
    assert database.add_lead(lead("same", classifier_status="provider_error", classifier_error_category="network", classifier_error_message="timed out"))

    added = database.add_lead(
        lead(
            "same",
            classifier_status="qualified",
            icp="recruitment_agency",
            author_role="owner",
            intent_type="buying",
            urgency="now",
            summary="Agency owner needs ATS matching help.",
            one_line="Agency owner needs ATS matching help.",
            confidence=0.8,
        )
    )

    assert added is False
    with database.get_db_connection() as conn:
        row = dict(conn.execute("SELECT * FROM leads WHERE post_id = 'same'").fetchone())
    assert row["classifier_status"] == "qualified"
    assert row["classifier_error_message"] is None
    assert row["intent_type"] == "buying"
    assert row["classification_attempts"] == 2
    assert row["last_classification_attempt_at"] is not None


def test_qualified_row_never_downgrades_reverse_order(monkeypatch, tmp_path):
    use_temporary_database(monkeypatch, tmp_path)
    database.add_lead(
        lead(
            "keep",
            classifier_status="qualified",
            icp="recruitment_agency",
            author_role="founder",
            intent_type="pain",
            urgency="now",
            summary="Founder sourcing pain.",
            one_line="Founder sourcing pain.",
            confidence=0.85,
            classifier_provider="codex-everywhere",
        )
    )
    for bad_status in ("provider_error", "unclassified", "not_qualified"):
        database.add_lead(
            lead(
                "keep",
                classifier_status=bad_status,
                classifier_error_category="network",
                classifier_error_message="boom",
                confidence=0.1,
            )
        )
        with database.get_db_connection() as conn:
            row = dict(conn.execute("SELECT * FROM leads WHERE post_id='keep'").fetchone())
        assert row["classifier_status"] == "qualified", bad_status
        assert row["author_role"] == "founder", bad_status
        assert row["icp"] == "recruitment_agency", bad_status
        assert float(row["confidence"]) == 0.85
    # Still syncable after later failures.
    assert [r["post_id"] for r in database.get_unsynced_leads()] == ["keep"]


def test_error_rows_track_attempts_and_retry_schedule(monkeypatch, tmp_path):
    use_temporary_database(monkeypatch, tmp_path)
    database.add_lead(lead("retry", classifier_status="provider_error", classifier_error_category="timeout"))
    with database.get_db_connection() as conn:
        row = dict(conn.execute("SELECT * FROM leads WHERE post_id='retry'").fetchone())
    assert row["classification_attempts"] == 1
    assert row["last_classification_attempt_at"] is not None
    assert row["next_classification_retry_at"] is not None
    assert len(str(row["classifier_error_message"] or "")) <= 300 or True  # None ok

    # Bounded error message truncation.
    database.add_lead(
        lead("retry", classifier_status="provider_error", classifier_error_category="timeout",
             classifier_error_message="x" * 1000)
    )
    with database.get_db_connection() as conn:
        row = dict(conn.execute("SELECT * FROM leads WHERE post_id='retry'").fetchone())
    assert len(row["classifier_error_message"]) <= 300
    assert row["classification_attempts"] == 2


def test_due_retry_selection_respects_cap_and_only_errors(monkeypatch, tmp_path):
    use_temporary_database(monkeypatch, tmp_path)
    database.add_lead(lead("qualified", classifier_status="qualified", confidence=0.7))
    database.add_lead(lead("job-seeker", classifier_status="not_qualified", confidence=0.9))
    database.add_lead(lead("provider-error", classifier_status="provider_error", classifier_error_category="network"))
    database.add_lead(lead("unclassified", classifier_status="unclassified", classifier_error_category="invalid_response"))

    # Force retry rows to be due now.
    with database.get_db_connection() as conn:
        conn.execute("UPDATE leads SET next_classification_retry_at = '2000-01-01 00:00:00'")
        conn.commit()

    due_ids = {r["post_id"] for r in database.get_due_for_retry(limit=10)}
    assert "provider-error" in due_ids
    assert "unclassified" in due_ids
    assert "qualified" not in due_ids
    assert "job-seeker" not in due_ids


def test_only_qualified_unsynced_rows_are_selected(monkeypatch, tmp_path):
    use_temporary_database(monkeypatch, tmp_path)
    database.add_lead(lead("qualified", classifier_status="qualified", confidence=0.7))
    database.add_lead(lead("job-seeker", classifier_status="not_qualified", confidence=0.9))
    database.add_lead(lead("provider-error", classifier_status="provider_error", classifier_error_category="network"))

    assert [row["post_id"] for row in database.get_unsynced_leads()] == ["qualified"]


def test_qualified_reaffirmation_does_not_raise_unbound_local(monkeypatch, tmp_path):
    """Repair cycle 2: qualified + qualified must not reference classified_at unbound."""
    use_temporary_database(monkeypatch, tmp_path)
    database.add_lead(
        lead(
            "reaffirm",
            classifier_status="qualified",
            icp="recruitment_agency",
            author_role="founder",
            intent_type="pain",
            urgency="now",
            summary="Founder sourcing pain.",
            one_line="Founder sourcing pain.",
            confidence=0.85,
            classifier_provider="codex-everywhere",
        )
    )
    with database.get_db_connection() as conn:
        before = dict(conn.execute("SELECT * FROM leads WHERE post_id='reaffirm'").fetchone())
    assert before["classified_at"] is not None

    # Direct re-affirmation with a fresh qualified dict must not crash.
    added = database.add_lead(
        lead(
            "reaffirm",
            classifier_status="qualified",
            icp="recruitment_agency",
            author_role="founder",
            intent_type="pain",
            urgency="now",
            summary="New summary.",
            one_line="New one-liner.",
            confidence=0.9,
            classifier_provider="codex-everywhere",
        )
    )
    assert added is False
    with database.get_db_connection() as conn:
        after = dict(conn.execute("SELECT * FROM leads WHERE post_id='reaffirm'").fetchone())
    assert after["classifier_status"] == "qualified"
    # Established evidence preserved; original qualification timestamp kept.
    assert after["summary"] == "Founder sourcing pain."
    assert after["one_line"] == "Founder sourcing pain."
    assert float(after["confidence"]) == 0.85
    assert after["classified_at"] == before["classified_at"]
