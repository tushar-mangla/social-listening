"""Strict two-stage ICP qualification (Stage 2: LLM).

Stage 1 (keyword pre-filter) lives in ``listening_loop.run``.
This module implements Stage 2: bounded OpenAI-compatible chat-completions
requests to the verified Codex Everywhere gateway, strict JSON validation,
and sanitized diagnostics.

Provider (non-secret):
- Base URL default: https://codex-easy.ai/v1
- Model default: gpt-5.6-luna (label: codex-everywhere)
- API key variable: CODEX_EVERYWHERE_API_KEY (from .env at runtime)

Never log API keys, authorization headers, query-string credentials,
full post content, or full prompts.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

from listening_loop import config

# Backward-compatible module attributes (introspection only; functional path
# reads runtime environment via config getters so tests can inject with setenv).
LLM_BASE_URL = ""
LLM_MODEL = config.CODEX_EVERYWHERE_MODEL_DEFAULT
INTENT_BATCH_SIZE = config.INTENT_BATCH_SIZE
LLM_TIMEOUT_SECONDS = config.LLM_TIMEOUT_SECONDS
MAX_POST_CONTENT_LENGTH = config.MAX_POST_CONTENT_LENGTH
ERROR_MESSAGE_LIMIT = config.ERROR_MESSAGE_LIMIT

ICP_VALUES = {"recruitment_agency", "independent_recruiter", "not_icp"}
AUTHOR_ROLE_VALUES = {
    "owner",
    "founder",
    "principal",
    "headhunter",
    "independent_recruiter",
    "job_seeker",
    "internal_recruiter",
    "hr_generalist",
    "developer",
    "employer",
    "freelancer",
    "unknown",
    "other",
}
INTENT_VALUES = {"buying", "pain", "advice", "job_search", "other"}
URGENCY_VALUES = {"now", "soon", "later", "unknown"}
# Strict ICP: unknown is NEVER qualifying.
QUALIFYING_ROLES = {"owner", "founder", "principal", "headhunter", "independent_recruiter"}
QUALIFYING_ICPS = {"recruitment_agency", "independent_recruiter"}
QUALIFYING_INTENTS = {"buying", "pain"}
CONFIDENCE_THRESHOLD = config.CONFIDENCE_THRESHOLD

PROVIDER_LABEL = config.CODEX_EVERYWHERE_PROVIDER_LABEL

# Consecutive provider-failure tracking for graceful degradation.
_consecutive_provider_failures = 0


def reset_consecutive_failures() -> None:
    global _consecutive_provider_failures
    _consecutive_provider_failures = 0


def record_provider_outcome(had_provider_error: bool) -> int:
    """Update the consecutive-failure counter; return the new count."""
    global _consecutive_provider_failures
    if had_provider_error:
        _consecutive_provider_failures += 1
    else:
        _consecutive_provider_failures = 0
    return _consecutive_provider_failures


def should_use_keyword_fallback() -> bool:
    return _consecutive_provider_failures >= config.MAX_CONSECUTIVE_PROVIDER_FAILURES


def _bounded_error(value: object) -> str:
    """Bounded, credential-free diagnostic (canonical sanitizer)."""
    return sanitize_error_message(value)


def sanitize_error_message(value: object, limit: int | None = None) -> str:
    """Canonical sanitizer for error diagnostics.

    Used before ANY error logging or SQLite error-message persistence:
    - Case-insensitively redacts Authorization header credentials
      (``Bearer ...`` and ``Basic ...`` token material).
    - Case-insensitively redacts URL query-string credentials
      (``token``, ``key``, ``api_key``, ``apikey``, ``access_token``,
      ``secret``).
    - Bounds output to a concise, safe description. Callers must never
      pass full raw post content, raw prompt bodies, or full stderr here;
      only concise exception/diagnostic descriptions should be supplied.
    """
    cap = limit if limit is not None else config.ERROR_MESSAGE_LIMIT
    text = str(value).replace("\n", " ").replace("\r", " ")
    text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/=]+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)\bBasic\s+[A-Za-z0-9\-._~+/=]+", "Basic [REDACTED]", text)
    text = re.sub(
        r"(?i)([?&](?:token|key|api_key|apikey|access_token|secret)=)[^&\s]+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)\b(api_key|apikey|access_token|secret|token)\s*[:=]\s*[^\s&;,]+",
        r"\1=[REDACTED]",
        text,
    )
    return text[:cap]


def sanitize_for_log(value: object, max_chars: int = 120) -> str:
    """Return a short, credential-free snippet safe for logs."""
    return sanitize_error_message(value)[:max_chars]


def _failure(post_id: str, status: str, category: str, message: object) -> dict:
    return {
        "post_id": post_id,
        "classifier_status": status,
        "classifier_error_category": category,
        "classifier_error_message": _bounded_error(message),
    }


def _runtime_base_url() -> str:
    """Resolve base URL at call time (env injection friendly, no import snapshot)."""
    override = globals().get("LLM_BASE_URL") or ""
    if isinstance(override, str) and override.strip():
        return override.strip().rstrip("/")
    # Test-compat: allow injection via classifier shim namespace.
    try:
        import sys as _sys

        _classifier = _sys.modules.get("listening_loop.classifier")
        _c_override = getattr(_classifier, "LLM_BASE_URL", "") if _classifier else ""
        if isinstance(_c_override, str) and _c_override.strip():
            return _c_override.strip().rstrip("/")
    except Exception:
        pass
    return config.get_provider_base_url()


def _runtime_model() -> str:
    override = globals().get("LLM_MODEL") or ""
    if isinstance(override, str) and override.strip():
        return override.strip()
    try:
        import sys as _sys

        _classifier = _sys.modules.get("listening_loop.classifier")
        _c_override = getattr(_classifier, "LLM_MODEL", "") if _classifier else ""
        if isinstance(_c_override, str) and _c_override.strip():
            return _c_override.strip()
    except Exception:
        pass
    return config.get_provider_model()


def _runtime_api_key() -> str:
    return config.get_provider_api_key()


def _provider_url() -> str:
    """Return the chat-completions endpoint URL (legacy full-URL tolerant)."""
    raw = _runtime_base_url()
    if not raw:
        return ""
    if raw.rstrip("/").endswith("/chat/completions"):
        return raw.rstrip("/")
    return raw.rstrip("/") + "/chat/completions"


def _provider_headers() -> dict:
    key = _runtime_api_key()
    if not key:
        return {}
    return {"Authorization": "Bearer " + key}


def _prompt_posts(posts: list[dict]) -> str:
    compact_posts = [
        {
            "id": str(post["post_id"]),
            "source": post.get("source", ""),
            "content": (post.get("content") or "")[:MAX_POST_CONTENT_LENGTH],
        }
        for post in posts
    ]
    return json.dumps(compact_posts, ensure_ascii=True, separators=(",", ":"))


SYSTEM_PROMPT = """Classify each social post as RecruitmentOS lead evidence. Return only a JSON array.
Each item must be {"id","icp","author_role","intent","urgency","one_line","confidence"}.
icp: recruitment_agency, independent_recruiter, or not_icp.
author_role: owner, founder, principal, headhunter, independent_recruiter, job_seeker, internal_recruiter, hr_generalist, developer, employer, freelancer, unknown, or other.
intent: buying, pain, advice, job_search, or other. urgency: now, soon, later, or unknown.
An ICP is ONLY a recruitment/staffing agency founder, owner, principal, headhunter, or independent recruiter discussing BD/client acquisition, candidate sourcing, ATS/matching, or recruitment automation.
EXCLUDE all of: job seekers, resume advice, internal HR/talent acquisition hiring directly, developers, generic agencies without recruitment-agency evidence, freelancers, employers, and unrelated users.
author_role unknown is NOT qualified and must be classified as not_qualified (never qualified). confidence is 0..1; only >= 0.60 with buying/pain intent can qualify."""


def validate_classification(raw: Any, expected_ids: set[str]) -> dict:
    if not isinstance(raw, dict):
        return _failure("", "unclassified", "invalid_response", "classification item is not an object")

    post_id = raw.get("id")
    if not isinstance(post_id, str) or post_id not in expected_ids:
        return _failure(str(post_id or ""), "unclassified", "invalid_response", "unknown or missing post id")

    required_values = {
        "icp": ICP_VALUES,
        "author_role": AUTHOR_ROLE_VALUES,
        "intent": INTENT_VALUES,
        "urgency": URGENCY_VALUES,
    }
    for field, allowed in required_values.items():
        if raw.get(field) not in allowed:
            return _failure(post_id, "unclassified", "invalid_response", "invalid " + field)

    confidence = raw.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        return _failure(post_id, "unclassified", "invalid_response", "invalid confidence")
    one_line = raw.get("one_line")
    if not isinstance(one_line, str) or not one_line.strip():
        return _failure(post_id, "unclassified", "invalid_response", "missing one_line")

    result = {
        "post_id": post_id,
        "icp": raw["icp"],
        "author_role": raw["author_role"],
        "intent_type": raw["intent"],
        "urgency": raw["urgency"],
        "one_line": one_line.strip()[:1000],
        "summary": one_line.strip()[:1000],
        "confidence": float(confidence),
        "classifier_error_category": None,
        "classifier_error_message": None,
    }
    result["classifier_status"] = (
        "qualified"
        if raw["author_role"] in QUALIFYING_ROLES
        and raw["icp"] in QUALIFYING_ICPS
        and raw["intent"] in QUALIFYING_INTENTS
        and float(confidence) >= CONFIDENCE_THRESHOLD
        else "not_qualified"
    )
    return result


def parse_response(payload: Any, expected_ids: set[str]) -> dict[str, dict]:
    try:
        content = payload["choices"][0]["message"]["content"]
        items = json.loads(content)
        if not isinstance(items, list):
            raise ValueError("response content is not an array")
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {post_id: _failure(post_id, "unclassified", "invalid_response", exc) for post_id in expected_ids}

    seen: set[str] = set()
    for item in items:
        # Strict batch ID correlation: any non-object, unknown ID, or
        # duplicate ID invalidates the entire batch.
        if not isinstance(item, dict):
            return {
                post_id: _failure(post_id, "unclassified", "invalid_response", "batch id mismatch: non-object item")
                for post_id in expected_ids
            }
        pid = item.get("id")
        if not isinstance(pid, str) or pid not in expected_ids or pid in seen:
            if isinstance(pid, str) and pid in seen:
                reason = "duplicate classification result"
            else:
                reason = "unknown or missing post id"
            return {
                post_id: _failure(post_id, "unclassified", "invalid_response", "batch id mismatch: " + reason)
                for post_id in expected_ids
            }
        seen.add(pid)
    if set(seen) != set(expected_ids):
        return {
            post_id: _failure(post_id, "unclassified", "invalid_response", "batch id mismatch: set mismatch")
            for post_id in expected_ids
        }
    results: dict[str, dict] = {}
    for item in items:
        result = validate_classification(item, expected_ids)
        pid = result.get("post_id") or ""
        if not pid:
            continue
        results[pid] = result
    for post_id in expected_ids:
        results.setdefault(post_id, _failure(post_id, "unclassified", "invalid_response", "missing classification result"))
    return results


def is_retryable_category(category: str | None) -> bool:
    """provider_error outcomes are retryable; unclassified malformed rows get bounded retries."""
    return category in {
        "missing_configuration",
        "timeout",
        "network",
        "provider_http_error",
        "provider_error",
        "invalid_response",
        "provider_fallback",
    }


def retry_delay_seconds(attempts: int) -> int:
    """Exponential backoff bounded by config limits."""
    base = config.RETRY_BASE_DELAY_SECONDS
    cap = config.RETRY_MAX_DELAY_SECONDS
    delay = base * (2 ** max(0, attempts - 1))
    return max(base, min(cap, delay))


def build_keyword_fallback(post: dict, reason: str = "provider fallback after consecutive failures") -> dict:
    """Keyword-only fallback outcome: never qualified, bounded diagnostic."""
    outcome = {
        **post,
        "post_id": str(post.get("post_id", "")),
        "classifier_status": "unclassified",
        "classifier_error_category": "provider_fallback",
        "classifier_error_message": _bounded_error(reason),
        "classifier_provider": PROVIDER_LABEL,
    }
    return outcome


def _request_batch(posts: list[dict]) -> dict[str, dict]:
    expected_ids = {str(post["post_id"]) for post in posts}
    url = _provider_url()
    if not url:
        for post_id in expected_ids:
            pass
        return {post_id: _failure(post_id, "provider_error", "missing_configuration", "provider base URL is not configured") for post_id in expected_ids}
    if not _runtime_api_key():
        return {post_id: _failure(post_id, "provider_error", "missing_configuration", config.CODEX_API_KEY_VAR + " is not configured") for post_id in expected_ids}

    try:
        response = requests.post(
            url,
            headers=_provider_headers(),
            json={
                "model": _runtime_model(),
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": _prompt_posts(posts)},
                ],
            },
            timeout=LLM_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.Timeout as exc:
        return {post_id: _failure(post_id, "provider_error", "timeout", exc) for post_id in expected_ids}
    except requests.ConnectionError as exc:
        return {post_id: _failure(post_id, "provider_error", "network", exc) for post_id in expected_ids}
    except requests.HTTPError as exc:
        return {post_id: _failure(post_id, "provider_error", "provider_http_error", exc) for post_id in expected_ids}
    except (ValueError, json.JSONDecodeError) as exc:
        return {post_id: _failure(post_id, "provider_error", "invalid_response", exc) for post_id in expected_ids}
    except requests.RequestException as exc:
        return {post_id: _failure(post_id, "provider_error", "provider_error", exc) for post_id in expected_ids}

    try:
        return parse_response(response.json(), expected_ids)
    except (ValueError, json.JSONDecodeError) as exc:
        return {post_id: _failure(post_id, "unclassified", "invalid_response", exc) for post_id in expected_ids}


def classify_posts(posts: list[dict]) -> list[dict]:
    """Return one durable classifier outcome for every submitted post."""
    results = []
    for start in range(0, len(posts), INTENT_BATCH_SIZE):
        batch = posts[start:start + INTENT_BATCH_SIZE]
        outcomes = _request_batch(batch)
        batch_had_provider_error = False
        for post in batch:
            outcome = outcomes[str(post["post_id"])]
            if outcome.get("classifier_status") == "provider_error":
                batch_had_provider_error = True
            results.append({**post, **outcome, "classifier_provider": PROVIDER_LABEL})
        record_provider_outcome(batch_had_provider_error)
    return results


def get_provider_diagnostics() -> dict:
    """Non-secret diagnostics safe for logs (never includes the API key)."""
    summary = config.get_provider_config_summary()
    summary["consecutive_provider_failures"] = _consecutive_provider_failures
    summary["keyword_fallback_active"] = should_use_keyword_fallback()
    return summary
