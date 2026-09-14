"""Strict qualification, ICP evaluation, noise pre-filtering, and provider tests."""

import json

from listening_loop import config
from listening_loop import qualification


def _valid_item(**overrides):
    item = {
        "id": "p1",
        "icp": "yes",
        "score": 0.85,
        "role": "founder",
        "problem": "client_acquisition",
        "intent": "pain",
        "reason": "Founder of recruitment agency facing BD challenges.",
    }
    item.update(overrides)
    return item


def test_icp_qualification_cases_a_through_f():
    # Case A: Clear ICP (Score >= 0.75 -> qualified)
    case_a = qualification.validate_classification(
        {
            "id": "case_a",
            "icp": "yes",
            "score": 0.88,
            "role": "Founder at ABC Technology Recruitment",
            "problem": "client_acquisition",
            "intent": "pain",
            "reason": "Bio confirms agency founder; client acquisition pain is relevant.",
        },
        {"case_a"},
    )
    assert case_a["classifier_status"] == "qualified"
    assert case_a["score"] == 0.88
    assert case_a["icp"] == "yes"

    # Case B: ICP but no buying signal (Proud of team -> qualified, intent=discussion or none)
    case_b = qualification.validate_classification(
        {
            "id": "case_b",
            "icp": "yes",
            "score": 0.90,
            "role": "Owner of XYZ Staffing",
            "problem": "none",
            "intent": "discussion",
            "reason": "Agency owner sharing milestone; no immediate commercial pain.",
        },
        {"case_b"},
    )
    assert case_b["classifier_status"] == "qualified"
    assert case_b["intent"] == "discussion"
    assert case_b["problem"] == "none"

    # Case C: Internal recruiter (Talent Acquisition Manager at Microsoft -> not_qualified)
    case_c = qualification.validate_classification(
        {
            "id": "case_c",
            "icp": "no",
            "score": 0.05,
            "role": "Talent Acquisition Manager at Microsoft",
            "problem": "candidate_sourcing",
            "intent": "pain",
            "reason": "Internal corporate recruiter/TA at Microsoft, not an agency operator.",
        },
        {"case_c"},
    )
    assert case_c["classifier_status"] == "not_qualified"
    assert case_c["icp"] == "no"

    # Case D: Job seeker (Looking for React dev role -> not_qualified)
    case_d = qualification.validate_classification(
        {
            "id": "case_d",
            "icp": "no",
            "score": 0.0,
            "role": "Job seeker",
            "problem": "none",
            "intent": "none",
            "reason": "Candidate seeking software engineering work.",
        },
        {"case_d"},
    )
    assert case_d["classifier_status"] == "not_qualified"

    # Case E: Insufficient evidence (Cold outreach isn't working, no bio -> uncertain -> needs_enrichment)
    case_e = qualification.validate_classification(
        {
            "id": "case_e",
            "icp": "uncertain",
            "score": 0.50,
            "role": "unknown",
            "problem": "outbound_bd",
            "intent": "pain",
            "reason": "Post discusses outbound, but author bio/background is unavailable.",
        },
        {"case_e"},
    )
    assert case_e["classifier_status"] == "needs_enrichment"
    assert case_e["icp"] == "uncertain"

    # Case F: Strong pain but wrong ICP (HR Director at manufacturing company -> not_qualified)
    case_f = qualification.validate_classification(
        {
            "id": "case_f",
            "icp": "no",
            "score": 0.05,
            "role": "HR Director at a manufacturing company",
            "problem": "ats_crm",
            "intent": "pain",
            "reason": "Internal HR director at manufacturing company, not a recruitment agency.",
        },
        {"case_f"},
    )
    assert case_f["classifier_status"] == "not_qualified"


def test_confidence_boundary_and_low_confidence_yes():
    # Score >= 0.75 -> qualified
    assert qualification.validate_classification(_valid_item(score=0.75), {"p1"})["classifier_status"] == "qualified"
    assert qualification.validate_classification(_valid_item(score=0.76), {"p1"})["classifier_status"] == "qualified"

    # Low-confidence yes (score < 0.75) -> needs_enrichment
    low_yes = qualification.validate_classification(_valid_item(score=0.74), {"p1"})
    assert low_yes["classifier_status"] == "needs_enrichment"

    # icp == "no" with any score -> not_qualified
    assert qualification.validate_classification(_valid_item(icp="no", score=0.9), {"p1"})["classifier_status"] == "not_qualified"


def test_deterministic_noise_prefilter():
    # Job seeker phrases filtered deterministically
    noisy_post = {
        "content": "Looking for a job as python backend engineer, please hire me.",
        "bio": "Passionate coder",
    }
    is_noise, reason = qualification.is_obvious_jobseeker_noise(noisy_post)
    assert is_noise is True
    assert "looking for a job" in reason

    # Agency founder mentioning hiring / resume tips is NOT filtered if bio confirms agency ownership
    agency_post = {
        "content": "Please review my resume tips for tech candidates.",
        "author_bio": "Founder at Apex Recruitment Agency",
    }
    is_noise, _ = qualification.is_obvious_jobseeker_noise(agency_post)
    assert is_noise is False


def test_compact_llm_payload():
    posts = [
        {
            "post_id": "t1",
            "source": "twitter",
            "author_bio": "Agency owner",
            "content": "BD outbound struggles.",
            "unnecessary_field": 12345,
            "likes": 50,
        }
    ]
    prompt_json = json.loads(qualification._prompt_posts(posts))
    assert len(prompt_json) == 1
    assert set(prompt_json[0].keys()) == {"id", "src", "bio", "text"}
    assert prompt_json[0]["id"] == "t1"
    assert prompt_json[0]["src"] == "twitter"
    assert prompt_json[0]["bio"] == "Agency owner"
    assert prompt_json[0]["text"] == "BD outbound struggles."


def test_strict_response_validation_rejects_bad_shapes():
    ids = {"p1"}
    # Non-object item.
    assert qualification.validate_classification(["x"], ids)["classifier_error_category"] == "invalid_response"
    # Unknown id.
    assert qualification.validate_classification(_valid_item(id="nope"), ids)["classifier_error_category"] == "invalid_response"
    # Invalid enums.
    for field, bad in (("icp", "maybe"), ("problem", "quantum_computing"), ("intent", "angry")):
        assert qualification.validate_classification(_valid_item(**{field: bad}), ids)["classifier_error_category"] == "invalid_response"
    # Bad score variants.
    for bad_score in (True, -0.1, 1.5, "high", None):
        assert qualification.validate_classification(_valid_item(score=bad_score), ids)["classifier_error_category"] == "invalid_response"


def test_duplicate_and_missing_results_are_classification_error():
    payload = {
        "choices": [{
            "message": {"content": json.dumps([
                _valid_item(id="a"), _valid_item(id="a"),
            ])}
        }]
    }
    out = qualification.parse_response(payload, {"a", "b"})
    assert out["a"]["classifier_status"] == "classification_error"
    assert out["a"]["classifier_error_category"] == "invalid_response"
    assert out["b"]["classifier_status"] == "classification_error"


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
    monkeypatch.setattr(config, "ensure_dotenv_loaded", lambda: None)
    monkeypatch.setenv("CODEX_EVERYWHERE_MODEL", "gpt-5.6-luna")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    import sys
    if "listening_loop.classifier" in sys.modules:
        monkeypatch.setattr(sys.modules["listening_loop.classifier"], "LLM_MODEL", "", raising=False)

    diag = qualification.get_provider_diagnostics()
    dumped = json.dumps(diag)
    assert "super-secret-value" not in dumped
    assert diag["provider"] == "codex-everywhere"
    assert diag["model"] == "gpt-5.6-luna"
    assert diag["api_key_var"] == "CODEX_EVERYWHERE_API_KEY"


def test_retryable_categories_and_backoff_bounds():
    assert qualification.is_retryable_category("timeout")
    assert qualification.is_retryable_category("provider_http_error")
    assert qualification.is_retryable_category("invalid_response")
    assert qualification.is_retryable_category("classification_error")
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
