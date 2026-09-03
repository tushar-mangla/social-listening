# listening_loop/config.py

# Default lookback window in hours
DEFAULT_LOOKBACK_HOURS = 24

# List of platforms supported by opencli that we want to search
PLATFORMS = [
    "twitter",
    "facebook",
    "reddit"
]

# Keywords to search for
# Using a list of phrases to be joined with OR
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
    "applicant tracking system"
]

QUALIFYING_KEYWORDS = (
    "need a recruiter",
    "need recruiting help",
    "recommend a recruiting agency",
    "struggling to hire",
    "can't find candidates",
    "candidate ghosting",
    "hiring is hard",
    "recruiting software",
    "applicant tracking system",
)

EXCLUDED_KEYWORDS = (
    "looking for a job",
    "open to work",
    "my resume",
    "job application",
    "seeking employment",
)
