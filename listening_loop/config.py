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
        load_dotenv(override=True)
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

# Platforms searched in order for each configured query.
PLATFORMS = ["reddit", "twitter", "facebook"]

# Randomized pacing and bounded rate-limit recovery for discovery searches.
INTER_QUERY_SLEEP_MIN = 3.0
INTER_QUERY_SLEEP_MAX = 7.0
RATE_LIMIT_BACKOFF_MIN = 60.0
RATE_LIMIT_BACKOFF_MAX = 300.0
MAX_RATE_LIMIT_RETRIES = 3

# Fetch retry constants
FETCH_RETRY_BACKOFF_MIN = 15.0
FETCH_RETRY_BACKOFF_MAX = 30.0
MAX_FETCH_RETRIES = 1

# Platforms that use retrieved_at when posted_at is missing.
TIMESTAMP_FALLBACK_PLATFORMS = ("facebook",)

# Descriptive aliases retained for callers that use the plan's long names.
DISCOVERY_QUERY_JITTER_MIN_SECONDS = INTER_QUERY_SLEEP_MIN
DISCOVERY_QUERY_JITTER_MAX_SECONDS = INTER_QUERY_SLEEP_MAX
DISCOVERY_RATE_LIMIT_COOLDOWN_MIN_SECONDS = RATE_LIMIT_BACKOFF_MIN
DISCOVERY_RATE_LIMIT_COOLDOWN_MAX_SECONDS = RATE_LIMIT_BACKOFF_MAX
DISCOVERY_RATE_LIMIT_MAX_RETRIES = MAX_RATE_LIMIT_RETRIES

# RecruitmentOS sells to recruitment/staffing agency operators.
# Do NOT mix employer hiring-intent communities into this pipeline.
# r/SaaS, r/startups → TREND_SUBREDDITS only (employer/developer audience, not agency owners).
LEAD_SUBREDDITS = [
    "freelanceRecruiters",   # highest-signal: independent recruiters discussing BD & client pain
    "staffingagency",
    "recruiting",
    "agencyowners",
]

DISCOVERY_QUERIES = {
    "agency_client_acquisition": [
        "recruitment agency getting clients",
        "staffing agency client acquisition",
    ],
    "agency_pipeline_pain": [
        "recruitment agency need more clients",
        "staffing agency pipeline dry",
    ],
    "agency_outbound": [
        "recruitment agency cold email",
        "recruitment agency outbound sales",
    ],
    "agency_operations": [
        "staffing agency ATS automation",
        "recruitment agency CRM",
    ],
}

# Facebook feed is fetched once per run (no search queries needed — the news feed
# surfaces posts from joined groups and followed pages already curated to the user's
# account). FACEBOOK_FEED_LIMIT controls how many posts are pulled per run.
FACEBOOK_FEED_LIMIT = 25

# FACEBOOK_QUERIES is retained for reference / testing; the live pipeline uses feed.
FACEBOOK_QUERIES = {
    "agency_client_acquisition": [
        "how to get staffing clients",
        "recruitment agency getting new clients",
    ],
    "agency_pipeline_pain": [
        "struggling to get clients recruitment",
    ],
    "agency_outbound": [
        "cold email tips for recruiters",
        "recruiter cold outreach advice",
    ],
    "agency_operations": [
        "recommendations for recruitment ATS",
        "best CRM for staffing agency",
    ],
}

TREND_SUBREDDITS = [
    "webdev",
    "SaaS",       # employer/developer/product audience — trend content only
    "startups",   # employer audience — trend content only
    "automation",
]

# Search keywords — maximize recall; the LLM handles final ICP precision.
KEYWORDS = [
    # BD
    "business development",
    "new business",
    "client acquisition",
    "getting clients",
    "finding clients",
    "win clients",
    "new clients",
    "lead generation",
    # Pipeline pain
    "pipeline",
    "referrals",
    "job flow",
    "vacancies",
    "struggling with BD",
    "need more clients",
    # Outreach
    "cold email",
    "cold calling",
    "linkedin outreach",
    "outbound",
    "prospecting",
    "reply rate",
    # Recruitment operations
    "recruitment agency",
    "recruitment business",
    "staffing agency",
    "staffing firm",
    "recruitment firm",
    "recruitment automation",
    # Database / C2C
    "candidate database",
    "candidate matching",
    "candidate marketing",
    "reverse marketing",
    "ATS",
    "CRM",
]

# Stage-1 pre-filter: indicates EITHER agency identity OR relevant commercial pain.
# Do not use this as the final ICP decision — the LLM does that.
QUALIFYING_KEYWORDS = (
    # Agency identity
    "recruitment agency",
    "recruiting agency",
    "staffing agency",
    "recruitment business",
    "recruitment firm",
    "staffing firm",
    "executive search",
    "headhunting",
    "agency owner",
    "recruitment founder",
    "staffing founder",
    "recruitment director",
    "staffing owner",
    "360 recruiter",
    "recruiter",
    # BD / commercial problems
    "business development",
    "new business",
    "client acquisition",
    "getting clients",
    "finding clients",
    "win clients",
    "winning clients",
    "need more clients",
    "lead generation",
    "sales pipeline",
    "pipeline is dry",
    "dry pipeline",
    "referrals",
    "job flow",
    # Outbound
    "cold email",
    "cold emailing",
    "cold calling",
    "linkedin outreach",
    "outbound",
    "prospecting",
    "reply rate",
    "response rate",
    "booking meetings",
    # Recruitment operations
    "candidate database",
    "candidate matching",
    "candidate marketing",
    "reverse marketing",
    "recruitment automation",
    "staffing automation",
    "ATS automation",
    "CRM automation",
)

EXCLUDED_KEYWORDS = (
    # Job seekers
    "looking for a job",
    "open to work",
    "my resume",
    "my cv",
    "job application",
    "job applications",
    "seeking employment",
    "hire me",
    "i am looking for work",
    "looking for work",
    "entry level resume",
    "resume advice",
    "cv advice",
    # Candidate-focused discussions
    "interview advice",
    "interview tips",
    "salary negotiation",
    "career advice",
    # Internal HR / talent teams
    "internal recruiter",
    "in-house recruiter",
    "in house recruiter",
    "internal talent acquisition",
    "talent acquisition specialist",
    "hr generalist",
    # Recruiter job hunting
    "looking for recruiter role",
    "looking for recruitment role",
    "recruiter looking for work",
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


def __getattr__(name: str):
    if name == "REDDIT_COMMUNITIES":
        return LEAD_SUBREDDITS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(list(globals().keys()) + ["REDDIT_COMMUNITIES"])

