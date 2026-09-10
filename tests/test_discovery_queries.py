from datetime import datetime, timezone

from listening_loop import config, opencli_adapter, run


ORIGINAL_QUALIFYING_KEYWORDS = config.QUALIFYING_KEYWORDS
ORIGINAL_EXCLUDED_KEYWORDS = config.EXCLUDED_KEYWORDS


EXPECTED = {
    "agency_client_acquisition": [
        "recruitment agency getting clients",
        "staffing agency client acquisition",
        "recruitment business new business",
    ],
    "agency_pipeline_pain": [
        "recruitment agency need more clients",
        "staffing agency pipeline is dry",
        "recruitment business job flow",
    ],
    "agency_outbound": [
        "recruitment agency cold email",
        "staffing agency linkedin outreach",
        "recruitment business outbound sales",
    ],
    "agency_operations": [
        "recruitment agency candidate database",
        "staffing agency ATS automation",
        "recruitment agency CRM automation",
    ],
}

EXPECTED_SUBREDDITS = [
    "recruiting", "staffing", "Recruitment", "freelanceRecruiters",
]


def test_discovery_configuration_is_exact_and_ordered():
    assert config.PLATFORMS == ["reddit", "twitter"]
    assert (config.INTER_QUERY_SLEEP_MIN, config.INTER_QUERY_SLEEP_MAX) == (3.0, 7.0)
    assert (config.RATE_LIMIT_BACKOFF_MIN, config.RATE_LIMIT_BACKOFF_MAX) == (60.0, 90.0)
    assert config.MAX_RATE_LIMIT_RETRIES == 1
    assert config.LEAD_SUBREDDITS == EXPECTED_SUBREDDITS
    assert config.REDDIT_COMMUNITIES == EXPECTED_SUBREDDITS
    assert config.DISCOVERY_QUERIES == EXPECTED
    assert config.QUALIFYING_KEYWORDS == ORIGINAL_QUALIFYING_KEYWORDS
    assert config.EXCLUDED_KEYWORDS == ORIGINAL_EXCLUDED_KEYWORDS


def test_discovery_queries_syntax_integrity():
    assert list(config.DISCOVERY_QUERIES.keys()) == [
        "agency_client_acquisition",
        "agency_pipeline_pain",
        "agency_outbound",
        "agency_operations",
    ]
    all_queries = [
        q for family_queries in config.DISCOVERY_QUERIES.values() for q in family_queries
    ]
    assert len(all_queries) == 12
    for q in all_queries:
        assert isinstance(q, str) and len(q.strip()) > 0
        assert '"' not in q, f"Query contains double quotes: {q}"
        assert "'" not in q, f"Query contains single quotes: {q}"
        assert " OR " not in q, f"Query contains OR operator: {q}"
        assert " AND " not in q, f"Query contains AND operator: {q}"
        assert not (q.startswith('"') and q.endswith('"')), f"Query is wrapped in quotes: {q}"


def test_adapter_executes_one_exact_scoped_query_and_attaches_provenance(monkeypatch):
    captured = {}
    now = datetime.now(timezone.utc).isoformat()

    def fake_run(platform, query, community=None):
        captured.update(platform=platform, query=query, community=community)
        return [{"id": "p1", "title": "Agency", "selftext": "ATS", "created_utc": now}]

    monkeypatch.setattr(opencli_adapter, "run_opencli", fake_run)
    query = EXPECTED["agency_client_acquisition"][0]
    lead = opencli_adapter.fetch_leads("reddit", query, 24, "Recruitment", "agency_client_acquisition")[0]
    assert captured == {"platform": "reddit", "query": query, "community": "Recruitment"}
    assert lead["platform"] == "reddit"
    assert lead["community"] == "Recruitment"
    assert lead["query_family"] == "agency_client_acquisition"
    assert lead["exact_query"] == query
    assert lead["retrieved_at"].tzinfo == timezone.utc


def test_run_opencli_uses_documented_reddit_scope(monkeypatch):
    captured = []
    opencli_adapter._SUBREDDIT_SCOPE_SUPPORTED = None

    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        output = "--subreddit [value]" if cmd[-1] == "--help" else "[]"
        return __import__("subprocess").CompletedProcess(cmd, 0, output, "")

    monkeypatch.setattr(opencli_adapter.subprocess, "run", fake_run)
    opencli_adapter.run_opencli("reddit", "recruitment agency getting clients", "staffing")
    assert captured[1] == [
        "opencli",
        "reddit",
        "search",
        "recruitment agency getting clients",
        "--sort",
        "new",
        "--subreddit",
        "staffing",
        "--format",
        "json",
    ]


def test_subreddit_scope_verification_requires_documented_option_syntax(monkeypatch):
    opencli_adapter._SUBREDDIT_SCOPE_SUPPORTED = None

    def fake_run(cmd, **kwargs):
        return __import__("subprocess").CompletedProcess(
            cmd, 0, "Use --subreddit to filter communities.", ""
        )

    monkeypatch.setattr(opencli_adapter.subprocess, "run", fake_run)

    try:
        opencli_adapter.verify_subreddit_scoping_supported()
    except opencli_adapter.UnsupportedSubredditScopeError:
        pass
    else:
        raise AssertionError("Expected undocumented --subreddit mention to be rejected")


def test_run_report_is_structured_and_counts_failed_query(monkeypatch, capsys):
    monkeypatch.setattr(run, "_sleep_for", lambda seconds: None)
    monkeypatch.setattr(run.config, "PLATFORMS", ["reddit"])
    monkeypatch.setattr(run.config, "DISCOVERY_QUERIES", {"family": ["q1"]})
    monkeypatch.setattr(run.config, "LEAD_SUBREDDITS", ["staffing"])
    monkeypatch.setattr(
        run.opencli_adapter,
        "fetch_leads",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            opencli_adapter.OpenCLIExecutionError("mocked failure")
        ),
    )
    monkeypatch.setattr(run.database, "get_existing_status_map", lambda ids: {})
    monkeypatch.setattr(run.database, "get_due_for_retry", lambda limit: [])
    monkeypatch.setattr(run.database, "get_unsynced_leads", lambda: [])
    import sys
    monkeypatch.setattr(sys, "argv", ["run", "--dry-run"])

    run.main()

    report_line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("Query performance report: "))
    report = __import__("json").loads(report_line.split(": ", 1)[1])
    assert report == [{
        "community": "staffing", "duplicates_removed": 0, "errors": 1,
        "exact_query": "q1", "luna_qualified": 0, "luna_rejected": 0,
        "platform": "reddit", "posts_retrieved": 0, "stage_one_passed": 0,
        "query_family": "family",
    }]


def test_reddit_default_queries_expand_to_correct_discrete_work_items(monkeypatch, capsys):
    # 12 queries × 4 subreddits = 48 Reddit work items
    monkeypatch.setattr(run, "_sleep_for", lambda seconds: None)
    monkeypatch.setattr(run.config, "PLATFORMS", ["reddit"])
    calls = []

    def fetch(platform, query, hours, community, family):
        calls.append((platform, query, hours, community, family))
        return []

    monkeypatch.setattr(run.opencli_adapter, "fetch_leads", fetch)
    monkeypatch.setattr(run.database, "get_existing_status_map", lambda ids: {})
    monkeypatch.setattr(run.database, "get_due_for_retry", lambda limit: [])
    monkeypatch.setattr(run.database, "get_unsynced_leads", lambda: [])
    import sys
    monkeypatch.setattr(sys, "argv", ["run", "--dry-run"])

    run.main()

    expected_queries = [
        query
        for queries in config.DISCOVERY_QUERIES.values()
        for query in queries
    ]
    n_queries = sum(len(v) for v in config.DISCOVERY_QUERIES.values())
    n_subreddits = len(config.LEAD_SUBREDDITS)
    expected_calls = n_queries * n_subreddits
    assert len(expected_queries) == n_queries
    assert len(calls) == expected_calls
    assert all(platform == "reddit" for platform, *_ in calls)
    assert all(query in expected_queries for _, query, _, _, _ in calls)
    assert all(community in config.LEAD_SUBREDDITS for _, _, _, community, _ in calls)
    assert all(" OR " not in query for _, query, _, _, _ in calls)
    assert len({(query, community) for _, query, _, community, _ in calls}) == expected_calls

    report_line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("Query performance report: "))
    report = __import__("json").loads(report_line.split(": ", 1)[1])
    assert len(report) == expected_calls
    assert all(item["errors"] == 0 for item in report)


def test_all_platforms_schedule_48_reddit_and_12_twitter_items(monkeypatch):
    calls = []
    monkeypatch.setattr(run, "_sleep_for", lambda seconds: None)
    monkeypatch.setattr(run.opencli_adapter, "fetch_leads", lambda *args: calls.append(args) or [])
    monkeypatch.setattr(run.database, "get_existing_status_map", lambda ids: {})
    monkeypatch.setattr(run.database, "get_due_for_retry", lambda limit: [])
    monkeypatch.setattr(run.database, "get_unsynced_leads", lambda: [])
    import sys
    monkeypatch.setattr(sys, "argv", ["run", "--dry-run"])
    run.main()
    assert len(calls) == 60
    assert sum(call[0] == "reddit" for call in calls) == 48
    assert sum(call[0] == "twitter" for call in calls) == 12
    assert [call[0] for call in calls] == ["reddit"] * 48 + ["twitter"] * 12
    assert all(call[3] in config.REDDIT_COMMUNITIES for call in calls[:48])
    assert all(call[3] is None for call in calls[48:])


def test_exact_60_item_sequence_order_all_platforms(monkeypatch):
    calls = []
    monkeypatch.setattr(run, "_sleep_for", lambda seconds: None)
    monkeypatch.setattr(run.opencli_adapter, "fetch_leads", lambda *args: calls.append(args) or [])
    monkeypatch.setattr(run.database, "get_existing_status_map", lambda ids: {})
    monkeypatch.setattr(run.database, "get_due_for_retry", lambda limit: [])
    monkeypatch.setattr(run.database, "get_unsynced_leads", lambda: [])
    import sys
    monkeypatch.setattr(sys, "argv", ["run", "--dry-run"])
    run.main()

    # Exact 60-item sequence order: first 48 are reddit, next 12 are twitter
    assert len(calls) == 60
    assert [call[0] for call in calls] == ["reddit"] * 48 + ["twitter"] * 12
    assert all(call[3] in config.REDDIT_COMMUNITIES for call in calls[:48])
    assert all(call[3] is None for call in calls[48:])

    # Assert all 60 calls receive unquoted strings with no boolean operators or rigid quotes
    approved_queries = {q for queries in EXPECTED.values() for q in queries}
    for platform, query, hours, community, family in calls:
        assert query in approved_queries
        assert '"' not in query
        assert "'" not in query
        assert " OR " not in query
        assert " AND " not in query


def test_run_dedupes_across_query_work_items_and_reports(monkeypatch, capsys):
    monkeypatch.setattr(run, "_sleep_for", lambda seconds: None)
    monkeypatch.setattr(run.config, "PLATFORMS", ["reddit"])
    monkeypatch.setattr(run.config, "DISCOVERY_QUERIES", {"family": ["q1", "q2"]})
    calls = []
    def fetch(platform, query, hours, community, family):
        calls.append((query, community))
        return [{"post_id": "same", "source": platform, "content": "agency", "posted_at": now}]
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(run.opencli_adapter, "fetch_leads", fetch)
    monkeypatch.setattr(run, "is_qualified_candidate", lambda lead: True)
    received = []
    monkeypatch.setattr(run, "classify_and_store", lambda leads, outcome_callback=None: received.extend(leads) or 0)
    monkeypatch.setattr(run.database, "get_existing_status_map", lambda ids: {})
    monkeypatch.setattr(run.database, "get_due_for_retry", lambda limit: [])
    monkeypatch.setattr(run.database, "get_unsynced_leads", lambda: [])
    import sys
    monkeypatch.setattr(sys, "argv", ["run", "--dry-run"])
    run.main()
    # 2 queries × len(LEAD_SUBREDDITS) subreddits = expected call count
    assert len(calls) == 2 * len(config.LEAD_SUBREDDITS)
    assert [lead["post_id"] for lead in received] == ["same"]
    assert '"duplicates_removed": 1' in capsys.readouterr().out
