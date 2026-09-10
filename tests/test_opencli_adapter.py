import subprocess
from datetime import datetime, timezone

import pytest

from listening_loop import opencli_adapter


def test_run_opencli_accepts_json_lines_and_discards_non_objects(monkeypatch):
    monkeypatch.setattr(
        opencli_adapter.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, '{"id":"one"}\n[]\ninvalid', ""),
    )

    assert opencli_adapter.run_opencli("reddit", "staffing") == [{"id": "one"}]


def test_run_opencli_handles_nonzero_exit_and_timeout(monkeypatch):
    monkeypatch.setattr(
        opencli_adapter.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "failed"),
    )
    try:
        opencli_adapter.run_opencli("reddit", "staffing")
    except opencli_adapter.OpenCLIExecutionError:
        pass
    else:
        assert False, "expected OpenCLIExecutionError"

    monkeypatch.setattr(
        opencli_adapter.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "HTTP 429 Too Many Requests"),
    )
    with pytest.raises(opencli_adapter.OpenCLIRateLimitError):
        opencli_adapter.run_opencli("reddit", "staffing")

    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 60)

    monkeypatch.setattr(opencli_adapter.subprocess, "run", timed_out)
    try:
        opencli_adapter.run_opencli("reddit", "staffing")
    except opencli_adapter.OpenCLIExecutionError:
        pass
    else:
        assert False, "expected OpenCLIExecutionError"


@pytest.mark.parametrize(
    "stdout,stderr",
    [
        ("", "HTTP 429"),
        ("", "http 429"),
        ("429", ""),
        ("", "429"),
        ("", "too many requests"),
        ("", "Too Many Requests"),
        ("", "Error: 429 Too Many Requests"),
        ("", "status 429: rate limited"),
        ("error: HTTP 429", ""),
    ],
)
def test_run_opencli_rate_limit_positive_cases(monkeypatch, stdout, stderr):
    monkeypatch.setattr(
        opencli_adapter.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, stdout, stderr),
    )
    with pytest.raises(opencli_adapter.OpenCLIRateLimitError):
        opencli_adapter.run_opencli("reddit", "staffing")


@pytest.mark.parametrize(
    "stdout,stderr",
    [
        ("", "Error code 1429"),
        ("", "post_id_429abc failed"),
        ("processing post 4290", ""),
        ("", "4299 items remaining"),
        ("", "post_id 1429 not found"),
        ("item429", ""),
    ],
)
def test_run_opencli_rate_limit_negative_cases(monkeypatch, stdout, stderr):
    monkeypatch.setattr(
        opencli_adapter.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, stdout, stderr),
    )
    with pytest.raises(opencli_adapter.OpenCLIExecutionError) as exc_info:
        opencli_adapter.run_opencli("reddit", "staffing")
    assert not isinstance(exc_info.value, opencli_adapter.OpenCLIRateLimitError)


def test_run_opencli_uses_bounded_subprocess_settings(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, "[]", "")

    monkeypatch.setattr(opencli_adapter.subprocess, "run", fake_run)
    opencli_adapter.run_opencli("reddit", "q")
    assert captured["timeout"] == 60
    assert captured["check"] is False


def test_run_opencli_handles_missing_executable_empty_and_malformed(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("no opencli")

    monkeypatch.setattr(opencli_adapter.subprocess, "run", missing)
    try:
        opencli_adapter.run_opencli("reddit", "q")
    except opencli_adapter.OpenCLIExecutionError:
        pass
    else:
        assert False, "expected OpenCLIExecutionError"

    monkeypatch.setattr(
        opencli_adapter.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "", ""),
    )
    assert opencli_adapter.run_opencli("reddit", "q") == []

    monkeypatch.setattr(
        opencli_adapter.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "not json at all", ""),
    )
    assert opencli_adapter.run_opencli("reddit", "q") == []

    # Top-level object normalizes to single dict; non-dicts discarded.
    monkeypatch.setattr(
        opencli_adapter.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, '{"id":"solo"}', ""),
    )
    assert opencli_adapter.run_opencli("reddit", "q") == [{"id": "solo"}]


def test_fetch_leads_normalizes_recent_posts(monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(
        opencli_adapter,
        "run_opencli",
        lambda *args: [{"id": "post", "text": "Agency ATS pain", "url": "https://example.test", "created_at": now, "author": "Owner"}],
    )

    result = opencli_adapter.fetch_leads("reddit", ["ATS"], 24)
    assert result[0]["post_id"] == "post"
    assert result[0]["content"] == "Agency ATS pain"
    assert result[0]["posted_at"] == datetime.fromisoformat(now)
    assert result[0]["author"] == "Owner"


def test_fetch_leads_twitter_uses_platform_command_and_preserves_provenance(monkeypatch):
    captured = {}
    now = datetime.now(timezone.utc).isoformat()

    def fake_run(command, **kwargs):
        captured["command"] = command
        return subprocess.CompletedProcess(
            command,
            0,
            '{"id":"tweet-1","text":"Recruiter bottleneck","created_at":"%s"}' % now,
            "",
        )

    monkeypatch.setattr(opencli_adapter.subprocess, "run", fake_run)

    result = opencli_adapter.fetch_leads("twitter", "recruiter bottleneck")

    assert captured["command"] == [
        "opencli",
        "twitter",
        "search",
        "recruiter bottleneck",
        "--format",
        "json",
    ]
    assert "--subreddit" not in captured["command"]
    assert result[0]["platform"] == "twitter"
    assert result[0]["community"] is None


def test_fetch_leads_skips_non_dicts_and_uses_safe_defaults(monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(
        opencli_adapter,
        "run_opencli",
        lambda *args: [
            "not-a-dict",
            {"text": "no id here", "created_at": now},
            {"id": "ok", "created_at": now},  # no text/url/author -> safe defaults
            {"id": "user-obj", "text": "hi", "created_at": now, "user": {"name": "Founder"}},
            {"id": "old", "text": "old post", "created_at": "2000-01-01T00:00:00+00:00"},
        ],
    )
    result = opencli_adapter.fetch_leads("reddit", ["hi"], 24)
    by_id = {r["post_id"]: r for r in result}
    assert "ok" in by_id
    assert by_id["ok"]["content"] == ""
    assert by_id["ok"]["url"] is None
    assert by_id["ok"]["author"] is None
    assert by_id["user-obj"]["author"] == "Founder"
    assert "old" not in by_id


def test_fetch_leads_rejects_multiple_queries_in_a_list():
    with pytest.raises(ValueError, match="single query string"):
        opencli_adapter.fetch_leads("reddit", ["first query", "second query"])


def test_run_opencli_passes_unquoted_conversational_queries_directly(monkeypatch):
    captured = []
    opencli_adapter._SUBREDDIT_SCOPE_SUPPORTED = None

    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        output = "--subreddit [value]" if cmd[-1] == "--help" else "[]"
        return subprocess.CompletedProcess(cmd, 0, output, "")

    monkeypatch.setattr(opencli_adapter.subprocess, "run", fake_run)

    conversational_query = "recruitment agency getting clients"

    # Test Reddit invocation
    opencli_adapter.run_opencli("reddit", conversational_query, community="recruiting")
    assert captured[1] == [
        "opencli",
        "reddit",
        "search",
        conversational_query,
        "--sort",
        "new",
        "--subreddit",
        "recruiting",
        "--format",
        "json",
    ]
    assert '"' not in captured[1][3]
    assert "'" not in captured[1][3]
    assert " OR " not in captured[1][3]

    # Test Twitter invocation
    opencli_adapter.run_opencli("twitter", conversational_query, community=None)
    assert captured[2] == [
        "opencli",
        "twitter",
        "search",
        conversational_query,
        "--format",
        "json",
    ]
    assert "--subreddit" not in captured[2]
    assert '"' not in captured[2][3]
    assert "'" not in captured[2][3]
    assert " OR " not in captured[2][3]
