import subprocess
from datetime import datetime, timezone

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
    assert opencli_adapter.run_opencli("reddit", "staffing") == []

    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 60)

    monkeypatch.setattr(opencli_adapter.subprocess, "run", timed_out)
    assert opencli_adapter.run_opencli("reddit", "staffing") == []


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
    assert opencli_adapter.run_opencli("reddit", "q") == []

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
