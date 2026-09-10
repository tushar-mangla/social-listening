# ENHANCEMENT_PLAN: Authenticated Multi-Platform Discovery With Rate Limits

**Date:** 2026-09-09  
**Repository:** `/Users/tusharmangla/RecruitmentOS/social_listening`  
**Status:** Pending explicit Tushar approval before implementation  
**Process tier:** Medium. This changes an authenticated third-party discovery path and its scheduler behavior, but has no application API or persistence migration.

## Goal

Reduce discovery volume to 12 high-intent recruitment-agency queries, enable authenticated Twitter global search alongside subreddit-scoped Reddit search, and make the runner pace work with randomized 3-7 second jitter plus bounded, explicit HTTP-429 cooldown handling. Preserve the existing read-only collection, qualification, SQLite, retry, and Notion-sync behavior.

## Evidence And Current Behavior

- `listening_loop/opencli_adapter.py:run_opencli` constructs only `opencli <platform> search <query> ... --format json`; Reddit additionally uses `--sort new` and verified `--subreddit`. The repository has no OpenCLI post, comment, reply, vote, follow, DM, or account-management invocation. The only `requests.post` found is the separate LLM-classification provider call in `qualification.py`, not Reddit or Twitter.
- `run.main` expands every configured query across `LEAD_SUBREDDITS` for Reddit and executes every non-Reddit query once with `community=None`. It currently sleeps a fixed 1.5 seconds after every attempted item and halts only after four generic consecutive discovery exceptions.
- The configured catalog is 74 queries in six families. With four lead subreddits it creates 296 Reddit requests per full run. Enabling Twitter with the same catalog would add 74 global Twitter searches. The target catalog creates 48 Reddit work items and 12 Twitter work items, 60 first attempts per all-platform run.
- `run_opencli` recognizes `429` only in an error string and raises generic `OpenCLIExecutionError`; the runner cannot reliably distinguish rate limiting from timeouts, unsupported Reddit scope, or session failures.
- Existing coverage is in `tests/test_discovery_queries.py`, `tests/test_run.py`, and `tests/test_opencli_adapter.py`. `tests/test_config.py` and `tests/test_discovery.py`, named in the request, do not exist in this checkout. `tests/test_resilience_repair.py` also exercises the main flow.
- GitNexus upstream impact: `main` is LOW risk (six exact dependents); `fetch_leads` is LOW risk (nine exact dependents, affecting the `main` flow); `run_opencli` is MEDIUM risk (13 exact dependents, mainly adapter tests and the `main` flow). The index is two commits behind `HEAD`, so implementation must refresh it and repeat impact analysis before source edits. No import cycles are currently detected.
- The worktree already has user changes in `listening_loop/config.py`, `listening_loop/install-scheduler.sh`, and `listening_loop/run.sh`, plus an untracked scheduler plan. Implementation must preserve and reconcile those changes, not revert them.

## Ban Risk Assessment

### What This System Does

This code path is **read-only discovery**. It asks OpenCLI to search Reddit/Twitter and locally filters, classifies, stores, and optionally sends qualified lead records to Notion. It does not publish content, interact with users, or alter social-platform state. Logging in through OpenCLI makes searches authenticated, but does not turn this application into a posting or DMing system.

### What HTTP 429 Means

HTTP 429 means the server is temporarily refusing requests because a rate or abuse threshold was exceeded. In this context it normally applies to the current request identity combination such as IP, browser/session cookies, account, endpoint, and request pattern. It is a cooldown/throttle signal, not an account-ban response. It can occur on a healthy account and does not itself establish that an account is restricted.

### When Reddit Generally Bans Or Restricts

Reddit can issue account, content, or IP/network restrictions for policy violations or abuse patterns, including spam/scams, repetitive promotional posting/comments/DMs, ban evasion, coordinated/manipulative behavior, credential/account abuse, deliberately evading rate limits, prohibited scraping/automation patterns, and repeatedly ignoring warnings or technical blocks. A read-only search workload does not eliminate policy risk: aggressive, unattended, or evasive automation can still be detected and restricted. Reddit alone controls enforcement, so no code change can guarantee no ban.

### Practical Risk By Scenario

| Scenario | Account-ban risk | Temporary 429/IP/session-throttle risk | Reasoned assessment |
| --- | --- | --- | --- |
| (a) Unauthenticated, spammy ~312-query pass | Low-to-moderate account risk; moderate-to-high if repeated after errors or combined with other abusive activity | High | High request volume without a stable authenticated session is likely to trigger temporary throttles. A one-off 429 is far more likely than a ban, but repeatedly hammering after 429 raises the chance of an account/network or anti-abuse restriction. |
| (b) Authenticated, 12 queries, four subreddits, 3-7s jitter, 429 cooldown | Low, but non-zero | Low-to-moderate, depending on OpenCLI/Reddit limits and schedule frequency | 48 initial Reddit searches spread over roughly 2.4-5.6 minutes (plus cooldown/retry) is substantially less bursty. Authentication and backoff reduce accidental throttling but are not a guarantee, especially if the scheduled job runs often or other activity shares the account/IP. |

**Operator guardrails:** Do not run overlapping jobs, do not retry 429s in a tight loop, stop the run after the bounded rate-limit policy is exhausted, keep OpenCLI credentials private, and pause/reassess if warnings, CAPTCHA, login challenges, or repeated 429s occur. This is an engineering risk assessment, not legal advice or a guarantee of platform-policy compliance.

## Assumptions, Non-Goals, And Decisions Needed

### Assumptions

- Tushar is already authenticated in the installed OpenCLI for both Reddit and Twitter.
- `opencli twitter search <query> --format json` remains the documented global-search command; the repository test currently models this form, but implementation must verify actual non-sensitive help/version output before enabling scheduled production use.
- Reddit continues to support the verified `--subreddit` search option. The adapter must not guess a replacement if that help contract is unavailable.
- A run invokes platforms in `config.PLATFORMS` order, then preserves existing configured query order and Reddit community order. No concurrent workers will be added.

### Non-Goals

- No posting, commenting, voting, DMing, following, account action, proxy rotation, CAPTCHA bypass, or attempt to evade platform controls.
- No change to LLM provider, prompt, qualification rules, SQLite schema, Notion schema/mapping, retryable classifier behavior, or the legacy RSS utility.
- No frontend, application HTTP API, database migration, or persistence of new rate-limit/provenance data.
- No claim that the implementation guarantees Reddit or Twitter account safety.

### Decisions Requiring Review

1. Approve the exact 12-query catalog below, or provide replacements before implementation. The set is shared across both platforms using quoted, recruitment-agency-specific phrase queries; Reddit scopes by subreddit while Twitter runs each query globally.
2. Approve a single retry after each explicit 429, using a randomized 60-90 second cooldown. If that retry is also 429, record the item as rate-limited and halt remaining discovery for that platform (continue the other platform only if it has not been halted). This avoids a retry storm while retaining one recovery opportunity.
3. Confirm that the scheduler will not overlap runs. With 60 first attempts and 3-7 seconds between attempts, an all-platform run takes roughly 3-7 minutes excluding OpenCLI execution, result processing, and any 429 cooldown.

## User Journeys

1. An operator runs `python -m listening_loop.run --platform reddit`. The runner performs 12 high-intent queries across the four configured subreddits, waits a random 3-7 seconds between requests, and continues with existing filtering/storage behavior.
2. An operator runs the default all-platform command. It performs those 48 Reddit searches plus 12 unscoped Twitter searches, with the same global pacing policy, while retaining platform/query/community provenance in the in-memory query report.
3. A search receives HTTP 429. The runner records a sanitized rate-limit event, waits a random 60-90 seconds, retries the same work item once, then stops further queries only for that platform if the retry also receives 429. It does not issue rapid retries.
4. A timeout, malformed output, login/session error, or unsupported Reddit scope is recorded as the existing non-rate-limit error path; the runner retains current bounded generic consecutive-error protection and does not mislabel it as 429.
5. A post matched through multiple work items is still deduplicated by `post_id`; only the first occurrence goes through the unchanged stage-one and qualification pipeline. Dry-run still persists locally and skips Notion.

## Contracts

### Discovery Configuration Contract

Set:

```python
PLATFORMS = ["reddit", "twitter"]
DISCOVERY_QUERY_JITTER_MIN_SECONDS = 3.0
DISCOVERY_QUERY_JITTER_MAX_SECONDS = 7.0
DISCOVERY_RATE_LIMIT_COOLDOWN_MIN_SECONDS = 60.0
DISCOVERY_RATE_LIMIT_COOLDOWN_MAX_SECONDS = 90.0
DISCOVERY_RATE_LIMIT_MAX_RETRIES = 1
```

Replace the 74-entry `DISCOVERY_QUERIES` catalog with this deterministic 12-query mapping:

```python
{
    "agency_client_acquisition": [
        '"recruitment agency" "getting clients"',
        '"staffing agency" "client acquisition"',
        '"recruitment business" "new business"',
    ],
    "agency_pipeline_pain": [
        '"recruitment agency" "need more clients"',
        '"staffing agency" "pipeline is dry"',
        '"recruitment business" "job flow"',
    ],
    "agency_outbound": [
        '"recruitment agency" "cold email"',
        '"staffing agency" "linkedin outreach"',
        '"recruitment business" "outbound sales"',
    ],
    "agency_operations": [
        '"recruitment agency" "candidate database"',
        '"staffing agency" "ATS automation"',
        '"recruitment agency" "CRM automation"',
    ],
}
```

Retain the current four `LEAD_SUBREDDITS`: `recruiting`, `staffing`, `Recruitment`, and `freelanceRecruiters`. The query strings are deliberately usable with both provider search syntaxes: Reddit applies a community option; Twitter receives the same exact string with `community=None`. If OpenCLI documents materially different Twitter query syntax, introduce a small explicit per-platform query mapping with the same 12 intent slots rather than passing Reddit-only syntax to Twitter. The runner must select the appropriate platform catalog and tests must assert its work-item counts.

`QUALIFYING_KEYWORDS`, `EXCLUDED_KEYWORDS`, and `KEYWORDS` are not discovery scheduling inputs in the current runner and remain unchanged unless the implementation discovers a direct compatibility requirement. Do not retain a static `DISCOVERY_QUERY_DELAY_SECONDS` as an active pacing control.

### Adapter And Error Contract

- Add a typed `OpenCLIRateLimitError(OpenCLIExecutionError)` (or an equivalent non-string error indicator) when a nonzero OpenCLI result contains a verified 429 indicator. Preserve redaction/bounded diagnostics and all other current `OpenCLIExecutionError` behavior.
- `run_opencli` remains search-only, preserves its 60-second subprocess timeout, JSON/JSON-lines parsing, and Reddit scope verification. Twitter command construction remains `opencli twitter search <query> --format json` with no subreddit flag.
- `fetch_leads` signature and normalized-lead fields remain compatible: `post_id`, `source`, `content`, `url`, `posted_at`, `author`, `platform`, `community`, `query_family`, `exact_query`, and UTC `retrieved_at`.

### Runner Contract

- Replace the fixed delay with an injectable/helper-backed random duration sampled inclusively from the configured jitter bounds. Tests must not sleep; production must sleep after each outbound attempt, including a failed attempt before the next item.
- For a typed 429: log only sanitized platform/query-family/context and cooldown duration, sleep a random 60-90 seconds, retry the identical item exactly once, then mark its report record error if retry fails. A second 429 halts pending work items for that platform, not all platforms. Reset generic consecutive-error accounting after a successful fetch.
- Preserve query report fields and add a bounded `rate_limit_events`/`rate_limit_retries` count only if needed to make retry behavior observable; do not log raw subprocess output, social content, or credentials.
- Non-429 failures retain isolated handling and four-consecutive-error early stop semantics. Implement platform-local halt state so a Reddit throttle does not incorrectly suppress Twitter discovery.

### Frontend, API, And Database Contract

No frontend or application API exists in scope. No database entity changes, migrations, indexes, validation rules, permissions, or database constraints are required. Existing `leads` identity remains `post_id` and its unique constraint continues to prevent duplicate persistence. Only local runtime configuration and transient in-memory runner/report behavior change.

## Affected Files

| File | Planned change |
| --- | --- |
| `listening_loop/config.py` | Enable Twitter; replace the broad discovery catalog with the approved 12 queries; define jitter/cooldown/retry constants while preserving qualification constants and four lead subreddits. |
| `listening_loop/opencli_adapter.py` | Distinguish an OpenCLI-detected 429 with a typed error; preserve read-only command construction, scope validation, parsing, and normalized output. |
| `listening_loop/run.py` | Add testable randomized pacing, bounded one-time 429 cooldown/retry, platform-local rate-limit halting, and correct Reddit/Twitter work-item execution. |
| `tests/test_discovery_queries.py` | Replace the old 74-query exact fixture with the approved 12-query contract; assert 48 Reddit and 12 Twitter scheduled items; cover jitter and 429 retry/halt behavior. |
| `tests/test_run.py` | Update all-platform assumptions; verify Twitter global work items, no subreddit value for Twitter, non-429 failure isolation, and no real sleeps under test. |
| `tests/test_opencli_adapter.py` | Assert typed 429 detection, error compatibility, and unchanged Twitter/Reddit search-only command construction. |
| `tests/test_resilience_repair.py` | Update only fixtures affected by changed scheduling counts/delay constants; retain redaction, dedupe, and persistence assertions. |

## Implementation Sequence

1. Preserve the existing dirty worktree. Refresh GitNexus, rerun upstream impact for `main`, `fetch_leads`, and `run_opencli`, and inspect all direct test callers before source edits.
2. Verify non-sensitive operational capabilities using `opencli --version`, `opencli reddit search --help`, and `opencli twitter search --help`; confirm logged-in sessions through the least-invasive documented status method. Stop with a blocker if Reddit scope or Twitter global search syntax differs from the repository contract.
3. Write/update configuration tests first for exact platforms, four subreddits, four families/12 queries, count calculation (48 Reddit, 12 Twitter), unchanged qualifying/excluded constants, and valid jitter/cooldown ranges.
4. Update `config.py` with the approved catalog and rate-limit constants. Reconcile rather than overwrite Tushar's existing uncommitted configuration changes.
5. Add adapter characterization tests for a 429 stderr/stdout response yielding the typed error, while retaining non-429 error, timeout, malformed JSON, scope, and Twitter command assertions. Implement the minimal typed rate-limit signal in `opencli_adapter.py`.
6. Add runner tests using injected/mocked random selection and `time.sleep`: jitter stays within 3-7 seconds; first 429 waits 60-90 seconds and retries the same tuple once; second 429 stops only the affected platform; a later platform still runs; generic errors retain existing bounds; tests never wait in real time.
7. Refactor `run.main` work-item execution behind a small helper if needed to make retry state and pacing unambiguous. Apply post-attempt jitter and 429 cooldown in the defined order, retain global post dedupe and all downstream persistence/sync behavior.
8. Run focused tests, then the full test suite. Execute one controlled `--dry-run --hours 1` smoke check only after documented OpenCLI syntax is confirmed, with a single platform first, and stop immediately on repeated 429/login challenge.
9. Run GitNexus `detect_changes` on all worktree changes, inspect affected flows, verify no cycle/contract regressions, and review the diff for accidental modifications to qualification, database, Notion, scheduler, or legacy RSS behavior.

## Acceptance Criteria

1. `PLATFORMS == ["reddit", "twitter"]` in the approved configuration.
2. Scheduled discovery has exactly 12 high-intent queries in the approved order and current four lead subreddits. A default pass schedules 48 Reddit work items and 12 Twitter work items before any retry.
3. Every social-platform command remains a read-only OpenCLI `search` command. Twitter has no Reddit community flag; Reddit uses only a help-verified community option.
4. Production pacing samples every inter-query delay from 3.0 to 7.0 seconds; no test incurs a real wait.
5. A detected HTTP 429 produces exactly one randomized 60-90 second cooldown and one retry for the same work item. A second 429 does not spin or continue that platform; it records a sanitized failure and stops remaining work for only that platform.
6. Non-429 errors continue to be isolated and use existing bounded failure protection. No raw social content, stderr, credentials, or cookies are emitted in new logs.
7. Existing post-ID dedupe, lookback filtering, stage-one gate, classifier batch cap/retry behavior, SQLite persistence, dry-run semantics, and Notion sync eligibility remain unchanged.
8. Focused tests and `venv/bin/python -m pytest -q` pass. The controlled smoke check shows expected command cardinality/behavior without writes to Reddit or Twitter.

## Test And Verification Commands

```bash
venv/bin/python -m pytest -q tests/test_discovery_queries.py tests/test_run.py tests/test_opencli_adapter.py tests/test_resilience_repair.py
venv/bin/python -m pytest -q
opencli --version
opencli reddit search --help
opencli twitter search --help
venv/bin/python -m listening_loop.run --platform reddit --hours 1 --dry-run
```

Use the smoke command only after approval and syntax verification. It writes qualifying local results to SQLite by existing dry-run semantics, does not sync Notion, and does not write to any social platform.

## Risks And Mitigations

- **Platform anti-abuse action:** Rate limiting and authentication reduce but do not remove risk. Mitigate with a small query catalog, randomized pacing, one bounded retry, platform-local halt, no overlapping jobs, and no evasive behavior.
- **OpenCLI CLI drift/login state:** Verify help/version and session status before change and smoke test. Treat undocumented flags or login challenges as blockers.
- **Longer scheduler duration:** 60 requests at 3-7 seconds add 3-7 minutes plus process/runtime. Confirm launchd interval and non-overlap before production scheduling.
- **False 429 classification:** Use an explicit adapter type based on current bounded subprocess output, retain generic fallback errors, and test both paths.
- **Dirty worktree conflict:** Limit edits to approved files and preserve Tushar's existing changes after reviewing them during implementation.

## Rollback

Revert only the approved implementation commit(s) or restore the prior `config.py` platforms/query mapping and `run.py` pacing behavior as a coordinated rollback. Disable Twitter first (`PLATFORMS = ["reddit"]`) or pause the scheduler if rate-limit or login symptoms appear. Do not repeatedly rerun the collector to validate a suspected restriction; wait for the provider cooldown and inspect OpenCLI's normal authenticated session manually.

## Definition Of Done / Binary Completion Contract

**DONE only when all are true:**

- The exact approved 12-query configuration and both platforms are implemented without overwriting unrelated worktree changes.
- Adapter and runner behavior meet the read-only search, jitter, typed-429, one-retry, and platform-local halt contracts.
- The specified focused tests and full pytest suite pass, with no real sleeps in tests.
- OpenCLI Reddit/Twitter syntax is verified from installed help, and a controlled dry run completes or stops safely on documented rate limiting.
- GitNexus change detection is complete (not partial/truncated), affected flows are reviewed, and no unrelated persistence/qualification/Notion changes exist.

**NOT DONE if any are true:** OpenCLI syntax is unverified; 429 retries are unbounded or rapid; Twitter receives a Reddit scope; tests sleep/live-call a platform; a social-platform write action is introduced; test suite fails; rate limits are treated as a ban guarantee; or change detection is incomplete.
