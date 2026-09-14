"""Repair cycle 1 regression tests: redaction, dedup, monotonic evidence, batch IDs."""

import json
import subprocess

from listening_loop import database
from listening_loop import qualification
from listening_loop import run
from listening_loop import opencli_adapter


def use_tmp_db(monkeypatch, tmp_path):
    database_path = tmp_path / "repair.db"
    monkeypatch.setattr(database, "DB_FILE", str(database_path))
    database.initialize_db()
    return database_path


def lead(post_id, **overrides):
    value = {
        "post_id": post_id,
        "source": "reddit",
        "content": "My staffing agency needs candidate matching automation.",
        "url": "https://example.test/post/" + post_id,
        "posted_at": "2026-09-05T10:00:00+00:00",
    }
    value.update(overrides)
    return value


def test_url_query_credentials_redacted():
    cases = [
        "GET https://api.example.test/search?token=secret123 failed",
        "GET https://api.example.test/x?api_key=AKIA-SECRET-VALUE failed",
        "GET https://api.example.test/x?key=abcdef&other=1 failed",
        "GET https://api.example.test/x?access_token=tok-xyz failed",
        "GET https://api.example.test/x?secret=s3cr3t failed",
        "Authorization: Bearer super-secret-token-value",
        "authorization: bearer super-secret-token-value",
        "Authorization: Basic dXNlcjpwYXNzd29yZA==",
    ]
    secrets = ["secret123", "AKIA-SECRET-VALUE", "abcdef", "tok-xyz", "s3cr3t",
               "super-secret-token-value", "dXNlcjpwYXNzd29yZA=="]
    for raw in cases:
        cleaned = qualification.sanitize_error_message(raw)
        for secret in secrets:
            assert secret not in cleaned, (raw, cleaned)
        assert "[REDACTED]" in cleaned, (raw, cleaned)
    # Legacy helper routes through the canonical sanitizer too.
    assert "secret123" not in qualification._bounded_error("?token=secret123")


def test_terminal_leads_never_reclassified_and_run_dedupes(monkeypatch, tmp_path):
    use_tmp_db(monkeypatch, tmp_path)
    database.add_lead(lead("q1", classifier_status="qualified", icp="recruitment_agency",
                           author_role="owner", intent_type="buying", urgency="now",
                           summary="Owner ATS pain.", one_line="Owner ATS pain.", confidence=0.9))
    database.add_lead(lead("n1", classifier_status="not_qualified", confidence=0.9))
    # No rows are due for retry (qualified/not_qualified are never retryable).
    assert database.get_due_for_retry(limit=10) == []

    monkeypatch.setattr(run.config, "PLATFORMS", ["reddit"])
    monkeypatch.setattr(
        run.opencli_adapter, "fetch_leads",
        lambda *a, **k: [lead("q1"), lead("n1"), lead("fresh"), lead("fresh")],
    )
    monkeypatch.setattr(run, "is_qualified_candidate", lambda l: True)
    seen_batches = []

    def fake_classify(posts):
        seen_batches.append([p["post_id"] for p in posts])
        return [{**p, "classifier_status": "not_qualified"} for p in posts]

    monkeypatch.setattr(run.qualification, "classify_posts", fake_classify)
    monkeypatch.setattr(run.database, "get_unsynced_leads", lambda: [])
    import sys
    monkeypatch.setattr(sys, "argv", ["run"])
    run.main()

    flat = [pid for batch in seen_batches for pid in batch]
    assert flat == ["fresh"], flat
    # The duplicate fresh post was sent to the provider only once.
    assert len(flat) == len(set(flat)) == 1


def test_classify_and_store_dedupes_within_call(monkeypatch):
    monkeypatch.setattr(run.database, "add_lead", lambda row: True)
    received = []

    def fake_classify(posts):
        received.extend(p["post_id"] for p in posts)
        return [{**p, "classifier_status": "not_qualified"} for p in posts]

    monkeypatch.setattr(run.qualification, "classify_posts", fake_classify)
    qualification.reset_consecutive_failures()
    run.classify_and_store([lead("dup"), lead("dup"), lead("other")])
    assert sorted(received) == ["dup", "other"]
    qualification.reset_consecutive_failures()


def test_qualified_evidence_monotonic_on_reaffirmation(monkeypatch, tmp_path):
    use_tmp_db(monkeypatch, tmp_path)
    database.add_lead(lead(
        "keep", classifier_status="qualified", icp="recruitment_agency",
        author_role="founder", intent_type="pain", urgency="now",
        summary="Founder sourcing pain.", one_line="Founder sourcing pain.",
        confidence=0.85, classifier_provider="codex-everywhere",
    ))
    with database.get_db_connection() as conn:
        row_id = conn.execute("SELECT id FROM leads WHERE post_id='keep'").fetchone()["id"]
    database.mark_as_synced([row_id])

    # A later qualified outcome with conflicting evidence and missing fields
    # must not overwrite established non-null evidence; missing fields stay.
    database.add_lead(lead(
        "keep", classifier_status="qualified", icp="independent_recruiter",
        author_role="owner", intent_type="buying", urgency="later",
        summary="Different summary.", one_line="Different one-liner.",
        confidence=0.61, classifier_provider="codex-everywhere",
    ))
    with database.get_db_connection() as conn:
        row = dict(conn.execute("SELECT * FROM leads WHERE post_id='keep'").fetchone())
    assert row["classifier_status"] == "qualified"
    assert row["icp"] == "recruitment_agency"
    assert row["author_role"] == "founder"
    assert row["intent_type"] == "pain"
    assert row["urgency"] == "now"
    assert float(row["confidence"]) == 0.85
    assert row["summary"] == "Founder sourcing pain."
    assert row["one_line"] == "Founder sourcing pain."
    assert row["synced_to_notion_at"] is not None

    # A qualified row with a previously-missing field may have it filled.
    database_path2 = tmp_path / "repair2.db"
    monkeypatch.setattr(database, "DB_FILE", str(database_path2))
    database.initialize_db()
    database.add_lead(lead("partial", classifier_status="qualified", icp="recruitment_agency",
                           author_role="owner", intent_type="buying", confidence=0.7))
    database.add_lead(lead("partial", classifier_status="qualified", icp="recruitment_agency",
                           author_role="owner", intent_type="buying", urgency="soon",
                           summary="Filled.", one_line="Filled.", confidence=0.7))
    with database.get_db_connection() as conn:
        filled = dict(conn.execute("SELECT * FROM leads WHERE post_id='partial'").fetchone())
    assert filled["urgency"] == "soon"
    assert filled["summary"] == "Filled."
    assert filled["icp"] == "recruitment_agency"


def _valid_item(pid, **overrides):
    item = {
        "id": pid,
        "icp": "yes",
        "score": overrides.get("score", 0.8),
        "role": "owner",
        "problem": "ats_crm",
        "intent": "buying",
        "reason": "Agency owner needs ATS help.",
    }
    item.update(overrides)
    return item


def _payload(items):
    return {"choices": [{"message": {"content": json.dumps(items)}}]}


def test_strict_batch_id_mismatch_marks_entire_batch_unclassified():
    # Unknown ID present alongside a valid one.
    out = qualification.parse_response(_payload([_valid_item("a"), _valid_item("zzz")]), {"a", "b"})
    assert set(out) == {"a", "b"}
    assert all(v["classifier_status"] in ("unclassified", "classification_error") for v in out.values())
    assert all(v["classifier_error_category"] == "invalid_response" for v in out.values())

    # Duplicate ID.
    out = qualification.parse_response(_payload([_valid_item("a"), _valid_item("a")]), {"a"})
    assert out["a"]["classifier_status"] in ("unclassified", "classification_error")

    # Set mismatch: response omits one requested ID.
    out = qualification.parse_response(_payload([_valid_item("a")]), {"a", "b"})
    assert out["a"]["classifier_status"] in ("unclassified", "classification_error")
    assert out["b"]["classifier_status"] in ("unclassified", "classification_error")

    # Non-object item poisons the batch.
    out = qualification.parse_response(_payload([_valid_item("a"), "nope"]), {"a"})
    assert out["a"]["classifier_status"] in ("unclassified", "classification_error")

    # Control: exact ID set with valid enums still classifies per item.
    out = qualification.parse_response(_payload([_valid_item("a"), _valid_item("b")]), {"a", "b"})
    assert out["a"]["classifier_status"] == "qualified"
    assert out["b"]["classifier_status"] == "qualified"


def test_opencli_adapter_never_dumps_raw_malformed_json(capsys, monkeypatch):
    monkeypatch.setattr(
        opencli_adapter.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a[0], 0, '{"id":"one"}\nnot-json {secret stuff', ""),
    )
    assert opencli_adapter.run_opencli("reddit", "q") == [{"id": "one"}]
    captured = capsys.readouterr()
    assert "secret stuff" not in captured.out
    assert "not-json" not in captured.out
