# FEATURE_PLAN: LLM Qualification and Pipeline Resilience

**Date:** 2026-09-05  
**Repository:** `/Users/tusharmangla/RecruitmentOS/social_listening`  
**Mode:** `FEATURE_PLANNING`  
**Status:** Pending explicit user approval before implementation

## Evidence Gate

`EVIDENCE_GATE: PASS`

The provider-configuration blocker in the prior plan is resolved by direct,
non-secret inspection of `/Users/tusharmangla/.config/opencode/opencode.json`.
The active provider is `codex-everywhere`, implemented through
`@ai-sdk/openai-compatible`, with base URL `https://codex-easy.ai/v1`, API-key
environment variable `CODEX_EVERYWHERE_API_KEY`, and configured model ID
`gpt-5.6-luna` (`GPT-5.6 Luna`). The transport is therefore OpenAI-compatible;
the implementation must construct the provider-specific chat-completions URL
from the configured base URL rather than retain the obsolete guessed Luna URL.

No secret value was read or recorded. The repository's ignored `.env` was
searched only for relevant variable names and does not establish a conflicting
OpenCode/Codex Everywhere provider configuration. The repository's `.env.example`
files contain Notion settings only. No Muse Spark 1.3 configuration was found in
the inspected OpenCode configuration or repository environment examples.

"Free model" is a user decision for provider selection, not a verified pricing
claim in local configuration. This plan uses the verified configured model
`codex-everywhere/gpt-5.6-luna`; billing, quota, and entitlement must be
confirmed operationally outside source control before enabling scheduled runs.

## Goal

Improve RecruitmentOS social-listening lead precision and resilience using a
two-stage qualification pipeline: deterministic keyword pre-filtering followed
by LLM qualification through the configured OpenCode-compatible provider. Keep
SQLite as the single durable source of truth, retain qualified leads
monotonically, and preserve optional Notion synchronization.

## Assumptions and Non-Goals

**Assumptions**

- The canonical scheduled path remains `listening_loop.run` and continues to
  collect OpenCLI posts, apply lookback/platform filtering, write SQLite, then
  optionally synchronize to Notion.
- The current configured `codex-everywhere` gateway accepts OpenAI-compatible
  requests at `{baseURL}/chat/completions` using `Authorization: Bearer` with
  `CODEX_EVERYWHERE_API_KEY`. The adapter will isolate this detail and validate
  the actual response envelope at runtime/tests.
- The user-selected qualification threshold remains confidence `>= 0.60`.

**Explicit non-goals**

- Do not change `listening_loop/fetch_and_sync_real_leads.py`.
- Do not add webhooks, alerts, bad-lead cleanup, deletion, archival, a
  dead-letter store, or a second persistence system.
- Do not build a frontend or HTTP API.
- Do not introduce Gemini, Muse Spark, or another provider/model as a fallback.

## Current Behavior and Affected Components

The active path is `listening_loop/run.py -> opencli_adapter.py -> database.py
-> notion_sync.py`. GitNexus reports `run.main` has one direct upstream caller
and low current graph risk; the index predates current worktree changes, so it
must be refreshed before implementation consequence scanning.

| File/component | Planned responsibility |
|---|---|
| `listening_loop/run.py` | Preserve keyword gate and orchestrate LLM classification, durable state transitions, counters, and Notion sync. |
| `listening_loop/classifier.py` or provider adapter module | Resolve runtime provider settings, make bounded batch requests, strictly parse results, classify provider/response failures, and redact diagnostics. |
| `listening_loop/config.py` | Load dotenv/runtime configuration without import-time environment snapshots; expose only non-secret setting names/defaults. |
| `listening_loop/database.py` | Perform idempotent `leads` migration, monotonic upserts, error/attempt persistence, qualified-only sync selection, and bounded retry selection. |
| `listening_loop/notion_sync.py` | Map canonical durable classification values to existing Notion properties and mark sync success only after success. |
| `listening_loop/opencli_adapter.py` | Preserve and test safe OpenCLI normalization, subprocess timeout/nonzero/malformed-output handling, and continuation by platform. |
| `.env.example`, `listening_loop/.env.example`, `README.md`, `listening_loop/SETUP.md` | Document verified non-secret Codex Everywhere setting names, canonical pipeline, state/retry behavior, and the unchanged RSS helper. |
| `tests/test_classifier.py`, `tests/test_database.py`, `tests/test_run.py`, focused new/updated tests | Establish feature acceptance and regression coverage using synthetic posts and mocked provider/Notion boundaries. |

`fetch_and_sync_real_leads.py` is a separate RSS-to-Notion utility that bypasses
the canonical CLI, SQLite, and classifier. It is deliberately unaffected.

## User Journeys

1. An operator runs `venv/bin/python -m listening_loop.run` manually or via the
   existing scheduler.
2. OpenCLI posts are normalized and filtered by existing excluded and qualifying
   keyword rules. Rejected posts do not invoke the LLM.
3. Keyword survivors are batched with bounded content and sent to
   `codex-everywhere/gpt-5.6-luna` through the isolated provider adapter.
4. A valid ICP-qualified result is persisted to SQLite before any Notion call.
   A later process invocation can sync it after an outage.
5. Invalid output and provider failures are retained with status, bounded error,
   attempt count, and due retry metadata. They do not enter the qualified Notion
   queue.
6. A previously qualified lead remains qualified and, if unsynced, syncable even
   if a subsequent classification attempt fails or returns a negative result.

## Qualification Contract

The LLM returns one result per input post with `id`, `icp`, `author_role`,
`intent`, `urgency`, `one_line`, and `confidence`. Results must be JSON-schema
validated, correlated to input IDs exactly once, and rejected as `unclassified`
when malformed, incomplete, unknown, duplicate, or type-invalid.

Qualification requires all of:

- `author_role` is `owner`, `founder`, `principal`, `headhunter`, or
  `independent_recruiter`.
- `icp` is `recruitment_agency` or `independent_recruiter`.
- `intent` is `buying` or `pain`.
- `confidence >= 0.60`.

The prompt and validation must include these exclusions: job seekers, resume
advice, internal HR/recruiters hiring directly, generic agencies without
recruitment-agency ICP evidence, developers, freelancers, employers, and
unrelated users. `unknown` role is retained as `not_qualified`; it is not a
qualified escape hatch. This resolves the earlier undecided policy.

## Frontend, API, and Database Contracts

There is no frontend or HTTP API. The CLI/SQLite/Notion data contract is:

| Classifier field | Canonical SQLite/internal field | Existing Notion property | Rule |
|---|---|---|---|
| `id` | `post_id` | none | Must match the source post and existing unique identity. |
| `icp` | `icp` | none | Persist for audit; do not add a Notion property. |
| `author_role` | `author_role` | `Author Role` | Validated enum only. |
| `intent` | `intent_type` | `Intent Type` | Explicit rename. |
| `urgency` | `urgency` | `Urgency` | Validated enum only. |
| `one_line` | `summary` | `Summary` | Persist the model's bounded summary. |
| `confidence` | `confidence` | none | Persist; do not derive `Score`. |
| deterministic keyword score | `keyword_score` | `Score` | Preserve existing deterministic score semantics only. |
| deterministic outreach | `outreach_draft` | `Cold Outreach Draft` | Do not represent it as model output. |

Retain source fields `post_id`, `source`, `content`, `url`, and `posted_at` as
authoritative raw capture data. Retain all existing Notion property names and
`synced_to_notion_at` semantics.

## SQLite Schema and Migration

Adopt Option A: an idempotent migration on the existing `leads` table. SQLite
remains the only source of truth; no JSON, CSV, or additional database is added.

Add nullable enrichment/state columns after `PRAGMA table_info(leads)` guards:

- `classifier_status`: `qualified`, `not_qualified`, `unclassified`, or
  `provider_error`.
- `icp`, `author_role`, `intent_type`, `urgency`, `confidence`, `summary`,
  `keyword_score`, and `outreach_draft`.
- `classification_attempts`, `last_classification_attempt_at`, and
  `classified_at`.
- `classifier_error_category`, `classifier_error_message`, and
  `next_classification_retry_at`.
- `classifier_provider` containing the non-secret label `codex-everywhere`.

The migration preserves every existing row, `post_id UNIQUE`, and nullable
`synced_to_notion_at`; it must safely run twice. New keyword survivors and due
`provider_error`/`unclassified` rows are selected with a per-run batch cap and
backoff. `not_qualified` rows are retained but not retried unless manually
requeued by a future approved feature.

**Monotonic retention invariant:** a qualified row, whether synced or unsynced,
cannot be changed to a negative/error status by a later attempt. A later failure
may increment attempt/error metadata only. Valid enrichment may fill deliberately
missing values without erasing qualified evidence or `synced_to_notion_at`.

## Error States and Permissions

No new user permissions are introduced. Existing local filesystem access,
OpenCLI access, `CODEX_EVERYWHERE_API_KEY`, and optional Notion credentials
govern execution. Error treatment is:

- Missing provider configuration, connection/timeouts, 429, and 5xx: persist
  `provider_error`, schedule bounded retry, continue processing other work.
- Invalid/malformed/unmappable provider response: persist `unclassified` with a
  bounded redacted diagnostic; do not qualify or sync.
- OpenCLI timeout, missing executable, nonzero exit, or malformed output:
  warn/error for that platform and continue remaining platforms.
- Missing Notion credentials: collection/classification succeeds locally;
  eligible rows remain unsynced.
- Per-lead Notion error: retain the qualified row and leave it unsynced.

Logs must never emit API keys, authorization headers, query-string credentials,
or full social-post content. Prompt content, diagnostic messages, batch size,
request timeout, retry cap, and exponential-backoff limits are bounded constants
covered by tests.

## Implementation Sequence

1. Refresh GitNexus at the implementation `HEAD`; run impact analysis for each
   edited application symbol and record callers/processes before edits.
2. Add acceptance tests for keyword short-circuit, full ICP matrix, strict
   response validation, and the no-downgrade invariant before implementation.
3. Add runtime dotenv/config resolution for `CODEX_EVERYWHERE_API_KEY`,
   `https://codex-easy.ai/v1`, and `gpt-5.6-luna`; retain configuration injection
   in tests and avoid secrets in docs/logs.
4. Implement/adjust the provider adapter to use the OpenAI-compatible endpoint,
   bearer authorization, bounded batch request, strict parser, redaction, and
   classified retryable/non-retryable errors.
5. Implement the guarded SQLite migration and access methods, including
   monotonic upsert behavior, attempts/errors, due retries, and qualified-only
   Notion selection.
6. Wire the classifier after the existing keyword gate in `run.main`, persist
   results before Notion, and preserve dry-run, lookback, platform, and
   continuation semantics.
7. Keep Notion property mapping compatible with canonical durable fields and
   successful-sync-only timestamp marking.
8. Update dependency/docs/examples with verified non-secret provider settings;
   document the unchanged separate RSS utility.
9. Run focused and full tests, compile/import checks, schema upgrade checks, and
   GitNexus change analysis. Do not call live provider or Notion services in CI.

## Acceptance Criteria and Test Plan

1. Excluded-keyword and below-threshold posts never call the provider.
2. Requests use `codex-everywhere/gpt-5.6-luna` via the verified configured
   base URL and `CODEX_EVERYWHERE_API_KEY`; no Gemini/Muse configuration appears.
3. Owner, founder, principal, headhunter, and independent recruiter with allowed
   ICP/intent/confidence qualify; `unknown` and every specified exclusion do not.
4. Confidence `0.60` qualifies and lower values do not; buying/pain qualify,
   advice/job-search/other do not.
5. `PRAGMA table_info(leads)` verifies the migration, second initialization is
   idempotent, existing rows/unique identity/sync timestamps remain intact.
6. A qualified row remains qualified and syncable after later provider-error,
   malformed, unclassified, and not-qualified outcomes, including reverse-order
   regression tests.
7. Error/unclassified rows retain bounded diagnostics and obey retry cap/backoff;
   they are not sent to Notion.
8. SQLite persistence occurs before Notion; Notion failures and absent
   credentials preserve unsynced qualified rows and do not block other rows.
9. OpenCLI object/list/JSON-lines/empty/malformed/nonzero/missing/timeout paths
   do not crash the overall run.
10. `--dry-run`, scheduler entrypoint, deduplication, lookback/platform filters,
    and the unchanged `fetch_and_sync_real_leads.py` behavior remain covered.
11. Tests use mocked external clients and synthetic posts; redaction tests prove
    no API key, authorization header, URL query secret, or full post is logged.
12. Execute `venv/bin/python -m pytest -q`, an import/compile check, and
    `gitnexus_detect_changes(scope="all")`; incomplete/truncated graph output is
    not accepted as clean verification.

## Risks and Rollback

Risks are provider contract drift, quota/cost availability, prompt injection,
misclassification, migration compatibility, retry storms, Notion schema drift,
and accidental disclosure in diagnostics. Mitigate through the adapter boundary,
strict schema validation, keyword-first filtering, bounded requests/retries,
redaction, nullable idempotent schema evolution, synthetic fixtures, and
qualified-only sync selection.

Rollback disables classification through the approved configuration switch or
reverts application wiring while preserving SQLite rows and backward-readable
columns. Never delete classification evidence, alter the RSS helper, or run
cleanup during rollback.

## Decisions Recorded and Review Items

Recorded decisions:

- Provider/model: `codex-everywhere/gpt-5.6-luna`, `https://codex-easy.ai/v1`,
  `CODEX_EVERYWHERE_API_KEY`; local config does not prove pricing is free.
- Persistence: Option A idempotent SQLite migration on `leads`.
- Qualification: keyword pre-filter then LLM; strict RecruitmentOS ICP and
  `unknown` is not qualified.
- Invariants: preserve `fetch_and_sync_real_leads.py`; defer webhooks and
  bad-lead cleanup.

Review items requiring explicit approval:

- The exact planned migration columns/status values and bounded retry policy.
- Operational confirmation that the selected account can use the chosen model
  within the intended cost/quota policy.
- The deterministic existing-score/outreach behavior and its Notion mapping.

## Material Blockers

None for feature planning. Provider endpoint, provider name, model ID, and
credential variable are evidenced from active OpenCode configuration, so the
former transport blocker is resolved. Implementation remains blocked solely by
the mandatory user approval gate.

## Definition of Done

- [ ] Tushar explicitly approves this exact plan.
- [ ] The two-stage classifier and exact ICP exclusions are implemented and
      acceptance-tested.
- [ ] The `leads` migration, durable state/errors, retry bounds, and monotonic
      qualified retention pass upgrade and reverse-order tests.
- [ ] Qualified rows are durable before Notion and sync only after valid success.
- [ ] Existing canonical CLI behavior is preserved, RSS helper untouched, and
      webhook/cleanup work absent.
- [ ] Documentation uses only verified non-secret provider configuration.
- [ ] Tests, compile/import checks, and complete graph change analysis pass.

**Plan path:** `docs/plans/20260904_llm_qualification_api_resilience.md`

APPROVAL_STATUS: PENDING_USER_REVIEW

STOP: Review the plan with Tushar. Do not start implementation until Tushar explicitly approves this exact plan in a later message.
