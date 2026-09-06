"""Strict qualification, redaction, retry, and provider-config acceptance tests."""

import json

from listening_loop import config
from listening_loop import qualification


def _valid_item(**overrides):
    item = {
        "id": "p1",
        "icp": "recruitment_agency",
        "author_role": "owner",
        "intent": "buying",
        "urgency": "now",
        "one_line": "Agency owner needs ATS help.",
        "icp_score": overrides.get("confidence", 0.8),
        "intent_score": overrides.get("confidence", 0.8),
    }
    if "confidence" in overrides:
        del overrides["confidence"]
    item.update(overrides)
    return item


def test_confidence_boundary_and_intent_matrix():
    assert qualification.validate_classification(_valid_item(confidence=0.60), {"p1"})["classifier_status"] == "qualified"
    assert qualification.validate_classification(_valid_item(confidence=0.59), {"p1"})["classifier_status"] == "not_qualified"
    
    # Low intent score gets rejected regardless of intent string
    out = qualification.validate_classification(_valid_item(icp_score=0.9, intent_score=0.4), {"p1"})
    assert out["classifier_status"] == "not_qualified"


def test_strict_response_validation_rejects_bad_shapes():
    ids = {"p1"}
    # Non-object item.
    assert qualification.validate_classification(["x"], ids)["classifier_error_category"] == "invalid_response"
    # Unknown id.
    assert qualification.validate_classification(_valid_item(id="nope"), ids)["classifier_error_category"] == "invalid_response"
    # Invalid enums.
    for field, bad in (("icp", "agency"), ("author_role", "ceo"), ("intent", "hiring"), ("urgency", "asap")):
        assert qualification.validate_classification(_valid_item(**{field: bad}), ids)["classifier_error_category"] == "invalid_response"
    # Bad confidence variants.
    for bad_conf in (True, -0.1, 1.5, "high", None):
        assert qualification.validate_classification(_valid_item(confidence=bad_conf), ids)["classifier_error_category"] == "invalid_response"
    # Missing one_line.
    assert qualification.validate_classification(_valid_item(one_line="  "), ids)["classifier_error_category"] == "invalid_response"


def test_duplicate_and_missing_results_are_unclassified():
    payload = {
        "choices": [{
            "message": {"content": json.dumps([
                _valid_item(id="a"), _valid_item(id="a"),
            ])}
        }]
    }
    out = qualification.parse_response(payload, {"a", "b"})
    assert out["a"]["classifier_status"] == "unclassified"
    assert out["a"]["classifier_error_category"] == "invalid_response"
    assert out["b"]["classifier_status"] == "unclassified"


def test_error_messages_bounded_and_redacted():
    long_msg = "x" * 1000
    out = qualification._failure("p1", "provider_error", "timeout", long_msg)
    assert len(out["classifier_error_message"]) <= config.ERROR_MESSAGE_LIMIT
    redacted = qualification._failure("p1", "provider_error", "timeout", "Bearer secret-key leaked")
    assert "secret-key" not in redacted["classifier_error_message"]
    assert qualification.sanitize_for_log("Authorization: Bearer abc") != "Authorization: Bearer abc" or "abc" not in qualification.sanitize_for_log("Authorization: Bearer abc")


def test_provider_diagnostics_never_include_secrets(monkeypatch):
    monkeypatch.setenv("CODEX_EVERYWHERE_API_KEY", "super-secret-value")
    monkeypatch.setenv("CODEX_EVERYWHERE_BASE_URL", "https://codex-easy.ai/v1")
    monkeypatch.setenv("CODEX_EVERYWHERE_MODEL", "gpt-5.6-luna")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    diag = qualification.get_provider_diagnostics()
    dumped = json.dumps(diag)
    assert "super-secret-value" not in dumped
    assert diag["provider"] == "codex-everywhere"
    assert diag["model"] == "gpt-5.6-luna"
    assert diag["api_key_var"] == "CODEX_EVERYWHERE_API_KEY"


def test_runtime_config_resolution_without_import_snapshot(monkeypatch):
    monkeypatch.setenv("CODEX_EVERYWHERE_BASE_URL", "https://codex-easy.ai/v1/")
    monkeypatch.setenv("CODEX_EVERYWHERE_MODEL", "gpt-5.6-luna")
    assert config.get_provider_base_url() == "https://codex-easy.ai/v1"
    assert config.get_provider_chat_url() == "https://codex-easy.ai/v1/chat/completions"
    assert config.get_provider_model() == "gpt-5.6-luna"
    summary = config.get_provider_config_summary()
    assert summary["base_url"] == "https://codex-easy.ai/v1"
    assert "api_key" not in json.dumps(summary).lower() or "CODEX_EVERYWHERE_API_KEY" in json.dumps(summary)


def test_retryable_categories_and_backoff_bounds():
    assert qualification.is_retryable_category("timeout")
    assert qualification.is_retryable_category("provider_http_error")
    assert qualification.is_retryable_category("invalid_response")
    assert not qualification.is_retryable_category(None)
    assert not qualification.is_retryable_category("not_qualified")
    assert qualification.retry_delay_seconds(1) == config.RETRY_BASE_DELAY_SECONDS
    assert qualification.retry_delay_seconds(100) <= config.RETRY_MAX_DELAY_SECONDS


def test_keyword_fallback_never_qualifies():
    post = {"post_id": "f1", "source": "reddit", "content": "agency needs ATS"}
    out = qualification.build_keyword_fallback(post)
    assert out["classifier_status"] == "unclassified"
    assert out["classifier_error_category"] == "provider_fallback"
    assert out["classifier_provider"] == "codex-everywhere"


def test_consecutive_failure_counter_and_fallback_gate(monkeypatch):
    monkeypatch.setattr(config, "MAX_CONSECUTIVE_PROVIDER_FAILURES", 2)
    qualification.reset_consecutive_failures()
    assert not qualification.should_use_keyword_fallback()
    qualification.record_provider_outcome(True)
    assert not qualification.should_use_keyword_fallback()
    qualification.record_provider_outcome(True)
    assert qualification.should_use_keyword_fallback()
    qualification.record_provider_outcome(False)
    assert not qualification.should_use_keyword_fallback()
