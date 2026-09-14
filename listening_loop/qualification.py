"""Strict ICP qualification (Stage 2: LLM).

Given social posts/leads scraped from Twitter/X, Reddit, Facebook, etc.,
determine whether the AUTHOR belongs to the RecruitmentOS ICP.

ICP Definition:
- People who own, lead, operate, or independently work in a recruitment/staffing/executive-search/headhunting agency.
- Roles: founder, owner, partner, principal, managing director, agency director, independent recruiter/headhunter, or senior agency recruiter involved in BD.
- NOT ICP: job seekers, candidates, internal recruiters/TA/HR, employers/hiring managers, developers, career coaches, generic agencies, unrelated freelancers.
- Rule: Recruitment-related content alone does NOT prove ICP. If evidence is insufficient, use "uncertain".

Classification statuses:
- qualified: icp == "yes" and score >= 0.75
- needs_enrichment: icp == "uncertain" or (icp == "yes" and score < 0.75)
- not_qualified: icp == "no" or other non-qualifying
- classification_error / provider_error: network/provider/formatting failures (retryable)
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

ICP_VALUES = {"yes", "no", "uncertain"}
PROBLEM_VALUES = {
    "client_acquisition",
    "outbound_bd",
    "lead_gen",
    "candidate_sourcing",
    "matching",
    "ats_crm",
    "automation",
    "operations",
    "other",
    "none",
}
INTENT_VALUES = {
    "buying",
    "solution_seeking",
    "pain",
    "advice",
    "discussion",
    "none",
}
INTENT_PRIORITY = config.INTENT_PRIORITY
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


def is_obvious_jobseeker_noise(post: dict) -> tuple[bool, str]:
    """Conservative noise filter: obvious job seekers / resume review without agency ownership signals."""
    content = (post.get("content") or post.get("text") or "").lower()
    bio = (post.get("author_bio") or post.get("bio") or post.get("author_description") or "").lower()

    # Check if bio has strong agency ownership signals - if so, do NOT filter out deterministically
    agency_owner_signals = (
        "recruitment agency",
        "staffing agency",
        "executive search",
        "search firm",
        "headhunting",
        "founder",
        "owner",
        "partner",
        "managing director",
        "agency director",
    )
    if any(sig in bio for sig in agency_owner_signals):
        return False, ""

    for kw in getattr(config, "OBVIOUS_NOISE_KEYWORDS", ()):
        if kw in content or kw in bio:
            return True, f"Deterministic pre-filter: obvious job seeker/resume review ('{kw}')"

    return False, ""


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
    # Prefer config.get_provider_model() when env or default is set
    cfg_model = config.get_provider_model()
    if cfg_model and cfg_model != config.CODEX_EVERYWHERE_MODEL_DEFAULT:
        return cfg_model
    override = globals().get("LLM_MODEL") or ""
    if isinstance(override, str) and override.strip() and override.strip() != config.CODEX_EVERYWHERE_MODEL_DEFAULT:
        return override.strip()
    try:
        import sys as _sys

        _classifier = _sys.modules.get("listening_loop.classifier")
        _c_override = getattr(_classifier, "LLM_MODEL", "") if _classifier else ""
        if isinstance(_c_override, str) and _c_override.strip() and _c_override.strip() != config.CODEX_EVERYWHERE_MODEL_DEFAULT:
            return _c_override.strip()
    except Exception:
        pass
    return cfg_model


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
    return {"Authorization": "Bearer " + key, "Content-Type": "application/json"}


def _prompt_posts(posts: list[dict]) -> str:
    """Minimize payload sent to LLM for classification (id, src, bio, text)."""
    compact_posts = []
    max_len = getattr(config, "MAX_POST_CONTENT_LENGTH", 1000)
    for post in posts:
        pid = str(post.get("post_id") or post.get("id") or "")
        src = str(post.get("source") or post.get("src") or "")
        bio = str(post.get("author_bio") or post.get("bio") or post.get("author_description") or "")[:500]
        text = str(post.get("content") or post.get("text") or "")[:max_len]
        compact = {
            "id": pid,
            "src": src,
            "bio": bio,
            "text": text,
        }
        compact_posts.append(compact)
    return json.dumps(compact_posts, ensure_ascii=True, separators=(",", ":"))


SYSTEM_PROMPT = """You classify social authors for RecruitmentOS.

ICP = people who own, lead, operate, or independently work in a recruitment/staffing/executive-search/headhunting agency.

ICP roles: founder, owner, partner, principal, managing director, agency director, independent recruiter/headhunter, or senior agency recruiter involved in BD.

NOT ICP: job seekers, candidates, internal recruiters/TA/HR, employers/hiring managers, developers, career coaches, generic agencies, unrelated freelancers.

Recruitment-related content alone does NOT prove ICP. If evidence is insufficient, use "uncertain".

Also extract useful commercial signals when present.

Return ONLY JSON:
[
 {
  "id":"",
  "icp":"yes|no|uncertain",
  "score":0.0,
  "role":"",
  "problem":"client_acquisition|outbound_bd|lead_gen|candidate_sourcing|matching|ats_crm|automation|operations|other|none",
  "intent":"buying|solution_seeking|pain|advice|discussion|none",
  "reason":""
 }
]

score = confidence that the AUTHOR belongs to the RecruitmentOS ICP.

Never invent information."""


def validate_classification(raw: Any, expected_ids: set[str]) -> dict:
    """Deterministic qualification logic based strictly on author ICP membership."""
    if not isinstance(raw, dict):
        return _failure("", "classification_error", "invalid_response", "classification item is not an object")

    post_id = raw.get("id")
    if not isinstance(post_id, str) or post_id not in expected_ids:
        return _failure(str(post_id or ""), "classification_error", "invalid_response", "unknown or missing post id")

    icp = raw.get("icp")
    if icp not in ICP_VALUES:
        return _failure(post_id, "classification_error", "invalid_response", f"invalid icp: {icp}")

    score = raw.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not (0 <= float(score) <= 1):
        return _failure(post_id, "classification_error", "invalid_response", f"invalid score: {score}")
    score = float(score)

    role = raw.get("role")
    if not isinstance(role, str):
        role = str(role or "")

    problem = raw.get("problem")
    if problem not in PROBLEM_VALUES:
        if isinstance(problem, str) and problem.lower() in PROBLEM_VALUES:
            problem = problem.lower()
        else:
            return _failure(post_id, "classification_error", "invalid_response", f"invalid problem: {problem}")

    intent = raw.get("intent")
    if intent not in INTENT_VALUES:
        if isinstance(intent, str) and intent.lower() in INTENT_VALUES:
            intent = intent.lower()
        else:
            return _failure(post_id, "classification_error", "invalid_response", f"invalid intent: {intent}")

    reason = raw.get("reason")
    if not isinstance(reason, str):
        reason = str(reason or "")

    # Qualification Gate:
    # if icp == "yes" and score >= 0.75: qualified
    # elif icp == "uncertain" or (icp == "yes" and score < 0.75): needs_enrichment
    # else: not_qualified
    threshold = getattr(config, "CONFIDENCE_THRESHOLD", 0.75)
    if icp == "yes" and score >= threshold:
        status = "qualified"
        rejection_reason = None
    elif icp == "uncertain" or (icp == "yes" and score < threshold):
        status = "needs_enrichment"
        rejection_reason = (
            f"insufficient_evidence (icp={icp}, score={score:.2f})"
            if icp == "uncertain"
            else f"low_confidence_yes (score={score:.2f} < {threshold:.2f})"
        )
    else:
        status = "not_qualified"
        rejection_reason = reason if reason else f"not_icp (icp={icp}, score={score:.2f})"

    priority = INTENT_PRIORITY.get(intent, 1)

    result = {
        "post_id": post_id,
        "classifier_status": status,
        "icp": icp,
        "score": score,
        "confidence": score,  # backwards compatibility
        "icp_score": score,   # backwards compatibility
        "intent_score": priority / 5.0,  # backwards compatibility
        "author_role": role,
        "role": role,
        "problem": problem,
        "intent_type": intent,
        "intent": intent,
        "urgency": "now" if intent in ("buying", "pain") else ("soon" if intent in ("solution_seeking", "advice") else "later"),
        "reason": reason[:1000],
        "one_line": reason[:1000],
        "summary": reason[:1000],
        "lead_priority": priority,
        "rejection_reason": rejection_reason,
        "classifier_error_category": None,
        "classifier_error_message": None,
    }
    return result


def parse_response(payload: Any, expected_ids: set[str]) -> dict[str, dict]:
    """Parse and validate LLM completion response."""
    try:
        if isinstance(payload, str):
            text = payload.strip()
            if "data: [DONE]" in text:
                text = text.split("data: [DONE]")[0].strip()
            payload = json.loads(text)

        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            if "data" in payload and isinstance(payload["data"], dict) and "choices" in payload["data"]:
                choices = payload["data"]["choices"]
            elif "choices" in payload:
                choices = payload["choices"]
            else:
                raise ValueError("Response payload does not contain choices array")

            content = choices[0]["message"]["content"]
            if isinstance(content, str):
                content = content.strip()
                # Strip markdown JSON fences if present
                if content.startswith("```"):
                    lines = content.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    content = "\n".join(lines).strip()
                try:
                    items = json.loads(content)
                except json.JSONDecodeError:
                    match = re.search(r"\[.*\]", content, re.DOTALL)
                    if match:
                        items = json.loads(match.group(0))
                    else:
                        raise
            elif isinstance(content, list):
                items = content
            else:
                raise ValueError("Unexpected message content format")
        else:
            raise ValueError("Unexpected payload format")

        if not isinstance(items, list):
            raise ValueError("Response content is not an array")
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {post_id: _failure(post_id, "classification_error", "invalid_response", exc) for post_id in expected_ids}

    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            return {
                post_id: _failure(post_id, "classification_error", "invalid_response", "batch id mismatch: non-object item")
                for post_id in expected_ids
            }
        pid = str(item.get("id") or "")
        if not pid or pid not in expected_ids or pid in seen:
            if pid in seen:
                reason = f"duplicate classification result for id {pid}"
            else:
                reason = f"unknown or missing post id: {pid}"
            return {
                post_id: _failure(post_id, "classification_error", "invalid_response", "batch id mismatch: " + reason)
                for post_id in expected_ids
            }
        seen.add(pid)

    if set(seen) != set(expected_ids):
        return {
            post_id: _failure(post_id, "classification_error", "invalid_response", "batch id mismatch: set mismatch")
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
        results.setdefault(post_id, _failure(post_id, "classification_error", "invalid_response", "missing classification result"))

    return results


def is_retryable_category(category: str | None) -> bool:
    """provider_error outcomes and malformed rows get bounded retries."""
    return category in {
        "missing_configuration",
        "timeout",
        "network",
        "provider_http_error",
        "provider_error",
        "invalid_response",
        "provider_fallback",
        "classification_error",
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
    expected_ids = {str(post.get("post_id") or post.get("id")) for post in posts}
    url = _provider_url()
    if not url:
        return {
            post_id: _failure(post_id, "provider_error", "missing_configuration", "provider base URL is not configured")
            for post_id in expected_ids
        }
    if not _runtime_api_key():
        return {
            post_id: _failure(post_id, "provider_error", "missing_configuration", config.CODEX_API_KEY_VAR + " is not configured")
            for post_id in expected_ids
        }

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
        text = response.text.strip()
        if "data: [DONE]" in text:
            text = text.split("data: [DONE]")[0].strip()
        payload = json.loads(text)
        return parse_response(payload, expected_ids)
    except (ValueError, json.JSONDecodeError) as exc:
        return {post_id: _failure(post_id, "classification_error", "invalid_response", exc) for post_id in expected_ids}


def classify_posts(posts: list[dict]) -> list[dict]:
    """Return one durable classifier outcome for every submitted post."""
    results = []
    batch_size = getattr(config, "INTENT_BATCH_SIZE", 25)
    for start in range(0, len(posts), batch_size):
        batch = posts[start : start + batch_size]
        outcomes = _request_batch(batch)
        batch_had_provider_error = False
        for post in batch:
            pid = str(post.get("post_id") or post.get("id"))
            outcome = outcomes.get(pid) or _failure(pid, "classification_error", "invalid_response", "missing outcome")
            if outcome.get("classifier_status") in ("provider_error", "classification_error"):
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
