# ENHANCEMENT_PLAN: Broaden Conversational Social-Listening Discovery Queries

**Date:** 2026-09-10  
**Repository:** `/Users/tusharmangla/RecruitmentOS/social_listening`  
**Scope:** RecruitmentOS sales / marketing / product social listening  
**Status:** Pending explicit Tushar approval before implementation  
**Process tier:** Medium. This changes an external search contract and the discovery catalog, while preserving the existing qualification, persistence, and rate-limit pipeline.

## Goal

Increase relevant lead discovery in the 24-hour Reddit/Twitter loop by replacing rigid phrase-quoted searches with natural keyword matching. Reddit currently receives queries such as `"recruitment agency" "getting clients"`; the planned catalog will use unquoted conversational terms such as `recruitment agency getting clients`, allowing platform search to match natural founder discussions where the words are present but not adjacent or verbatim as a phrase.

The change must preserve the bounded work-item model, platform/community scoping, timestamp filtering, post-ID deduplication, stage-one qualification gate, LLM qualification, SQLite persistence, retry processing, optional Notion sync, and existing rate-limit safeguards.

## Current Findings

- `listening_loop/config.py:DISCOVERY_QUERIES` defines four families and 12 scheduled query strings, but every string contains two rigid quoted phrases.
- `listening_loop/run.py:main` expands each query independently: Reddit runs every query once per configured community; Twitter runs every query once with `community=None`. With the current four communities, the all-platform schedule is 48 Reddit calls plus 12 Twitter calls.
- `listening_loop/opencli_adapter.py:run_opencli` passes the query string directly to `opencli <platform> search <query>`, adding Reddit `--sort new`, verified `--subreddit <community>`, and `--format json`. It does not add quotes, `OR`, or other search syntax centrally.
- `listening_loop/opencli_adapter.py:fetch_leads` accepts one query at a time, rejects multi-query lists, invokes the adapter, filters out missing IDs and posts outside the lookback window, and emits canonical lead fields plus `platform`, `community`, `query_family`, `exact_query`, and UTC `retrieved_at`.
- `run.main` locally filters content with `is_qualified_candidate`: excluded terms reject a post, then qualifying terms admit it to the existing classification pipeline. Query broadening therefore increases recall without making the LLM or persistence path accept unfiltered results.
- The current worktree is dirty. Existing uncommitted changes touch `config.py`, `opencli_adapter.py`, `run.py`, and related tests/scripts. Implementation must reconcile those changes and must not overwrite unrelated user work.
- GitNexus impact analysis was run before planning. `fetch_leads` and `run_opencli` each returned `MEDIUM` risk with exact coverage because the runner and multiple tests depend on them; `main` returned `MEDIUM` risk. The affected execution flow is `main`; no HIGH/CRITICAL finding was returned. The implementation should refresh the index and repeat impact analysis because the repository index may lag the current worktree.

## Assumptions

- `config.PLATFORMS` remains `['reddit', 'twitter']` unless an operator explicitly selects one platform through the existing CLI.
- The existing four lead communities remain in scope: `recruiting`, `staffing`, `Recruitment`, and `freelanceRecruiters`.
- The same natural-language query string is valid for both Reddit and Twitter OpenCLI search. If installed OpenCLI help demonstrates platform-specific syntax, add an explicit per-platform mapping only after review; do not silently transform or quote queries in the adapter.
- The existing `INTER_QUERY_SLEEP_MIN/MAX` values of 3-7 seconds, `RATE_LIMIT_BACKOFF_MIN/MAX` values of 60-90 seconds, and one retry remain the rate-limit budget unless operational evidence requires a separately approved change.
- Search results remain read-only discovery data. No publishing, engagement, account action, proxy rotation, CAPTCHA bypass, or rate-limit evasion is in scope.

## Non-Goals And Invariants

- Do not change `QUALIFYING_KEYWORDS`, `EXCLUDED_KEYWORDS`, `is_qualified_candidate`, the LLM prompt, provider, model, parser, batching, or fallback behavior.
- Do not change SQLite tables, unique identity (`post_id`), migrations, database constraints, Notion properties, or synchronization behavior.
- Do not introduce concurrent workers, unbounded retries, a larger catalog, an aggregate `OR` query, or a second search path.
- Do not modify the legacy `fetch_and_sync_real_leads.py` flow.
- Do not change scheduler files or environment/credential setup as part of this query-recall fix.

## Query Catalog Decision

Retain four intent families and 12 total scheduled queries, but remove all rigid quote characters. The catalog should be deterministic and contain no `"` characters and no generated `OR` expressions:

```python
{
    "agency_client_acquisition": [
        "recruitment agency getting clients",
        "staffing agency client acquisition",
        "recruitment business new business",
    ],
    "agency_pipeline_pain": [
        "recruitment agency need more clients",
        "staffing agency pipeline is dry",
        "recruitment business job flow",
    ],
    "agency_outbound": [
        "recruitment agency cold email",
        "staffing agency linkedin outreach",
        "recruitment business outbound sales",
    ],
    "agency_operations": [
        "recruitment agency candidate database",
        "staffing agency ATS automation",
        "recruitment agency CRM automation",
    ],
}
```

This keeps agency identity and commercial pain in every query, so recall improves without reverting to the previous broad catalog of dozens of standalone terms. The unchanged stage-one gate remains the final local recall/precision guard before LLM spend.

## User Journeys

1. An operator runs the existing all-platform command. The runner executes the 12 catalog entries in family/query order, first across Reddit communities and then on Twitter, preserving current platform order and pacing.
2. A Reddit founder writes natural prose such as “How are recruitment agencies getting clients?” or “our staffing pipeline is dry.” The unquoted query can match the terms without requiring the exact quoted phrase; the result then goes through existing lookback, dedupe, exclusion, qualifying-keyword, LLM, and storage gates.
3. A Twitter result matches the same natural query. The adapter sends the exact unquoted string to Twitter without a Reddit community option and retains `community=None` in provenance.
4. The same post matches several query/community work items. The runner counts duplicate occurrences and sends the first-seen post ID through classification only once.
5. A query returns no results, malformed output, a timeout, or an HTTP 429. The existing isolated error, pacing, cooldown, retry, and platform-local halt behavior remains bounded and observable; broadening the catalog must not create retry storms.
6. An operator runs with `--platform reddit` or `--platform twitter`; only that platform’s existing work-item set runs, with no cross-platform behavior change.

## Acceptance Criteria

1. `DISCOVERY_QUERIES` contains exactly four existing family keys and exactly 12 queries matching the catalog in this plan and in deterministic order.
2. Every scheduled query is a non-empty string with no double quote character and no ` OR ` token. No adapter or runner code adds quoting or aggregation.
3. The 12 queries retain agency-specific identity and commercial-intent terms; the six broad family structure is not reintroduced.
4. `run.main` still creates `12 * 4 = 48` Reddit work items and 12 Twitter work items for an all-platform run. Twitter calls receive `community=None`; Reddit calls receive only configured lead communities.
5. `run_opencli` receives and places each query unchanged in the command for Reddit and Twitter. Reddit still uses documented subreddit scoping and Twitter never receives `--subreddit`.
6. `fetch_leads` continues to reject multi-query lists, preserve canonical/provenance fields, skip missing IDs and stale/unparseable timestamps, and enforce the configured lookback window.
7. Existing local filtering behavior is unchanged: excluded content is rejected, qualifying content is admitted, and no post reaches the LLM solely because the search query was broadened.
8. Cross-query and cross-community duplicate posts are removed by `post_id` before classification, with first-seen provenance retained and duplicate metrics reported as before.
9. Existing 3-7 second inter-query pacing, 60-90 second 429 cooldown, one retry, platform-local halt, generic failure bounds, dry-run behavior, database persistence, retries, and Notion behavior remain passing and bounded.
10. Tests assert both positive conversational examples and negative syntax regressions, including that the old rigid quoted catalog is absent from scheduled configuration.

## Affected Components And Files

| File | Symbols / responsibility | Planned treatment |
| --- | --- | --- |
| `listening_loop/config.py` | `DISCOVERY_QUERIES`, `LEAD_SUBREDDITS`, pacing constants | Replace only the 12 query strings with the approved unquoted catalog. Preserve communities and current pacing/rate-limit bounds. Reconcile existing dirty changes. |
| `listening_loop/opencli_adapter.py` | `run_opencli`, `fetch_leads`, `OpenCLIRateLimitError`, timestamp/normalization helpers | Characterize and, only if needed, adjust tests or a small contract guard to ensure query pass-through. Preserve command syntax, errors, parsing, time filtering, and provenance. No per-platform quote insertion. |
| `listening_loop/run.py` | `main`, `_pace_between_attempts`, `_rate_limit_cooldown`, `is_qualified_candidate`, dedupe/report logic | No behavioral redesign expected. Verify work-item expansion and preserve current rate-limit implementation while reconciling dirty changes. Add guards only if needed to enforce bounded catalog/work items. |
| `tests/test_discovery_queries.py` | Configuration, schedule cardinality, provenance, dedupe/report tests | Update expected catalog and assertions from quoted to unquoted strings; add syntax and conversational coverage; retain 48 Reddit/12 Twitter and exact-order assertions. |
| `tests/test_opencli_adapter.py` | OpenCLI command and lead normalization tests | Change fixtures to natural queries and explicitly assert exact pass-through, no quotes added, no `OR`, unchanged Reddit/Twitter flags, and existing filtering/error behavior. |
| `tests/test_run.py` | Runner scheduling, filtering, dedupe, retries, reports | Update query fixtures/comments where needed; preserve and extend schedule, duplicate, pacing, 429, generic failure, and downstream pipeline assertions. |
| `tests/test_resilience_repair.py` | Resilience fixtures around adapter/runner | Update only query literals or expected scheduling values affected by the catalog; retain sanitization and resilience assertions. |
| `listening_loop/qualification.py`, `database.py`, `notion_sync.py` | Downstream contracts | No changes planned; verify diff remains clean. |

## Frontend, API, Database, And Data Contract

- **Frontend:** None. This is a scheduled worker configuration and discovery change.
- **HTTP API:** None. OpenCLI is an external subprocess boundary, not an application route.
- **Discovery command contract:** one exact query string per `run_opencli` invocation; Reddit adds only its documented community scope; Twitter remains global.
- **Normalized lead contract:** preserve `post_id`, `source`, `content`, `url`, `posted_at`, `author`, `platform`, `community`, `query_family`, `exact_query`, and UTC `retrieved_at`.
- **Filtering contract:** preserve lookback filtering, missing-ID rejection, post-ID dedupe, excluded-keyword rejection, qualifying-keyword admission, and downstream classification limits.
- **Database:** no entity, column, index, migration, permission, or constraint change. Existing `post_id` uniqueness remains the persistence backstop.
- **Notion:** no new properties or mapping changes. Query provenance remains transient/report-level data.

## Schema Or Migration Approach

No schema or migration is required. The only persisted values are existing lead fields accepted by the current SQLite and Notion paths. `exact_query` and related provenance remain in-memory normalized/report data unless the existing implementation already carries them transiently; do not add persistence columns for this change.

## Implementation Sequence

1. Preserve and inspect the dirty worktree. Refresh GitNexus if stale, then rerun upstream impact for `fetch_leads`, `run_opencli`, and `main` before source edits. Record any changed risk or newly discovered caller.
2. Confirm installed OpenCLI search behavior with non-sensitive `opencli --version`, `opencli reddit search --help`, and `opencli twitter search --help`. Confirm that unquoted strings are accepted as ordinary query arguments and that Reddit community scoping remains documented. Stop implementation if the installed CLI requires a different syntax; raise that as a review blocker rather than guessing.
3. Update `tests/test_discovery_queries.py` expected configuration first. Assert exact family/query order, no quotes, no `OR`, 48 Reddit items, 12 Twitter items, and unchanged qualification/exclusion constants.
4. Update `listening_loop/config.py` with only the approved unquoted catalog. Preserve current communities, platform order, pacing, cooldown, retry, and all unrelated user changes.
5. Update adapter tests with natural query fixtures. Assert query equality at the subprocess boundary for both platforms and retain tests for scope verification, typed 429 detection, malformed JSON, timestamp parsing, missing IDs, and list rejection.
6. If tests expose a query transformation or unsafe expansion, make the smallest adapter/runner correction needed to enforce one-query-per-call and the existing bounds. Do not add a second query formatter or platform-specific behavior without documenting and testing the operational reason.
7. Update runner tests for natural query strings, schedule cardinality/order, duplicate handling, stage-one filtering, query-level reporting, pacing, retry/cooldown, platform-local halt, generic failure isolation, dry-run, and downstream retry behavior. Do not alter qualification/database/Notion implementations.
8. Run focused discovery/adapter/runner/resilience tests, then the complete test suite. Record failures caused by pre-existing dirty changes separately from failures caused by this plan.
9. Run a controlled dry-run with a short lookback and safe instrumentation. Verify command strings contain no rigid quote syntax or generated `OR`, expected work-item counts, no overlapping execution, no raw content/secrets in logs, and immediate stop/reassessment on repeated 429 or login challenge.
10. Run GitNexus change detection for all worktree changes, inspect affected processes, check for cycles if available, and review the final diff to ensure only the planned application files and tests changed during implementation. This step occurs after implementation, not during this planning turn.

## Test Plan And Verification Strategy

- **Configuration unit tests:** exact catalog equality; four families; 12 queries; all queries unquoted, non-empty, and non-aggregated; communities and platform order unchanged; query cardinality remains bounded.
- **Command-construction tests:** capture subprocess argv and assert the exact natural query occupies the search argument; Reddit includes `--sort new`, documented `--subreddit`, and JSON output; Twitter includes JSON output and no subreddit flag.
- **Normalization tests:** verify provenance carries the exact unquoted query and family, while recent results are retained and stale/missing-ID/invalid-timestamp results are skipped.
- **Runner integration tests:** assert deterministic 48 Reddit plus 12 Twitter work items, platform-specific community values, first-seen dedupe across overlapping work items, unchanged stage-one filtering, and report counts.
- **Rate-limit regression tests:** preserve one retry after a typed 429, 60-90 second cooldown, no tight loop, platform-local halt after exhausted retry, and continuation of another platform where current behavior specifies it.
- **Full regression suite:** run the repository’s complete test command after focused tests. The expected baseline should be taken from the current checkout rather than assuming the prior plan’s historical count, because the worktree already contains uncommitted changes.
- **Operational smoke check:** run a single controlled platform first, then all-platform only if syntax and authentication checks pass. Do not treat zero leads alone as a test failure; inspect retrieved counts, query report, filters, and command syntax to distinguish search recall from downstream qualification.

## Risks And Mitigations

- **Search engine semantics differ by platform:** verify both OpenCLI help/contracts and assert exact argv per platform. If syntax differs, use a reviewed explicit mapping rather than silently passing incompatible syntax.
- **Recall improves but noise increases:** retain the existing agency/commercial terms, stage-one exclusion/qualification filters, and LLM classifier. Measure retrieved, deduplicated, stage-one-passed, and qualified counts separately.
- **Expanded matches increase request/result volume:** keep 12 queries, four communities, sequential execution, 3-7 second jitter, 60-90 second cooldown, and one retry. Do not increase catalog size in this change.
- **Rigid quotes may have been intentional for a provider:** make the behavior change explicit in tests and smoke verification. Roll back the catalog if platform results show syntax errors or unacceptable noise.
- **Dirty worktree could mask regressions:** preserve all pre-existing edits, refresh/index-check before implementation, and review diffs and test failures by ownership.
- **External rate limits or authentication challenges:** stop on repeated 429, CAPTCHA, or login challenge; do not bypass controls or retry aggressively.

## Rollback Notes

Rollback is configuration-only if no supporting guard is needed: restore the prior 12 quoted query strings in `DISCOVERY_QUERIES` while retaining the existing adapter/runner behavior. If implementation discovers and changes a pass-through guard or test contract, revert those source changes together with the catalog change. Do not roll back unrelated scheduler, logging, qualification, database, or Notion worktree changes.

## Decisions Requiring Review

1. Approve the exact 12 unquoted query strings and the decision to retain four families and four Reddit communities.
2. Confirm that natural keyword matching is desired for both Reddit and Twitter, subject to installed OpenCLI syntax verification.
3. Confirm that the existing 3-7 second pacing, 60-90 second cooldown, one retry, and 60 all-platform first-attempt bound remain the operational limits.
4. Confirm that no schema/report persistence is desired; query provenance remains transient and existing normalized fields are preserved.

## Definition Of Done

- The exact approved unquoted catalog is implemented and covered by tests.
- Reddit and Twitter receive unchanged, platform-compatible query arguments with no aggregate `OR` construction or rigid quote insertion.
- Existing filtering, dedupe, qualification, persistence, retry, sync, pacing, and rate-limit behavior is verified unchanged.
- Focused and full tests pass, and a controlled smoke check confirms expected bounded work-item counts and safe logs.
- GitNexus impact/change analysis and final diff review show no unplanned affected components or scope violations.
- Tushar explicitly approves this exact plan before any application source or test implementation begins.

**APPROVAL_STATUS: PENDING_USER_REVIEW**

**STOP: Review the plan with Tushar. Do not start implementation until Tushar explicitly approves this exact plan in a later message.**
