import json

from listening_loop import config
from listening_loop import run
from listening_loop import qualification


def _set_dry_run_argv(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", ["run", "--dry-run"])


def lead(post_id, content="My staffing agency needs candidate matching automation."):
    return {
        "post_id": post_id,
        "source": "reddit",
        "content": content,
        "url": "https://example.test/" + post_id,
        "posted_at": "2026-09-05T10:00:00+00:00",
    }


def test_keyword_gate_accepts_all_posts_with_content():
    assert run.is_qualified_candidate(lead("job", "Looking for a job and updating my resume"))
    assert run.is_qualified_candidate(lead("advice", "How should an internal recruiter improve resume advice?"))
    assert run.is_qualified_candidate(lead("agency"))


def test_excluded_keyword_does_not_short_circuit_provider():
    excluded = lead("ex", "looking for a job, hire me please")
    assert run.is_qualified_candidate(excluded) is True


def test_enrich_and_persist_retains_provider_failure(monkeypatch):
    stored = []
    monkeypatch.setattr(run.classifier, "classify_posts", lambda leads: [{**leads[0], "classifier_status": "provider_error", "classifier_error_category": "timeout", "classifier_error_message": "timed out"}])
    # run.classify_and_store uses qualification canonical path; patch both.
    monkeypatch.setattr(run.qualification, "classify_posts", run.classifier.classify_posts)
    monkeypatch.setattr(run.database, "add_lead", lambda row: stored.append(row) or True)

    added = run.classify_and_store([lead("failed")])

    assert added == 1
    assert stored[0]["classifier_status"] == "provider_error"


def test_consecutive_provider_failures_trigger_keyword_fallback(monkeypatch):
    monkeypatch.setattr(config, "MAX_CONSECUTIVE_PROVIDER_FAILURES", 1)
    monkeypatch.setattr(config, "INTENT_BATCH_SIZE", 1)
    monkeypatch.setattr(qualification, "INTENT_BATCH_SIZE", 1)
    stored = []

    def always_fail(posts):
        # Simulate provider batch failure and bump the counter like classify_posts does.
        qualification.record_provider_outcome(True)
        return [
            {**p, "classifier_status": "provider_error",
             "classifier_error_category": "timeout",
             "classifier_error_message": "timed out",
             "classifier_provider": "codex-everywhere"}
            for p in posts
        ]

    monkeypatch.setattr(qualification, "classify_posts", always_fail)
    monkeypatch.setattr(run.database, "add_lead", lambda row: stored.append(row) or True)

    added = run.classify_and_store([lead("a"), lead("b"), lead("c")])
    assert added == 3
    # First batch hit provider; remaining used keyword-only fallback.
    assert stored[0]["classifier_status"] == "provider_error"
    assert stored[1]["classifier_status"] == "unclassified"
    assert stored[1]["classifier_error_category"] == "provider_fallback"
    assert stored[2]["classifier_error_category"] == "provider_fallback"
    qualification.reset_consecutive_failures()


def test_classify_and_store_respects_batch_cap(monkeypatch):
    monkeypatch.setattr(config, "CLASSIFICATION_BATCH_CAP", 2)
    seen = []
    monkeypatch.setattr(
        run.qualification, "classify_posts",
        lambda posts: seen.extend([p["post_id"] for p in posts]) or [
            {**p, "classifier_status": "not_qualified"} for p in posts
        ],
    )
    monkeypatch.setattr(run.database, "add_lead", lambda row: True)
    qualification.reset_consecutive_failures()

    run.classify_and_store([lead("1"), lead("2"), lead("3")])
    assert seen == ["1", "2"]


def test_notion_enrichment_uses_existing_property_names():
    properties = run.notion_sync.build_notion_properties(
        {
            **lead("qualified"),
            "classifier_status": "qualified",
            "author_role": "owner",
            "intent_type": "pain",
            "urgency": "now",
            "one_line": "Owner cannot source enough candidates.",
            "confidence": 0.9,
        }
    )

    assert properties["Summary"]["rich_text"][0]["text"]["content"] == "Owner cannot source enough candidates."
    assert properties["Author Role"]["rich_text"][0]["text"]["content"] == "owner"
    assert properties["Intent Type"]["select"]["name"] == "pain"


def test_main_dry_run_skips_notion_but_persists(monkeypatch):
    monkeypatch.setattr(run.config, "PLATFORMS", ["reddit"])
    monkeypatch.setattr(run.opencli_adapter, "fetch_leads", lambda *a, **k: [lead("dry")])
    monkeypatch.setattr(run, "is_qualified_candidate", lambda l: True)
    monkeypatch.setattr(run, "classify_and_store", lambda leads, *args, **kwargs: 1)
    monkeypatch.setattr(run.database, "get_unsynced_leads", lambda: (_ for _ in ()).throw(AssertionError("should not query")))
    monkeypatch.setattr(
        run.notion_sync, "sync_leads_to_notion",
        lambda leads: (_ for _ in ()).throw(AssertionError("should not sync")),
    )
    import sys
    monkeypatch.setattr(sys, "argv", ["run", "--dry-run"])
    run.main()  # should return without sync


def test_main_continues_across_platform_failure(monkeypatch):
    monkeypatch.setattr(run.config, "PLATFORMS", ["twitter", "reddit"])

    def flaky_fetch(platform, *a, **k):
        if platform == "twitter":
            raise RuntimeError("boom")
        return [lead("ok")]

    monkeypatch.setattr(run.opencli_adapter, "fetch_leads", flaky_fetch)
    monkeypatch.setattr(run, "is_qualified_candidate", lambda l: True)
    monkeypatch.setattr(run, "classify_and_store", lambda leads, *args, **kwargs: 1 if leads and leads[0]["post_id"] == "ok" else 0)
    monkeypatch.setattr(run.database, "get_unsynced_leads", lambda: [])
    import sys
    monkeypatch.setattr(sys, "argv", ["run"])
    run.main()


def test_main_skips_discovered_leads_when_status_lookup_fails(monkeypatch, capsys):
    monkeypatch.setattr(run.config, "PLATFORMS", ["twitter"])
    monkeypatch.setattr(run.config, "DISCOVERY_QUERIES", {"family": ["query"]})
    monkeypatch.setattr(run.opencli_adapter, "fetch_leads", lambda *args: [lead("unknown")])
    monkeypatch.setattr(run, "is_qualified_candidate", lambda candidate: True)
    monkeypatch.setattr(
        run.database,
        "get_existing_status_map",
        lambda ids: (_ for _ in ()).throw(RuntimeError("database credentials leaked")),
    )
    monkeypatch.setattr(run.database, "get_due_for_retry", lambda limit: [])
    monkeypatch.setattr(
        run,
        "classify_and_store",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not classify")),
    )
    _set_dry_run_argv(monkeypatch)

    run.main()

    output = capsys.readouterr().out
    assert "Database status lookup unavailable" in output
    assert "database credentials leaked" not in output
    assert '"database_errors": 1' in output
    assert '"classification_skipped_database_status": 1' in output


def test_main_runs_all_queries_unscoped_for_non_reddit_platform(monkeypatch):
    monkeypatch.setattr(run.config, "PLATFORMS", ["twitter"])
    calls = []

    def fetch(platform, query, hours, community, family):
        calls.append((platform, query, hours, community, family))
        return []

    monkeypatch.setattr(run.opencli_adapter, "fetch_leads", fetch)
    monkeypatch.setattr(run.database, "get_existing_status_map", lambda ids: {})
    monkeypatch.setattr(run.database, "get_due_for_retry", lambda limit: [])
    _set_dry_run_argv(monkeypatch)

    run.main()

    n_queries = sum(len(v) for v in run.config.DISCOVERY_QUERIES.values())
    assert len(calls) == n_queries
    assert all(platform == "twitter" and community is None for platform, _, _, community, _ in calls)


def test_rate_limit_cooldown_returns_sampled_float(monkeypatch):
    sleeps = []
    monkeypatch.setattr(run, "_sleep_for", sleeps.append)
    cooldown = run._rate_limit_cooldown(1)
    assert isinstance(cooldown, float)
    assert config.RATE_LIMIT_BACKOFF_MIN <= cooldown <= config.RATE_LIMIT_BACKOFF_MAX
    assert sleeps == [cooldown]


def test_rate_limit_retries_then_halts_only_that_platform(monkeypatch, caplog):
    calls = []
    sleeps = []
    attempts = {"reddit": 0}

    def fetch(platform, query, hours, community, family):
        calls.append((platform, query, community))
        if platform == "reddit":
            attempts[platform] += 1
            raise run.opencli_adapter.OpenCLIRateLimitError("HTTP 429")
        return []

    monkeypatch.setattr(run.config, "DISCOVERY_QUERIES", {"family": ["query"]})
    monkeypatch.setattr(run.config, "FACEBOOK_QUERIES", {"family": ["query"]})
    monkeypatch.setattr(run.config, "PLATFORMS", ["reddit", "twitter"])
    monkeypatch.setattr(run.config, "LEAD_SUBREDDITS", ["staffing"])
    monkeypatch.setattr(run.opencli_adapter, "fetch_leads", fetch)
    monkeypatch.setattr(run, "_sleep_for", sleeps.append)
    monkeypatch.setattr(run.database, "get_existing_status_map", lambda ids: {})
    monkeypatch.setattr(run.database, "get_due_for_retry", lambda limit: [])
    monkeypatch.setattr(run.database, "get_unsynced_leads", lambda: [])
    _set_dry_run_argv(monkeypatch)

    with caplog.at_level("WARNING"):
        run.main()

    assert attempts["reddit"] == 4
    assert [platform for platform, _, _ in calls] == ["reddit", "reddit", "reddit", "reddit", "twitter"]
    assert len(sleeps) == 8
    assert 3 <= sleeps[0] <= 7
    assert 60 <= sleeps[1] <= 300
    assert 3 <= sleeps[2] <= 7
    assert 60 <= sleeps[3] <= 300
    assert 3 <= sleeps[4] <= 7
    assert 60 <= sleeps[5] <= 300
    assert 3 <= sleeps[6] <= 7
    assert 3 <= sleeps[7] <= 7
    assert any(f"Rate limited on reddit. Waiting {sleeps[1]:.1f}s cooldown before retry..." in r.message for r in caplog.records)


def test_rate_limit_successful_retry_leaves_query_report_successful(monkeypatch, caplog, capsys):
    calls = []
    sleeps = []
    attempts = 0

    def fetch(platform, query, hours, community, family):
        nonlocal attempts
        attempts += 1
        calls.append((platform, query, community))
        if attempts == 1:
            raise run.opencli_adapter.OpenCLIRateLimitError("HTTP 429")
        return [lead("recovered")]

    monkeypatch.setattr(run.config, "DISCOVERY_QUERIES", {"family": ["query"]})
    monkeypatch.setattr(run.config, "PLATFORMS", ["reddit"])
    monkeypatch.setattr(run.config, "LEAD_SUBREDDITS", ["staffing"])
    monkeypatch.setattr(run.opencli_adapter, "fetch_leads", fetch)
    monkeypatch.setattr(run, "_sleep_for", sleeps.append)
    monkeypatch.setattr(run.database, "get_existing_status_map", lambda ids: {})
    monkeypatch.setattr(run.database, "get_due_for_retry", lambda limit: [])
    monkeypatch.setattr(run.database, "get_unsynced_leads", lambda: [])
    monkeypatch.setattr(run, "is_qualified_candidate", lambda candidate: True)
    monkeypatch.setattr(run, "classify_and_store", lambda leads, **kwargs: len(leads))
    _set_dry_run_argv(monkeypatch)

    with caplog.at_level("WARNING"):
        run.main()

    assert attempts == 2
    assert len(calls) == 2
    assert calls[0] == ("reddit", "query", "staffing")
    assert calls[1] == ("reddit", "query", "staffing")

    # Deterministic sequence:
    # 1. pace between attempts (3-7s)
    # 2. cooldown (60-90s)
    # 3. pace between attempts after successful retry (3-7s)
    assert len(sleeps) == 3
    assert 3.0 <= sleeps[0] <= 7.0
    assert 60.0 <= sleeps[1] <= 90.0
    assert 3.0 <= sleeps[2] <= 7.0

    # Warning log includes exact cooldown seconds
    expected_msg = f"Rate limited on reddit. Waiting {sleeps[1]:.1f}s cooldown before retry..."
    assert any(expected_msg in record.message for record in caplog.records)

    # Query report shows success (errors == 0, posts_retrieved == 1)
    out = capsys.readouterr().out
    report_line = next(line for line in out.splitlines() if line.startswith("Query performance report: "))
    report = json.loads(report_line.split(": ", 1)[1])
    assert len(report) == 1
    assert report[0]["platform"] == "reddit"
    assert report[0]["community"] == "staffing"
    assert report[0]["errors"] == 0
    assert report[0]["posts_retrieved"] == 1


def test_main_processes_due_retry_also_returned_by_discovery(monkeypatch):
    monkeypatch.setattr(run.config, "PLATFORMS", ["twitter"])
    monkeypatch.setattr(run.config, "DISCOVERY_QUERIES", {"family": ["query"]})
    monkeypatch.setattr(run.opencli_adapter, "fetch_leads", lambda *args: [lead("retry")])
    monkeypatch.setattr(run, "is_qualified_candidate", lambda candidate: True)
    monkeypatch.setattr(run.database, "get_existing_status_map", lambda ids: {"retry": "provider_error"})
    monkeypatch.setattr(
        run.database,
        "get_due_for_retry",
        lambda limit: [{**lead("retry"), "classifier_status": "provider_error"}],
    )
    received = []
    monkeypatch.setattr(
        run,
        "classify_and_store",
        lambda leads, **kwargs: received.extend(leads) or 0,
    )
    _set_dry_run_argv(monkeypatch)

    run.main()

    assert [candidate["post_id"] for candidate in received] == ["retry"]
