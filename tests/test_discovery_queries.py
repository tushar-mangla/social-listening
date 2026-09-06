from datetime import datetime, timezone

from listening_loop import config, opencli_adapter, run


ORIGINAL_QUALIFYING_KEYWORDS = config.QUALIFYING_KEYWORDS
ORIGINAL_EXCLUDED_KEYWORDS = config.EXCLUDED_KEYWORDS


EXPECTED = {
    "agency_business_development": [
        "getting clients",
        "find new clients",
        "finding clients",
        "win new clients",
        "winning clients",
        "client acquisition",
        "new business",
        "business development",
        "lead generation",
        "generate leads",
        "sales pipeline",
        "BD strategy",
        "BD calls",
    ],
    "agency_pipeline_pain": [
        "need more clients",
        "struggling to get clients",
        "struggling with BD",
        "pipeline is dry",
        "dry pipeline",
        "referrals drying up",
        "referrals have dried up",
        "not enough clients",
        "not enough vacancies",
        "job flow",
        "more job flow",
        "new vacancies",
        "new roles",
    ],
    "agency_outbound": [
        "cold email",
        "cold emailing",
        "cold calling",
        "linkedin outreach",
        "outbound",
        "outbound sales",
        "email outreach",
        "reply rate",
        "response rate",
        "booking meetings",
        "book more meetings",
        "prospecting",
    ],
    "agency_operations": [
        "recruitment automation",
        "recruiting automation",
        "staffing automation",
        "recruitment workflow",
        "recruiting workflow",
        "ATS automation",
        "CRM automation",
        "recruitment CRM",
        "staffing CRM",
        "recruitment ATS",
    ],
    "candidate_database": [
        "candidate database",
        "candidate database sitting",
        "old candidates",
        "database candidates",
        "database marketing",
        "candidate rediscovery",
        "candidate matching",
        "candidate to client",
        "candidate marketing",
        "market candidates",
        "reverse marketing",
    ],
    "agency_language": [
        "recruitment agency",
        "recruitment business",
        "recruiting agency",
        "staffing agency",
        "staffing firm",
        "recruitment firm",
        "executive search firm",
        "recruitment founder",
        "staffing founder",
        "agency owner",
        "recruitment owner",
        "recruitment director",
        "staffing owner",
        "360 recruiter",
        "recruitment consultant",
    ],
}

EXPECTED_SUBREDDITS = [
    "recruiting", "staffing", "Recruitment", "freelanceRecruiters",
]


def test_discovery_configuration_is_exact_and_ordered():
    assert config.LEAD_SUBREDDITS == EXPECTED_SUBREDDITS
    assert config.DISCOVERY_QUERIES == EXPECTED
    assert config.QUALIFYING_KEYWORDS == ORIGINAL_QUALIFYING_KEYWORDS
    assert config.EXCLUDED_KEYWORDS == ORIGINAL_EXCLUDED_KEYWORDS


def test_adapter_executes_one_exact_scoped_query_and_attaches_provenance(monkeypatch):
    captured = {}
    now = datetime.now(timezone.utc).isoformat()

    def fake_run(platform, query, community=None):
        captured.update(platform=platform, query=query, community=community)
        return [{"id": "p1", "title": "Agency", "selftext": "ATS", "created_utc": now}]

    monkeypatch.setattr(opencli_adapter, "run_opencli", fake_run)
    lead = opencli_adapter.fetch_leads("reddit", EXPECTED["agency_language"][0], 24, "Recruitment", "agency_language")[0]
    assert captured == {"platform": "reddit", "query": EXPECTED["agency_language"][0], "community": "Recruitment"}
    assert lead["platform"] == "reddit"
    assert lead["community"] == "Recruitment"
    assert lead["query_family"] == "agency_language"
    assert lead["exact_query"] == EXPECTED["agency_language"][0]
    assert lead["retrieved_at"].tzinfo == timezone.utc


def test_run_opencli_uses_documented_reddit_scope(monkeypatch):
    captured = []
    opencli_adapter._SUBREDDIT_SCOPE_SUPPORTED = None

    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        output = "--subreddit [value]" if cmd[-1] == "--help" else "[]"
        return __import__("subprocess").CompletedProcess(cmd, 0, output, "")

    monkeypatch.setattr(opencli_adapter.subprocess, "run", fake_run)
    opencli_adapter.run_opencli("reddit", '"agency" "clients"', "staffing")
    assert captured[1] == ["opencli", "reddit", "search", '"agency" "clients"', "--sort", "new", "--subreddit", "staffing", "--format", "json"]


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
    monkeypatch.setattr(run.config, "DISCOVERY_QUERY_DELAY_SECONDS", 0)
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
    # 18 queries × 7 subreddits = 126 Reddit work items
    monkeypatch.setattr(run.config, "DISCOVERY_QUERY_DELAY_SECONDS", 0)
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


def test_run_dedupes_across_query_work_items_and_reports(monkeypatch, capsys):
    monkeypatch.setattr(run.config, "DISCOVERY_QUERY_DELAY_SECONDS", 0)
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
