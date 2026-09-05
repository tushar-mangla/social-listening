"""Backward-compatible shim: canonical implementation lives in qualification.py."""

import requests  # noqa: F401  (re-exported so tests can monkeypatch classifier.requests)

from listening_loop.qualification import (  # noqa: F401
    AUTHOR_ROLE_VALUES,
    CONFIDENCE_THRESHOLD,
    ERROR_MESSAGE_LIMIT,
    ICP_VALUES,
    INTENT_BATCH_SIZE,
    INTENT_VALUES,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
    MAX_POST_CONTENT_LENGTH,
    QUALIFYING_INTENTS,
    QUALIFYING_ROLES,
    SYSTEM_PROMPT,
    URGENCY_VALUES,
    _bounded_error,
    _failure,
    _prompt_posts,
    _provider_url,
    _request_batch,
    build_keyword_fallback,
    classify_posts,
    is_retryable_category,
    parse_response,
    retry_delay_seconds,
    sanitize_error_message,
    sanitize_for_log,
    validate_classification,
)

LLM_BASE_URL = ""
