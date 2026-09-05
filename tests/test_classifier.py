import requests

from listening_loop import classifier
from listening_loop import qualification


def post(post_id="post-1", **overrides):
    result = {
        "post_id": post_id,
        "source": "reddit",
        "content": "I own a staffing agency and need a better ATS matching workflow.",
        "url": "https://example.test/" + post_id,
        "posted_at": "2026-09-05T10:00:00+00:00",
    }
    result.update(overrides)
    return result


def classification(post_id="post-1", **overrides):
    result = {
        "id": post_id,
        "icp": "recruitment_agency",
        "author_role": "owner",
        "intent": "buying",
        "urgency": "now",
        "one_line": "Agency owner wants ATS matching support.",
        "confidence": 0.8,
    }
    result.update(overrides)
    return result


def _provider_env(monkeypatch, base="https://codex-easy.ai/v1"):
    monkeypatch.setenv("CODEX_EVERYWHERE_BASE_URL", base)
    monkeypatch.setenv("CODEX_EVERYWHERE_API_KEY", "test-key")
    monkeypatch.setenv("CODEX_EVERYWHERE_MODEL", "gpt-5.6-luna")
    monkeypatch.setattr(qualification, "LLM_BASE_URL", "")
    monkeypatch.setattr(qualification, "LLM_MODEL", "")
    monkeypatch.setattr(classifier, "LLM_BASE_URL", "")
    monkeypatch.setattr(classifier, "LLM_MODEL", "")


def test_qualified_icp_post_is_enriched_and_qualifies():
    result = classifier.validate_classification(classification(), {"post-1"})

    assert result["classifier_status"] == "qualified"
    assert result["intent_type"] == "buying"
    assert result["one_line"] == "Agency owner wants ATS matching support."
    assert result["summary"] == "Agency owner wants ATS matching support."


def test_all_qualifying_roles_qualify_with_allowed_icp_intent():
    for role in ("owner", "founder", "principal", "headhunter", "independent_recruiter"):
        for icp in ("recruitment_agency", "independent_recruiter"):
            for intent in ("buying", "pain"):
                out = classifier.validate_classification(
                    classification(author_role=role, icp=icp, intent=intent, confidence=0.6),
                    {"post-1"},
                )
                assert out["classifier_status"] == "qualified", (role, icp, intent)


def test_strict_unknown_role_rejection():
    out = classifier.validate_classification(
        classification(author_role="unknown", icp="recruitment_agency", intent="buying", confidence=0.95),
        {"post-1"},
    )
    assert out["classifier_status"] == "not_qualified"


def test_job_seekers_direct_employers_and_advice_threads_are_not_qualified():
    for output in (
        classification(icp="not_icp", author_role="job_seeker"),
        classification(icp="not_icp", author_role="employer", intent="buying"),
        classification(icp="not_icp", author_role="internal_recruiter", intent="advice"),
        classification(icp="recruitment_agency", author_role="developer", intent="buying", confidence=0.9),
        classification(icp="recruitment_agency", author_role="freelancer", intent="pain", confidence=0.9),
        classification(icp="recruitment_agency", author_role="owner", intent="advice", confidence=0.9),
        classification(icp="recruitment_agency", author_role="owner", intent="job_search", confidence=0.9),
        classification(icp="recruitment_agency", author_role="owner", intent="buying", confidence=0.59),
        classification(icp="not_icp", author_role="owner", intent="buying", confidence=0.9),
    ):
        assert classifier.validate_classification(output, {"post-1"})["classifier_status"] == "not_qualified"


def test_malformed_provider_response_is_unclassified():
    result = classifier.parse_response({"choices": [{"message": {"content": "not-json"}}]}, {"post-1"})

    assert result["post-1"]["classifier_status"] == "unclassified"
    assert result["post-1"]["classifier_error_category"] == "invalid_response"


def test_invalid_json_body_is_unclassified(monkeypatch):
    _provider_env(monkeypatch)
    monkeypatch.setattr(classifier, "LLM_BASE_URL", "https://luna.example.test/v1/chat/completions")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(classifier.requests, "post", lambda *args, **kwargs: Response())
    result = classifier.classify_posts([post()])[0]

    assert result["classifier_status"] == "unclassified"
    assert result["classifier_error_category"] == "invalid_response"


def test_provider_failure_is_retained_for_each_post(monkeypatch):
    _provider_env(monkeypatch)
    monkeypatch.setattr(classifier, "LLM_BASE_URL", "https://luna.example.test/v1/chat/completions")

    def raise_timeout(*args, **kwargs):
        raise requests.Timeout("timed out")

    monkeypatch.setattr(classifier.requests, "post", raise_timeout)
    results = classifier.classify_posts([post("one"), post("two")])

    assert {row["post_id"] for row in results} == {"one", "two"}
    assert {row["classifier_status"] for row in results} == {"provider_error"}
    assert {row["classifier_error_category"] for row in results} == {"timeout"}


def test_provider_payload_uses_codex_model_default_and_bounded_content(monkeypatch):
    _provider_env(monkeypatch)
    captured = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": '[{"id":"post-1","icp":"recruitment_agency","author_role":"owner","intent":"pain","urgency":"soon","one_line":"Agency sourcing pain.","confidence":0.7}]'}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(qualification.requests, "post", fake_post)
    results = classifier.classify_posts([post(content="x" * 10000)])

    assert captured["url"] == "https://codex-easy.ai/v1/chat/completions"
    assert captured["json"]["model"] == "gpt-5.6-luna"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert len(captured["json"]["messages"][1]["content"]) < 7000
    assert results[0]["classifier_status"] == "qualified"
    assert results[0]["classifier_provider"] == "codex-everywhere"


def test_missing_api_key_is_provider_error(monkeypatch):
    monkeypatch.setenv("CODEX_EVERYWHERE_BASE_URL", "https://codex-easy.ai/v1")
    monkeypatch.setenv("CODEX_EVERYWHERE_MODEL", "gpt-5.6-luna")
    monkeypatch.delenv("CODEX_EVERYWHERE_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(qualification, "LLM_BASE_URL", "")
    monkeypatch.setattr(qualification, "LLM_MODEL", "")
    monkeypatch.setattr(classifier, "LLM_BASE_URL", "")
    monkeypatch.setattr(classifier, "LLM_MODEL", "")

    result = classifier.classify_posts([post()])[0]
    assert result["classifier_status"] == "provider_error"
    assert result["classifier_error_category"] == "missing_configuration"
