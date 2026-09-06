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

# List of platforms supported by opencli that we want to search.
# Only reddit is enabled until other platforms are validated end-to-end.
PLATFORMS = [
    "reddit",
]

# Rate limit protection: polite delay between successive discovery searches.
DISCOVERY_QUERY_DELAY_SECONDS = 1.5

# RecruitmentOS sells to recruitment/staffing agency operators.
# Do NOT mix employer hiring-intent communities into this pipeline.
# r/SaaS, r/startups → TREND_SUBREDDITS only (employer/developer audience, not agency owners).
LEAD_SUBREDDITS = [
    "recruiting",
    "staffing",
    "Recruitment",
    "freelanceRecruiters",   # highest-signal: independent recruiters discussing BD & client pain
]

DISCOVERY_QUERIES = {
    # ---------------------------------------------------------
    # 1. CLIENT ACQUISITION / BUSINESS DEVELOPMENT
    # Natural agency-owner language — NOT formal query phrases.
    # ---------------------------------------------------------
    "agency_business_development": [
        "getting clients",
        "find new clients",
        "finding clients",
        "win new clients",
        "winning clients",
        "client acquisition",
        "new business",
        "business development",
        "lead generation",
        "generate leads",
        "sales pipeline",
        "BD strategy",
        "BD calls",
    ],

    # ---------------------------------------------------------
    # 2. PIPELINE / REFERRAL PAIN
    # ---------------------------------------------------------
    "agency_pipeline_pain": [
        "need more clients",
        "struggling to get clients",
        "struggling with BD",
        "pipeline is dry",
        "dry pipeline",
        "referrals drying up",
        "referrals have dried up",
        "not enough clients",
        "not enough vacancies",
        "job flow",
        "more job flow",
        "new vacancies",
        "new roles",
    ],

    # ---------------------------------------------------------
    # 3. OUTBOUND / COLD EMAIL / LINKEDIN
    # ---------------------------------------------------------
    "agency_outbound": [
        "cold email",
        "cold emailing",
        "cold calling",
        "linkedin outreach",
        "outbound",
        "outbound sales",
        "email outreach",
        "reply rate",
        "response rate",
        "booking meetings",
        "book more meetings",
        "prospecting",
    ],

    # ---------------------------------------------------------
    # 4. RECRUITMENT BUSINESS OPERATIONS
    # ---------------------------------------------------------
    "agency_operations": [
        "recruitment automation",
        "recruiting automation",
        "staffing automation",
        "recruitment workflow",
        "recruiting workflow",
        "ATS automation",
        "CRM automation",
        "recruitment CRM",
        "staffing CRM",
        "recruitment ATS",
    ],

    # ---------------------------------------------------------
    # 5. CANDIDATE DATABASE / MONETISATION
    # ---------------------------------------------------------
    "candidate_database": [
        "candidate database",
        "candidate database sitting",
        "old candidates",
        "database candidates",
        "database marketing",
        "candidate rediscovery",
        "candidate matching",
        "candidate to client",
        "candidate marketing",
        "market candidates",
        "reverse marketing",
    ],

    # ---------------------------------------------------------
    # 6. RECRUITMENT-AGENCY SPECIFIC LANGUAGE
    # ---------------------------------------------------------
    "agency_language": [
        "recruitment agency",
        "recruitment business",
        "recruiting agency",
        "staffing agency",
        "staffing firm",
        "recruitment firm",
        "executive search firm",
        "recruitment founder",
        "staffing founder",
        "agency owner",
        "recruitment owner",
        "recruitment director",
        "staffing owner",
        "360 recruiter",
        "recruitment consultant",
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
