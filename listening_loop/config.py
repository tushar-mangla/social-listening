# listening_loop/config.py

# Default lookback window in hours
DEFAULT_LOOKBACK_HOURS = 24

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
)

