# ENHANCEMENT_PLAN: Full Reddit Reliability + Facebook Listening End-to-End

**Date:** 2026-09-11
**Repository:** `/Users/tusharmangla/RecruitmentOS/social_listening`
**Scope:** RecruitmentOS sales / marketing / product social listening
**Status:** Approved by Tushar on 2026-09-11
**Process tier:** Large/risky. Touches an external authenticated discovery boundary (Facebook), rate-limit/retry behavior, the LLM qualification gate (which determines what is stored and synced), and the discovery catalog. Multiple components and contracts change; requires layered verification and independent review.

---

## 1. Intent

### Goal

Make Reddit listening fully operational and reliable, and implement Facebook listening end-to-end, so that the scheduled loop reliably discovers, qualifies, stores, and syncs recruitment-agency leads.

### Request type

Enhancement (primary) with Bug (LLM qualification `llm_qualified: 0`) and Feature (Facebook platform) components. Dominant delivery risk: the LLM qualification gate and the new authenticated Facebook boundary.

### Scope

1. **Reddit reliability**
   - Improve 429 backoff/jitter/retry logic in `run.py` / `opencli_adapter.py`.
   - Handle OpenCLI browser fetch failures cleanly (distinct error type, bounded retry, clear diagnostics).
   - Reconcile `LEAD_SUBREDDITS` in `config.py` against `REQUIREMENTS.md` §2.1 (add relevant agency/staffing communities).
   - Fix/verify the LLM qualification pipeline so retrieved posts are properly evaluated and qualified leads are stored and synced (diagnose why recent runs produced `llm_qualified: 0`; check prompt, response parsing, provider config).
2. **Facebook listening end-to-end**
   - Add `facebook` to `config.PLATFORMS` and to argparse choices in `run.py` (automatic once `PLATFORMS` is updated).
   - Define `FACEBOOK_QUERIES` in `config.py` for target recruitment/staffing agency keywords.
   - Implement Facebook support in `opencli_adapter.py`, including a timestamp policy (use `retrieved_at` as recency fallback so valid posts without timestamps are not dropped).
   - Handle authentication requirements cleanly (detect missing `c_user` cookie / browser session; provide clear guidance without crashing).
   - Write comprehensive unit tests for Facebook parsing, adapter behavior, and error handling.

### Non-goals

- No posting, commenting, DMing, voting, following, account action, proxy rotation, CAPTCHA bypass, or rate-limit evasion.
- No change to SQLite schema, `post_id` uniqueness, Notion properties/mapping, or the legacy `fetch_and_sync_real_leads.py` flow.
- No change to scheduler files (`install-scheduler.sh`, `run.sh`, launchd plist) or credential storage.
- No new frontend, application HTTP API, or dashboard.
- No golden-set `--self-test` harness (REQUIREMENTS.md FR-2.5) in this change; it is a follow-up if the gate change ships.

### Assumptions

- OpenCLI is installed, authenticated for Reddit/Twitter, and supports `opencli facebook search <query> --format json` (must be verified with `opencli facebook search --help` before enabling scheduled use; if the command shape differs, stop and raise a blocker rather than guessing).
- The `.env` provider override (OpenRouter `deepseek/deepseek-v4.1-flash` at `https://openrouter.ai/api/v1`) is intentional and remains the active provider; `config.py` defaults are fallbacks only.
- Facebook search is read-only discovery. Closed-group monitoring stays manual per REQUIREMENTS.md FR-1.2.
- The worktree is currently clean; implementation must keep it clean and refresh the GitNexus index before editing (index is 1 commit behind HEAD).

---

## 2. Current Behavior And Evidence

### 2.1 Rate limiting and fetch failures (Reddit)

- `opencli_adapter.run_opencli` runs `opencli <platform> search <query> [--sort new] [--subreddit <c>] --format json` with `timeout=60`, `check=False`. Nonzero return codes raise `OpenCLIRateLimitError` when the combined output matches `(?i)(?:\bhttp\s*)?\b429\b|\btoo many requests\b`, otherwise generic `OpenCLIExecutionError` (with a `(fetch failed)` detail suffix when `"Failed to fetch"` appears).
- `run.main` retries 429 once (`MAX_RATE_LIMIT_RETRIES = 1`) after a uniform 60–90 s cooldown, then halts the platform. Generic failures are **not retried**; they increment `consecutive_discovery_errors` and move on. After 4 consecutive generic failures the whole run halts.
- Evidence (`logs/launchd.log`): `Discovery query failed: reddit process failed with returncode 1` (2026-09-11 13:30) — a generic fetch failure with no retry and no actionable detail.

### 2.2 LLM qualification (`llm_qualified: 0`)

- Evidence (`logs/launchd.log`, 2026-09-11): `sent_to_llm: 16, llm_rejected: 16` and `sent_to_llm: 5, llm_rejected: 5`. The provider is called, responses parse (no `unclassified`/`provider_error` flood), and every post is classified `not_qualified`. `added_to_db` equals `sent_to_llm`, so outcomes are persisted — the pipeline works mechanically; the gate rejects everything.
- `qualification.validate_classification` computes `confidence = (icp_score + intent_score) / 2` but the qualification gate is **numeric-only**: `icp_score >= 0.60 AND intent_score >= 0.50`. It ignores `author_role`, `intent`, and `icp` enums entirely.
- REQUIREMENTS.md FR-2.2 specifies a different gate: `author_role ∈ {owner, unknown}` AND `intent ∈ {buying, pain}` AND `icp ≠ not_icp` AND `confidence ≥ 0.6`. The implementation diverges from the spec.
- The `SYSTEM_PROMPT` is strict ("EXCLUDE all of: job seekers, resume advice, internal HR…, developers, generic agencies…, freelancers, employers, and unrelated users") and the active model is `deepseek/deepseek-v4.1-flash` via OpenRouter. Root cause is unconfirmed: either the model under-scores genuinely-ICP posts (gate too strict) or the discovered posts are genuinely non-ICP (discovery noise). **Diagnosis must precede the fix.**
- Sync is blocked downstream: `database.get_unsynced_leads()` returns only `classifier_status = 'qualified'` rows, so with `llm_qualified: 0` nothing ever syncs to Notion.

### 2.3 Subreddit reconciliation

- `REQUIREMENTS.md` §2.1: `r/recruiting` (primary), `r/staffingagency` (primary), `r/agencyowners` (verified), `r/Entrepreneur` (probation), `r/smallbusiness` (probation).
- `config.LEAD_SUBREDDITS = ["recruiting", "staffing", "Recruitment", "freelanceRecruiters"]`.
- Mismatch: `staffing` vs `staffingagency`; `agencyowners`, `Entrepreneur`, `smallbusiness` missing; `Recruitment` and `freelanceRecruiters` not listed in REQUIREMENTS.md (config comment calls `freelanceRecruiters` "highest-signal").

### 2.4 Facebook (new)

- `config.PLATFORMS = ["reddit", "twitter"]`; `run.py` argparse uses `choices=config.PLATFORMS + ['all']`, so adding `facebook` to `PLATFORMS` propagates automatically.
- `run.main` iterates `config.DISCOVERY_QUERIES` for every platform and uses `config.REDDIT_COMMUNITIES if platform == "reddit" else [None]` — Facebook would currently run the Reddit/Twitter query catalog with `community=None`.
- `fetch_leads` drops any post without a parseable timestamp (`if not posted_at or posted_at < time_limit: continue`). The OpenCLI Facebook scraper omits timestamps, so **every Facebook post would be dropped today**.
- There is no auth/session-failure detection anywhere in the adapter.

---

## 3. Impact Map

GitNexus upstream impact (index 1 commit behind HEAD — refresh and re-run before editing):

| Symbol | Risk | Direct dependents | Affected flows |
| --- | --- | --- | --- |
| `opencli_adapter.run_opencli` | LOW | 1 (`fetch_leads`) + tests | `main` |
| `opencli_adapter.fetch_leads` | LOW | 1 (`run.main`) + tests | `main` |
| `qualification.validate_classification` | LOW | `parse_response`, `classify_posts` + tests | `classify_posts`, `main` |
| `run.main` | LOW (per prior plans) | scheduler entrypoint + tests | `main` |

No HIGH/CRITICAL findings. No import cycles detected in prior checks. The `main` execution flow is the single affected process; every change below must keep it observable and recoverable.

---

## 4. Affected Files And Symbols

| File | Symbols / responsibility | Planned treatment |
| --- | --- | --- |
| `listening_loop/config.py` | `PLATFORMS`, `LEAD_SUBREDDITS`, `FACEBOOK_QUERIES`, `RATE_LIMIT_BACKOFF_MIN/MAX`, `MAX_RATE_LIMIT_RETRIES`, new `TIMESTAMP_FALLBACK_PLATFORMS`, new fetch-retry constants | Add `"facebook"` to `PLATFORMS`; reconcile `LEAD_SUBREDDITS`; add `FACEBOOK_QUERIES`; tune rate-limit constants (exponential backoff + jitter); add timestamp-fallback policy constant. |
| `listening_loop/opencli_adapter.py` | `run_opencli`, `fetch_leads`, `parse_timestamp`, `OpenCLIRateLimitError`, new `OpenCLIAuthenticationError`, new `OpenCLIFetchError`, new auth/fetch pattern detection, new `_parse_retry_after` | Add distinct exception types; broaden 429 detection; detect auth/session failures and browser fetch failures; implement Facebook timestamp fallback in `fetch_leads`; preserve all existing command construction, JSON parsing, and provenance. |
| `listening_loop/run.py` | `main`, `_rate_limit_cooldown`, `_pace_between_attempts`, `classify_and_store`, `record_outcome`, `run_metrics` | Select `FACEBOOK_QUERIES` for `platform == "facebook"`; catch `OpenCLIAuthenticationError` (clear guidance, halt only Facebook); retry `OpenCLIFetchError` once with short backoff; exponential+jitter 429 backoff honoring `Retry-After` when present; add `rejection_reason` breakdown to `run_metrics`. |
| `listening_loop/qualification.py` | `validate_classification`, `SYSTEM_PROMPT`, `QUALIFYING_ROLES`, `QUALIFYING_ICPS`, `QUALIFYING_INTENTS`, `CONFIDENCE_THRESHOLD` | Align the qualification gate with REQUIREMENTS.md FR-2.2 (enum-based + confidence) **pending Tushar's decision**; calibrate prompt only if diagnosis shows model under-scoring; add a `rejection_reason` breakdown helper for run metrics. |
| `tests/test_opencli_adapter.py` | adapter command/parse/error tests | Add Facebook command construction, timestamp fallback, auth-error detection, fetch-error detection, retry-after parsing tests. |
| `tests/test_run.py` | runner scheduling/filtering/retry tests | Add Facebook query selection, auth-halt behavior, backoff/jitter, fetch-retry, rejection-reason metrics tests. |
| `tests/test_discovery_queries.py` | config catalog tests | Update `PLATFORMS` expectation; add `FACEBOOK_QUERIES` assertions; update `LEAD_SUBREDDITS` expectation. |
| `tests/test_qualification.py` | gate/parse tests | Add FR-2.2 gate tests (enum + confidence), rejection-reason breakdown tests. |
| `tests/test_resilience_repair.py` | resilience fixtures | Update only if catalog/gate fixtures change; preserve redaction/monotonic assertions. |
| `.env.example` (optional, documentation only) | — | Document that Facebook search requires an authenticated OpenCLI browser session (`c_user` cookie); no secrets added. |

**Unchanged:** `database.py`, `notion_sync.py`, `classifier.py` (shim), `logger.py`, scheduler files, `fetch_and_sync_real_leads.py`.

---

## 5. Frontend / API / Database / Data Contract

- **Frontend:** None. Scheduled worker only.
- **HTTP API:** None. OpenCLI is an external subprocess boundary; the LLM provider call in `qualification.py` is unchanged in shape.
- **Discovery command contract:** `opencli <platform> search <query> [--sort new] [--subreddit <c>] --format json`. Facebook adds no flags beyond `--format json`; `community=None` for Facebook.
- **Normalized lead contract (unchanged fields):** `post_id`, `source`, `content`, `url`, `posted_at`, `author`, `platform`, `community`, `query_family`, `exact_query`, `retrieved_at`. **New field:** `posted_at_fallback` (`"retrieved_at"` when the Facebook timestamp policy applies, else `None`).
- **Timestamp policy (Facebook):** when a Facebook post has no parseable `timestamp`/`created_at`/`created_utc`, set `posted_at = retrieved_at` (now, UTC) and set `posted_at_fallback = "retrieved_at"`. The post is therefore always within the lookback window; `post_id` dedup prevents re-insertion. Scoped to platforms in `config.TIMESTAMP_FALLBACK_PLATFORMS` (default `("facebook",)`) so Reddit/Twitter behavior is unchanged.
- **Error contract (new exception hierarchy):**
  - `OpenCLIRateLimitError(OpenCLIExecutionError)` — 429 detected (existing).
  - `OpenCLIFetchError(OpenCLIExecutionError)` — browser/network fetch failure (e.g., `Failed to fetch`, `ERR_*`, `connection`, `timed out`), returncode nonzero.
  - `OpenCLIAuthenticationError(OpenCLIExecutionError)` — auth/session failure (e.g., `c_user`, `cookie`, `login`, `log in`, `sign in`, `session`, `authenticate`, `not logged in`, `captcha`, `challenge`).
- **Database:** no schema, column, index, migration, permission, or constraint change. `post_id` UNIQUE remains the persistence backstop; `source` stores `"facebook"`. `classifier_status = 'qualified'` remains the sync gate.
- **Notion:** no property or mapping change.

---

## 6. Schema Or Migration Approach

None. No SQLite migration is required. The only new persisted-adjacent data is the in-memory `posted_at_fallback` provenance field on the normalized lead (not a new column). If the builder later wants to persist it, that is a separate approved change.

---

## 7. User Journeys

1. **Operator runs the all-platform loop.** Reddit and Twitter behave as today (bounded pacing, 429 cooldown, platform-local halt), plus Facebook runs its own `FACEBOOK_QUERIES` catalog with `community=None`.
2. **Reddit returns a transient fetch failure.** The adapter raises `OpenCLIFetchError`; the runner retries once with a short backoff, logs a clear diagnostic, and continues the remaining work items instead of silently moving on.
3. **Reddit returns HTTP 429.** The runner backs off with exponential growth + jitter (honoring `Retry-After` when the CLI reports it), retries up to the configured bound, then halts only that platform with a clear log line.
4. **Facebook is not authenticated.** The adapter raises `OpenCLIAuthenticationError`; the runner prints actionable guidance ("run `opencli facebook login` / ensure the `c_user` cookie is present"), halts only Facebook, and continues Reddit/Twitter without crashing.
5. **Facebook returns posts without timestamps.** `fetch_leads` keeps them using the `retrieved_at` fallback, marks `posted_at_fallback`, and they flow through dedup, stage-1, LLM, and storage like any other post.
6. **A qualified lead is produced.** It is stored with `classifier_status='qualified'`, appears in `get_unsynced_leads()`, syncs to Notion, and is marked synced — the end-to-end journey the current `llm_qualified: 0` state blocks.
7. **Operator runs `--platform facebook` or `--platform reddit`.** Only that platform's work-item set runs.

---

## 8. Acceptance Criteria

1. `config.PLATFORMS == ["reddit", "twitter", "facebook"]`; `--platform facebook` and `--platform all` both work; `--platform all` runs Facebook with `FACEBOOK_QUERIES` and `community=None`.
2. `FACEBOOK_QUERIES` is a non-empty dict of recruitment/staffing agency-first queries (per REQUIREMENTS.md FR-1.1), each a non-empty unquoted string with no ` OR `/` AND ` tokens.
3. `LEAD_SUBREDDITS` matches the approved reconciled list (decision D1) and `REDDIT_COMMUNITIES` alias stays consistent.
4. 429 handling: exponential backoff with jitter bounded by `RATE_LIMIT_BACKOFF_MIN/MAX`, retry count = `MAX_RATE_LIMIT_RETRIES`, `Retry-After` honored when parseable, platform-local halt after exhaustion, no tight loop.
5. `OpenCLIFetchError` is raised for browser fetch failures, retried at most once with a short bounded backoff, and does not halt the platform on a single occurrence.
6. `OpenCLIAuthenticationError` is raised on auth/session patterns, produces actionable guidance in logs, halts only Facebook, and never crashes the run.
7. Facebook posts without timestamps are retained with `posted_at == retrieved_at` and `posted_at_fallback == "retrieved_at"`; Reddit/Twitter posts without timestamps are still dropped (unchanged).
8. LLM qualification: after diagnosis, the approved gate (decision D2) is implemented; a genuinely-ICP post (owner/founder of a recruitment agency expressing BD/pain intent with adequate confidence) is stored `qualified`; a job-seeker post is stored `not_qualified`; `run_metrics` includes a `rejection_reason` breakdown.
9. End-to-end: a `qualified` row is returned by `get_unsynced_leads()`, syncs via `notion_sync.sync_leads_to_notion`, and is marked synced (covered by tests).
10. Full test suite passes; focused Facebook/adapter/runner/qualification tests added; no raw content, secrets, or full prompts in logs.

---

## 9. Step-by-Step Implementation Sequence

**Phase 0 — Preconditions (no app edits)**
1. Refresh the GitNexus index (`node .gitnexus/run.cjs analyze --index-only` or MCP) and re-run upstream impact for `run_opencli`, `fetch_leads`, `validate_classification`, and `main`. Record any changed risk before editing.
2. Verify installed OpenCLI contracts with non-sensitive commands: `opencli --version`, `opencli reddit search --help`, `opencli twitter search --help`, `opencli facebook search --help`. **Blocker if** `facebook search` is not a documented command or requires different flags — stop and raise for review rather than guessing.
3. Run the full test suite to capture the current baseline (worktree is clean).

**Phase 1 — LLM qualification diagnosis (before any gate change)**
4. Inspect the persisted rejection evidence: query `social_listening.db` for `classifier_status='not_qualified'` rows and group by `rejection_reason` (and by `icp`/`author_role`/`intent_type`/`icp_score`/`intent_score`). Use a read-only script or a temporary test; do not modify app code.
5. Sample 5–10 rejected posts and judge whether the LLM's rejection was correct (genuine non-ICP) or a false negative (genuine ICP under-scored). Record the verdict in the plan's implementation notes.
6. Verify provider config: confirm `.env` values (`CODEX_EVERYWHERE_BASE_URL`, `CODEX_EVERYWHERE_MODEL`, `CODEX_EVERYWHERE_API_KEY`) match the log line (`openrouter.ai/api/v1`, `deepseek/deepseek-v4.1-flash`), and that a single manual `_request_batch` call returns the strict JSON schema. Do not log secrets.

**Phase 2 — Qualification gate + observability (depends on Phase 1 verdict)**
7. Implement the approved gate (decision D2). Default proposal: `is_qualified = icp in QUALIFYING_ICPS and author_role in QUALIFYING_ROLES | {"unknown"} and intent in QUALIFYING_INTENTS and confidence >= CONFIDENCE_THRESHOLD` (confidence = `(icp_score + intent_score) / 2`). Keep `rejection_reason` populated with the first failing condition.
8. If the diagnosis shows model under-scoring, calibrate `SYSTEM_PROMPT` (e.g., explicit scoring anchors: "icp_score ≥ 0.6 means the author is clearly an agency owner/founder/principal") and/or adjust thresholds — each change must be covered by a unit test and re-verified against the sampled posts.
9. Add a `rejection_reason` breakdown to `run_metrics` (counts per reason string) so future runs are observable without DB access.
10. Add tests: FR-2.2 gate matrix (qualified/not-qualified by enum + confidence), rejection-reason population, and an end-to-end storage/sync test (qualified outcome → `add_lead` → `get_unsynced_leads` → `sync_leads_to_notion` → `mark_as_synced`).

**Phase 3 — Adapter: error taxonomy + Facebook (opencli_adapter.py)**
11. Add `OpenCLIFetchError` and `OpenCLIAuthenticationError` exception classes.
12. Broaden 429 detection regex to also match `rate.?limit` and `status.?[: ]?429`; keep the existing negative-case tests passing (e.g., `post_id_429abc` must NOT match).
13. Add auth-pattern detection (conservative list: `c_user`, `cookie`, `login`, `log in`, `sign in`, `session`, `authenticate`, `not logged in`, `captcha`, `challenge`) and fetch-pattern detection (`Failed to fetch`, `fetch failed`, `ERR_`, `connection`, `timed out`, `timeout`) applied to combined stdout+stderr on nonzero returncode. Raise the corresponding typed error.
14. Add `_parse_retry_after(combined)` returning seconds when the CLI reports `Retry-After: N` or `retry after N` (bounded by `RATE_LIMIT_BACKOFF_MAX`).
15. Implement the Facebook timestamp fallback in `fetch_leads`: when `posted_at` is None and `platform in config.TIMESTAMP_FALLBACK_PLATFORMS`, set `posted_at = retrieved_at` and `posted_at_fallback = "retrieved_at"`. Preserve the drop behavior for all other platforms.
16. Add adapter tests: Facebook command construction (`opencli facebook search <q> --format json`, no `--subreddit`), timestamp fallback, auth detection, fetch detection, retry-after parsing, and regression tests for all existing Reddit/Twitter behavior.

**Phase 4 — Config: platforms, queries, subreddits, rate-limit constants (config.py)**
17. Add `"facebook"` to `PLATFORMS`.
18. Add `FACEBOOK_QUERIES` (decision D3) — proposal: reuse the four family keys with agency-first Facebook phrasing, e.g. `"recruitment agency BD"`, `"staffing agency client acquisition"`, `"ATS candidate matching"`, `"recruiter cold outreach"`, `"recruitment agency owners"`, `"staffing agency owners"`, `"independent recruiters network"`, `"recruiter business development"` (final list per decision D3).
19. Reconcile `LEAD_SUBREDDITS` per decision D1 (proposal: `["recruiting", "staffingagency", "agencyowners", "Entrepreneur", "smallbusiness", "freelanceRecruiters"]` — see D1 for the `staffing`/`Recruitment` question).
20. Tune rate-limit constants per decision D4 (proposal: `RATE_LIMIT_BACKOFF_MIN = 60`, `RATE_LIMIT_BACKOFF_MAX = 300`, `MAX_RATE_LIMIT_RETRIES = 3`); add `FETCH_RETRY_BACKOFF_MIN/MAX` (proposal 15–30 s) and `MAX_FETCH_RETRIES = 1`; add `TIMESTAMP_FALLBACK_PLATFORMS = ("facebook",)`.
21. Update `tests/test_discovery_queries.py` expectations (platforms, subreddits, `FACEBOOK_QUERIES` syntax/cardinality).

**Phase 5 — Runner: Facebook selection, auth halt, backoff/jitter (run.py)**
22. In `main`, select the query catalog per platform: `queries = config.FACEBOOK_QUERIES if platform == "facebook" else config.DISCOVERY_QUERIES`. Keep `communities = config.REDDIT_COMMUNITIES if platform == "reddit" else [None]`.
23. Replace `_rate_limit_cooldown()` with an attempt-aware exponential backoff + jitter: `cap = min(RATE_LIMIT_BACKOFF_MAX, RATE_LIMIT_BACKOFF_MIN * 2 ** (attempt - 1))`; `cooldown = random.uniform(min(RATE_LIMIT_BACKOFF_MIN, cap), cap)`; honor `_parse_retry_after` as a floor when present. Update the retry loop to pass `attempt`.
24. Add a `except OpenCLIAuthenticationError` branch: log actionable guidance, add the platform to `halted_platforms`, do not count it as a generic discovery error, continue other platforms.
25. Add a `except OpenCLIFetchError` branch: retry at most `MAX_FETCH_RETRIES` times with `FETCH_RETRY_BACKOFF_MIN/MAX` jitter, then record the error and continue (count toward `consecutive_discovery_errors`).
26. Add `rejection_reason` breakdown to `run_metrics` (populated from `record_outcome`).
27. Add runner tests: Facebook catalog selection, auth-halt (Facebook halted, Reddit continues), fetch retry, backoff growth/jitter bounds, rejection-reason metrics.

**Phase 6 — Verification**
28. Run focused tests (adapter, run, qualification, discovery_queries, resilience_repair), then the full suite.
29. Run a controlled `--dry-run` with a short lookback: verify Facebook command strings, timestamp fallback, auth guidance (if unauthenticated), no raw content/secrets in logs, and bounded work-item counts.
30. Run GitNexus change detection (`detect_changes --scope all`), inspect affected processes, check for cycles, and review the final diff to confirm only planned files changed.

---

## 10. Comprehensive Testing & Verification Plan

| Layer | Test | Gate |
| --- | --- | --- |
| Config | `PLATFORMS` order; `FACEBOOK_QUERIES` non-empty/unquoted/no `OR`/`AND`; reconciled `LEAD_SUBREDDITS`; rate-limit constants | exact-match assertions |
| Adapter — command | Facebook argv = `opencli facebook search <q> --format json`; no `--subreddit`; Reddit/Twitter argv unchanged | exact argv capture |
| Adapter — timestamp | Facebook post without timestamp retained with `posted_at == retrieved_at`, `posted_at_fallback == "retrieved_at"`; Reddit/Twitter post without timestamp still dropped | unit |
| Adapter — errors | 429 positive/negative matrix (existing + `rate limit`/`status: 429`); auth patterns → `OpenCLIAuthenticationError`; fetch patterns → `OpenCLIFetchError`; `Retry-After: 120` → 120 s; malformed JSON/empty output unchanged | unit |
| Qualification | FR-2.2 gate matrix (enum + confidence boundaries); `rejection_reason` populated with first failing condition; existing strict-JSON validation unchanged | unit |
| Runner | Facebook catalog selection; auth error halts Facebook only; fetch error retried once then recorded; 429 backoff grows with attempt and stays within bounds; `rejection_reason` in metrics | unit/integration |
| End-to-end | qualified outcome → `add_lead` → `get_unsynced_leads` → `sync_leads_to_notion` → `mark_as_synced` | integration (tmp DB) |
| Regression | full suite green; redaction/monotonic-evidence tests in `test_resilience_repair.py` unchanged | full suite |
| Operational smoke | `--dry-run` short lookback; inspect command strings, counts, logs for secrets | manual |

---

## 11. Edge Cases

- **429 text without the word 429** (e.g., "rate limit exceeded", "too many requests") — covered by broadened regex; negative cases (`post_id_429abc`, `4299 items`) must stay non-matching.
- **`Retry-After` absent or unparseable** — fall back to exponential+jitter; cap at `RATE_LIMIT_BACKOFF_MAX`.
- **Facebook post with a real (parseable) timestamp** — used as-is; fallback not applied.
- **Facebook post with no ID** — still skipped (unchanged).
- **Facebook returns empty output / JSON lines / top-level object** — existing parsing paths handle it.
- **Auth failure mid-run after some queries succeeded** — Facebook halts; Reddit/Twitter continue; `consecutive_discovery_errors` not polluted by auth errors.
- **Fetch failure on the last retry** — recorded as an error, run continues; platform halts only after the generic consecutive-error bound.
- **Duplicate Facebook posts across queries** — `post_id` dedup (first-seen provenance) unchanged.
- **LLM returns valid JSON but all `not_qualified`** — the new `rejection_reason` metric makes the cause visible; the gate change (D2) is the corrective lever.
- **LLM returns malformed JSON / provider error** — existing `unclassified`/`provider_error` + retry path unchanged.
- **`opencli facebook search --help` unavailable or different syntax** — implementation blocker; stop and raise for review.

---

## 12. Consequence Scan

- **Gate change (D2) alters what qualifies.** If the enum-based gate is stricter than today's numeric gate, `llm_qualified` could stay low or drop further; if looser, precision could drop. Mitigation: diagnosis first, gate tests, `rejection_reason` metrics, and a 14-day audit per REQUIREMENTS.md §2.3.
- **Adding Facebook increases request volume and platform surface.** Mitigation: bounded `FACEBOOK_QUERIES` catalog, existing pacing, platform-local halt, read-only posture, manual group monitoring (FR-1.2).
- **Timestamp fallback could admit stale posts.** Mitigation: scoped to `TIMESTAMP_FALLBACK_PLATFORMS`, `post_id` dedup, and `posted_at_fallback` provenance for audit.
- **Backoff constant changes affect test expectations and operational cadence.** Mitigation: update tests in the same change; keep bounds explicit in config.
- **Auth-error detection false positives** (e.g., a post containing the word "login"). Mitigation: conservative pattern list, applied only on nonzero returncode, and unit-tested negative cases.
- **Provider/model behavior is external.** The qualification fix cannot guarantee the model's calibration; the plan adds observability (rejection-reason metrics) and a manual verification step so drift is visible.
- **No schema/Notion changes** — persistence and sync contracts are preserved; the only new field is in-memory provenance.

---

## 13. Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| OpenCLI Facebook command shape differs from assumption | Verify `--help` in Phase 0; blocker if different |
| LLM gate change ships without diagnosis | Phase 1 diagnosis is mandatory before Phase 2 |
| Facebook auth detection misses a new failure mode | Conservative patterns + clear guidance + platform-local halt; no crash path |
| Rate-limit tuning increases platform risk | Bounded retries, jitter, `Retry-After` honor, halt after exhaustion; read-only posture |
| Test suite drift from constant changes | Update config tests in the same commit as constants |
| Index staleness masks callers | Refresh GitNexus and re-run impact before editing |

---

## 14. Rollback Notes

- **Config-only rollback:** revert `PLATFORMS`, `FACEBOOK_QUERIES`, `LEAD_SUBREDDITS`, and rate-limit constants in `config.py`; Facebook work items disappear and Reddit/Twitter behavior returns to the prior catalog.
- **Adapter rollback:** revert `opencli_adapter.py` to the prior commit; the new exception types and timestamp fallback are additive and do not affect Reddit/Twitter parsing.
- **Runner rollback:** revert `run.py`; the prior single-retry uniform-cooldown behavior is restored.
- **Gate rollback:** revert `qualification.py` `validate_classification`; existing rows are unaffected (monotonic retention invariant prevents downgrades), and new runs use the numeric gate again.
- Do not roll back unrelated scheduler, logging, database, or Notion changes. The worktree must remain clean and reviewed before any commit.

---

## 15. Decisions Approved by User

- **D1 — Subreddit reconciliation.** Approved unified list: `["recruiting", "staffing", "staffingagency", "agencyowners", "freelanceRecruiters", "Entrepreneur"]` (with `Entrepreneur` monitored for precision).
- **D2 — LLM qualification gate.** Approved pragmatic enum + confidence gate: `icp ∈ {"recruitment_agency", "independent_recruiter"}` AND `author_role ∈ {"owner", "founder", "principal", "headhunter", "independent_recruiter", "unknown"}` AND `intent ∈ {"buying", "pain", "advice"}` AND `confidence ≥ 0.60`. Qualified leads are stored in SQLite without blocking on Notion sync verification.
- **D3 — Facebook query catalog.** Approved agency-first commercial queries: `"recruitment agency BD"`, `"staffing agency client acquisition"`, `"recruitment agency owners"`, `"staffing agency owners"`, `"ATS candidate matching"`, `"recruiter cold outreach"`.
- **D4 — Rate-limit budget.** Approved `RATE_LIMIT_BACKOFF_MIN = 60`, `RATE_LIMIT_BACKOFF_MAX = 300`, `MAX_RATE_LIMIT_RETRIES = 3`, `MAX_FETCH_RETRIES = 1`, `FETCH_RETRY_BACKOFF_MIN/MAX = 15/30`, with `Retry-After` header parsing.
- **D5 — Timestamp fallback scope.** Approved scoping the `retrieved_at` fallback strictly to Facebook via `TIMESTAMP_FALLBACK_PLATFORMS = ("facebook",)`.

---

## 16. Definition Of Done

- Phase 0 preconditions met (index refreshed, OpenCLI Facebook contract verified, baseline tests captured).
- Phase 1 diagnosis recorded with a verdict on why `llm_qualified: 0` occurred.
- Approved gate (D2) implemented with tests; `rejection_reason` metrics in `run_metrics`.
- Facebook end-to-end: platform in `PLATFORMS`, `FACEBOOK_QUERIES` defined, adapter supports Facebook with timestamp fallback and typed auth/fetch errors, runner selects the Facebook catalog and halts only Facebook on auth failure.
- Rate-limit/fetch handling improved with exponential+jitter backoff, `Retry-After` support, bounded fetch retry, and platform-local halt.
- `LEAD_SUBREDDITS` reconciled per D1.
- Focused and full test suites pass; operational `--dry-run` smoke check confirms bounded work items, correct command strings, and safe logs.
- GitNexus change detection and final diff review show only planned files changed.
- Tushar explicitly approved this plan.

---

**APPROVAL_STATUS: APPROVED_BY_USER**

Implementation is unblocked to begin.