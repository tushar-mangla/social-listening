# listening_loop/config.py
"""Runtime configuration without import-time environment snapshots.

Provider (verified, non-secret):
- Base URL default: https://codex-easy.ai/v1
- Model default: gpt-5.6-luna (provider label: codex-everywhere)
- API key variable: CODEX_EVERYWHERE_API_KEY (loaded from .env at runtime)

Call get_* helpers at runtime so tests can inject environment variables
via monkeypatch without reimporting. Never log secret values.
"""

import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is a declared dependency
    def load_dotenv(*args, **kwargs):  # type: ignore[no-redef]
        return False


_DOTENV_LOADED = False


def ensure_dotenv_loaded() -> None:
    """Load .env once per process at runtime (idempotent, never logs secrets)."""
    global _DOTENV_LOADED
    if not _DOTENV_LOADED:
        load_dotenv()
        _DOTENV_LOADED = True


# Default lookback window in hours
DEFAULT_LOOKBACK_HOURS = 24

# Verified Codex Everywhere provider defaults (non-secret).
CODEX_EVERYWHERE_BASE_URL_DEFAULT = "https://codex-easy.ai/v1"
CODEX_EVERYWHERE_MODEL_DEFAULT = "gpt-5.6-luna"
CODEX_EVERYWHERE_PROVIDER_LABEL = "codex-everywhere"
CODEX_API_KEY_VAR = "CODEX_EVERYWHERE_API_KEY"

# Legacy variable names retained for backward compatibility (read only as fallback).
_LEGACY_BASE_URL_VARS = ("LLM_BASE_URL",)
_LEGACY_MODEL_VARS = ("LLM_MODEL",)
_LEGACY_API_KEY_VARS = ("LLM_API_KEY",)

# Bounded pipeline constants (covered by tests).
INTENT_BATCH_SIZE = 16
CLASSIFICATION_BATCH_CAP = 64
LLM_TIMEOUT_SECONDS = 30
MAX_POST_CONTENT_LENGTH = 4000
ERROR_MESSAGE_LIMIT = 300
MAX_CONSECUTIVE_PROVIDER_FAILURES = 3
MAX_CLASSIFICATION_ATTEMPTS = 5
RETRY_BASE_DELAY_SECONDS = 60
RETRY_MAX_DELAY_SECONDS = 3600

# Confidence threshold for ICP qualification.
CONFIDENCE_THRESHOLD = 0.60

# List of platforms supported by opencli that we want to search
PLATFORMS = [
    "twitter",
    "facebook",
    "reddit"
]

# Targeted subreddits for recruitment/staffing agency owners & hiring managers
LEAD_SUBREDDITS = [
    "recruiting",
    "staffingagency",
    "agencyowners",
    "smallbusiness",
    "Entrepreneur"
]

TREND_SUBREDDITS = [
    "webdev",
    "SaaS",
    "automation"
]

# Search keywords targeting recruitment agency BD & hiring pain points
KEYWORDS = [
    "need a recruiter",
    "need recruiting help",
    "recommend a recruiting agency",
    "struggling to hire",
    "can't find candidates",
    "candidate ghosting",
    "hiring is hard",
    "looking for talent",
    "recruiting software",
    "applicant tracking system",
    "recruitment agency BD",
    "staffing agency client acquisition",
    "recruiter cold email",
    "ATS candidate matching"
]

QUALIFYING_KEYWORDS = (
    "need a recruiter",
    "need recruiting help",
    "recommend a recruiting agency",
    "struggling to hire",
    "can't find candidates",
    "candidate ghosting",
    "hiring is hard",
    "looking for talent",
    "recruiting software",
    "applicant tracking system",
    "recruitment agency BD",
    "staffing agency",
    "recruitment agency",
    "recruiter",
)

EXCLUDED_KEYWORDS = (
    "looking for a job",
    "open to work",
    "my resume",
    "job application",
    "seeking employment",
    "hire me",
    "i am looking for work",
    "entry level resume",
    "internal recruiter",
    "hr generalist",
    "resume advice",
)


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return default


def get_provider_base_url() -> str:
    """Return the configured base URL (never a secret)."""
    ensure_dotenv_loaded()
    raw = _first_env(
        "CODEX_EVERYWHERE_BASE_URL",
        *_LEGACY_BASE_URL_VARS,
        default=CODEX_EVERYWHERE_BASE_URL_DEFAULT,
    )
    return raw.rstrip("/")


def get_provider_chat_url() -> str:
    """Return the OpenAI-compatible chat-completions URL for the base URL."""
    return get_provider_base_url().rstrip("/") + "/chat/completions"


def get_provider_model() -> str:
    """Return the configured model ID (non-secret)."""
    ensure_dotenv_loaded()
    return _first_env(
        "CODEX_EVERYWHERE_MODEL",
        *_LEGACY_MODEL_VARS,
        default=CODEX_EVERYWHERE_MODEL_DEFAULT,
    )


def get_provider_api_key() -> str:
    """Return the API key value (caller must never log it)."""
    ensure_dotenv_loaded()
    return _first_env(CODEX_API_KEY_VAR, *_LEGACY_API_KEY_VARS, default="")


def get_provider_config_summary() -> dict:
    """Return non-secret provider diagnostics safe for logs/docs."""
    return {
        "provider": CODEX_EVERYWHERE_PROVIDER_LABEL,
        "base_url": get_provider_base_url(),
        "model": get_provider_model(),
        "api_key_var": CODEX_API_KEY_VAR,
        "configured": bool(get_provider_api_key()),
        "timeout_seconds": LLM_TIMEOUT_SECONDS,
        "batch_size": INTENT_BATCH_SIZE,
        "batch_cap": CLASSIFICATION_BATCH_CAP,
        "retry_cap": MAX_CLASSIFICATION_ATTEMPTS,
        "retry_base_delay_seconds": RETRY_BASE_DELAY_SECONDS,
        "retry_max_delay_seconds": RETRY_MAX_DELAY_SECONDS,
    }
