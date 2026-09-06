# FEATURE_PLAN: OpenRouter DeepSeek and Community-Specific Discovery

**Date:** 2026-09-05  
**Repository:** `/Users/tusharmangla/RecruitmentOS/social_listening`  
**Mode:** `FEATURE_PLANNING`  
**Status:** Pending explicit user approval before implementation

## Evidence Gate

`EVIDENCE_GATE: PASS`

Evidence collected before planning:

- `listening_loop/config.py` currently resolves Codex Everywhere settings at runtime and already normalizes a base URL into a `/chat/completions` endpoint. `qualification.py` sends `Authorization: Bearer <key>` and consumes the OpenAI-style `choices[0].message.content` response.
- OpenRouter's official API reference and quickstart verify that it accepts an OpenAI-compatible `POST https://openrouter.ai/api/v1/chat/completions` request with `Authorization: Bearer <OPENROUTER_API_KEY>`. `HTTP-Referer` and `X-OpenRouter-Title` are optional attribution headers. The existing response parser and JSON contract are compatible without modification.
- The live OpenRouter catalog page identifies DeepSeek V3.1 by the model slug `deepseek/deepseek-chat-v3.1`. The user-facing label "DeepSeek Flash 0731" was not found as an OpenRouter catalog slug; specifically, the suggested `deepseek/deepseek-chat-v4-flash-0731` endpoint returns 404. This plan therefore uses the verified V3.1 slug as the default while retaining `OPENROUTER_MODEL` as an explicit runtime override. It does not use an unverified `:free` suffix.
- The checked OpenCLI upstream README lists independent `reddit search` and `reddit subreddit` commands, but does not document whether `reddit search` accepts `--subreddit`, an `r/<name>` scope, or another filter argument. The installed project only invokes `opencli reddit search <query> --sort new --format json`; it has no locally pinned OpenCLI version or help capture. The implementation begins with a local `opencli reddit search --help` contract probe and tests the exact supported syntax before wiring community scope. This is an operational prerequisite, not a schema or application-code blocker.
- GitNexus reports the retrieval (`fetch_leads`) and stage-one gate (`is_qualified_candidate`) change surface as `LOW` risk with exact caller information. Their direct application caller is `run.main`; adapter and CLI tests are direct consumers. The index is one commit behind `HEAD`, so implementation must refresh it and rerun impact analysis before edits.

No API key value was read, written, echoed, or included in this document. The user-supplied credential must be rotated if it was exposed outside its intended private channel, then stored only in ignored runtime secret storage.

## Goal

Replace the Codex Everywhere Luna qualification provider with OpenRouter DeepSeek V3.1, configurable through OpenRouter-specific environment variables, and replace broad aggregated discovery terms with individual, subreddit-scoped recruitment-agency intent queries. Preserve the qualification prompt, response JSON, parser behavior, SQLite schema, and Notion synchronization unchanged.

## Assumptions and Non-Goals

### Assumptions

- The canonical execution path remains `listening_loop.run`: OpenCLI retrieval, recency filtering, stage-one keyword gate, LLM qualification, SQLite persistence, then optional Notion sync.
- The OpenRouter account associated with `OPENROUTER_API_KEY` has access and budget for `deepseek/deepseek-chat-v3.1`; the model is not assumed to be free.
- The target communities are exactly `recruiting`, `staffing`, and `Recruitment`, retaining the requested capitalization in configuration and passing each value as a separate scope.
- Existing `EXCLUDED_KEYWORDS` remain intact. "No aggressive negative filters initially" means no new discovery-query exclusions and no expansion of the stage-one exclusion list in this feature.

### Non-Goals and Invariants

- Do not change `SYSTEM_PROMPT` text.
- Do not change the provider request's expected JSON response format, `parse_response`, `validate_classification`, or result-status policy.
- Do not alter the SQLite `leads` schema, migrations, deduplication key, persistence semantics, or Notion property mapping/sync behavior.
- Do not introduce a second LLM provider, fallback model, frontend, HTTP API, scraper, database, or new negative-query filter.
- Do not place credentials, real secret values, or copied `.env` contents into source, tests, README examples, plans, output, or Git.
- Do not modify the legacy `listening_loop/fetch_and_sync_real_leads.py` path.

## Current Behavior and Impact Map

`run.main` loops over `config.PLATFORMS`, calls `opencli_adapter.fetch_leads(platform, config.KEYWORDS, hours)`, applies `is_qualified_candidate`, removes stored/duplicate IDs, and sends survivors to `classify_and_store`. `fetch_leads` currently OR-combines all keywords into one OpenCLI call per platform and emits only canonical lead fields. `run_opencli` builds `opencli <platform> search <query>`, with Reddit sorted newest.

Provider configuration currently uses Codex-specific defaults and variables. `qualification._provider_url` already supports base URLs that either include or omit `/chat/completions`, and `_provider_headers` supplies bearer authorization. The request construction and parser need only provider/config/header attribution changes, not a new transport abstraction.

| Component | Existing responsibility | Planned change |
| --- | --- | --- |
| `listening_loop/config.py` | Provider resolution, platform and keyword constants | Switch to OpenRouter defaults and runtime variables; replace discovery constants with target communities and structured query-family data. |
| `listening_loop/qualification.py` | Provider request, strict parsing, classification | Retain prompt, request body semantics, JSON parser, and validation; consume new config defaults and add only optional non-secret OpenRouter attribution headers if configured. |
| `listening_loop/opencli_adapter.py` | Subprocess execution and raw-post normalization | Accept per-query metadata/community scope, build the locally verified Reddit command shape, and preserve metadata on each normalized in-memory lead. |
| `listening_loop/run.py` | CLI orchestration, stage-one gate, dedupe, store/sync | Generate/iterate individual platform-community-query work items, preserve cross-run dedupe, and send metadata-bearing leads through the unchanged qualification/store flow. |
| `listening_loop/database.py` | SQLite schema and durable lead state | No change. Metadata remains in memory and is intentionally not persisted under this scope. |
| `tests/test_qualification.py`, `tests/test_classifier.py` | Provider/config and request behavior | Update provider fixtures/assertions and prove OpenRouter endpoint, bearer header, model, safe diagnostics, and unchanged payload/parser behavior. |
| `tests/test_opencli_adapter.py`, `tests/test_run.py` | Retrieval normalization and CLI orchestration | Add contract tests for separate community/query calls, command construction, metadata, dedupe, and no broad query execution. |
| `.env.example`, `README.md` | Non-secret operator documentation | Replace Codex references with OpenRouter setting names/defaults; document commands only after the OpenCLI scope syntax is verified. |

## User Journeys

1. An operator adds `OPENROUTER_API_KEY` privately to the ignored `.env`, optionally overrides the endpoint/model, and runs the existing CLI. Startup diagnostics show only provider label, model, normalized base URL, key variable name, and configured status.
2. A Reddit-only run invokes a separate search for every `(community, query-family, exact-query)` work item. A recent result retains `platform`, `community`, `query_family`, `exact_query`, and UTC `retrieved_at` in the in-memory lead sent to the gate/classifier.
3. The same post matched by multiple searches is classified at most once per run because `post_id` deduplication remains global. First-seen metadata is retained; no database update is attempted solely to persist the additional retrieval provenance.
4. A qualifying candidate receives the exact existing LLM prompt and expected JSON array contract through OpenRouter, is parsed identically, stored in SQLite, and optionally synced to Notion as before.
5. An unavailable OpenCLI scope syntax, OpenCLI failure, malformed output, missing OpenRouter key, timeout, HTTP failure, or malformed model reply follows existing safe failure handling: bounded/sanitized diagnostics, continuation where applicable, and no unqualified lead is promoted or synced.

## Contracts

### Frontend, API, Database, and Notion

There is no frontend or application HTTP API. There is no database migration in this feature.

- **SQLite:** unchanged `leads` table and all existing fields/constraints, especially `post_id UNIQUE`, classifier state, retry state, and `synced_to_notion_at`.
- **Notion:** unchanged qualified-only selection and existing property mapping.
- **LLM request:** same `messages`, `model`, timeout, and expected `choices[0].message.content` envelope. Only endpoint/default model/key source and optional standard attribution headers change.
- **LLM response:** unchanged JSON array items with `id`, `icp`, `author_role`, `intent`, `urgency`, `one_line`, and `confidence`; unchanged parser and validation.

### Provider Configuration Contract

Define only these OpenRouter-specific environment variables:

| Variable | Default / behavior |
| --- | --- |
| `OPENROUTER_API_KEY` | Required secret for live LLM requests. Never log or commit its value. |
| `OPENROUTER_BASE_URL` | Defaults to `https://openrouter.ai/api/v1`; normalize trailing slash. |
| `OPENROUTER_MODEL` | Defaults to verified `deepseek/deepseek-chat-v3.1`; permits an explicit operator override after model access is confirmed. |

`get_provider_chat_url()` must resolve to `https://openrouter.ai/api/v1/chat/completions` by default. Preserve legacy generic `LLM_*` environment variables only as a documented backward-compatible fallback if their current support is required by existing tests/operations; remove all Codex Everywhere variables from the active resolution precedence so an old secret cannot silently select the retired provider. Diagnostics must use provider label `openrouter` and name `OPENROUTER_API_KEY`, never the secret itself.

Use `Authorization: Bearer <key>`. `HTTP-Referer` and `X-OpenRouter-Title` are optional according to OpenRouter; do not add new required settings. If attribution is added, use fixed non-secret application identity values and test their absence does not affect request success.

### Discovery Contract

`LEAD_SUBREDDITS` becomes exactly:

```python
["recruiting", "staffing", "Recruitment"]
```

Replace the flat broad `KEYWORDS` list with a deterministic collection of family/query records. Each exact query must include an agency-context phrase and a pain/intent phrase, and each is sent independently. Initial query set:

| Query family | Exact queries |
| --- | --- |
| `business_development_client_acquisition` | `"recruitment agency" "client acquisition"`; `"staffing agency" "getting clients"`; `"recruitment agency" "business development"` |
| `outreach_performance` | `"recruitment agency" "cold email"`; `"staffing agency" "reply rate"`; `"recruitment agency" "outreach automation"` |
| `candidate_database_ats` | `"recruitment agency" "candidate database"`; `"staffing agency" "ATS automation"`; `"recruitment agency" "candidate matching"` |
| `workflow_operations` | `"recruitment agency" "workflow automation"`; `"staffing agency" "CRM integration"`; `"recruitment agency" "recruitment operations"` |

Remove the following broad standalone discovery terms entirely: `need a recruiter`, `applicant tracking system`, `candidate ghosting`, `hiring is hard`, `recruiting software`, and `recruitment automation`. Do not add a discovery negative filter.

Every normalized in-memory lead must have the canonical fields it has today plus:

```text
platform      # value equals source/platform such as "reddit"
community     # subreddit name for scoped Reddit searches; None for unscoped non-Reddit work
query_family  # stable family identifier from config
exact_query   # one exact individual query string, never an OR aggregate
retrieved_at  # timezone-aware UTC datetime captured when that query is retrieved
```

`source` remains for persistence compatibility. Metadata is operational/retrieval evidence only and is not passed to the LLM prompt or made durable in SQLite/Notion in this scope.

## OpenCLI Community-Scope Decision and Probe

Before application edits, run `opencli --version` and `opencli reddit search --help` in the target operator environment, save only the non-sensitive syntax result in the implementation notes/test fixture, and choose exactly one supported strategy:

1. If help documents `--subreddit <name>` (or equivalent scope option), issue `opencli reddit search <exact_query> --subreddit <community> --sort new --format json`.
2. If help documents a Reddit search syntax that accepts an explicit `subreddit`/community positional or command-specific option, use that documented syntax.
3. If the installed command cannot scope `reddit search`, use OpenCLI's documented `reddit subreddit` command only if it can accept the exact search query and produce equivalent result records. Do not simulate scope by injecting `r/<name>` into the search text without explicit OpenCLI documentation or a verified live contract test.

If none can support query-plus-community scoping, stop implementation and return a blocker with the exact `--help` output summary. This is necessary to satisfy the requirement that each query be passed separately into OpenCLI for each subreddit, rather than treating an unscoped global search as compliant.

Non-Reddit platforms retain their current individual-query behavior but have `community=None`; this plan does not claim they are community-scoped. Confirm during implementation whether requirements intend Reddit-only discovery. If all platforms remain enabled, run each query separately on each platform, while only Reddit expands by the three communities.

## Implementation Sequence

1. Refresh the GitNexus index, inspect current `run_opencli`, `fetch_leads`, configuration getters, and their callers, and rerun upstream impact analysis for `run_opencli`, `fetch_leads`, and provider request symbols. Record the current OpenCLI version and verified Reddit scope syntax before changing command construction.
2. Write/adjust acceptance tests first for OpenRouter runtime resolution: default endpoint/model, env override precedence, bearer authorization, safe diagnostics, provider label, and unchanged request body/response parser. Use synthetic test keys only.
3. Update `config.py` documentation/constants/getters to select OpenRouter and the verified default slug, expose `OPENROUTER_*`, remove Codex Everywhere active defaults, and define the exact community list plus structured query-family records. Preserve runtime dotenv loading and base URL normalization.
4. Update `qualification.py` provider comments, defaults, label, diagnostics, and optional attribution header handling so it consumes only the new config contract. Leave `SYSTEM_PROMPT`, `_prompt_posts`, parser functions, validation sets, request response format, batching, retry behavior, and classifier decisions byte-for-byte/functionally unchanged as applicable.
5. Refactor the OpenCLI adapter around an explicit search-work-item input rather than a keyword list. It must execute each exact query once per target scope, use the syntax proven in the probe, preserve safe subprocess/output behavior, normalize timestamps as today, and add provenance metadata at retrieval time.
6. Update `run.main` to construct the deterministic work-item list, expand Reddit across `LEAD_SUBREDDITS`, execute each work item independently, apply the unchanged stage-one gate, and retain global post-ID dedupe before classification. Avoid quadratic duplicate checks while retaining first-seen ordering and metadata.
7. Do not modify `database.py` or `notion_sync.py`. Add assertions that metadata does not alter database insert/upsert inputs expected by existing persistence logic or Notion mapping.
8. Update `.env.example` and `README.md` using setting names and non-secret defaults only. Replace all user-facing references to Codex Everywhere/Luna with OpenRouter/DeepSeek V3.1, document the model override and that credentials stay outside Git, and describe scoped per-query collection without publishing assumed OpenCLI syntax before the probe verifies it.
9. Run focused tests, then the complete suite. Execute a controlled Reddit `--dry-run` smoke test with a low lookback and no secret output; verify command count/scope/query provenance in test instrumentation or safe logs, not raw post contents. Refresh GitNexus, run `detect_changes(scope="all")`, and inspect any affected process before commit.

## Acceptance Criteria

1. With only `OPENROUTER_API_KEY` defined, diagnostics report `openrouter`, `https://openrouter.ai/api/v1`, `deepseek/deepseek-chat-v3.1`, and `OPENROUTER_API_KEY`, without exposing the key.
2. `OPENROUTER_BASE_URL=https://example.test/v1/` resolves to `https://example.test/v1/chat/completions`; `OPENROUTER_MODEL` replaces the default at request time without a module reimport.
3. A mocked qualification request uses `Authorization: Bearer test-key`, targets OpenRouter's chat-completions URL, sends the existing messages/payload shape, and accepts the existing valid `choices[0].message.content` response unchanged.
4. `SYSTEM_PROMPT`, `_prompt_posts`, `parse_response`, `validate_classification`, parser error handling, response JSON fields, qualification threshold, and classifier statuses have no behavioral change. Existing malformed-response and provider-failure tests remain passing.
5. `LEAD_SUBREDDITS` is exactly the requested three values, all 12 listed query records are present with stable family identifiers, and none of the six forbidden broad standalone terms are scheduled as standalone discovery queries.
6. For Reddit, the adapter produces one supported OpenCLI invocation for every community/query pair (36 calls for 3 communities x 12 queries) with no OR-combined query. The invocation includes `--sort new`, JSON output, and the locally verified community scoping form.
7. Every normalized lead from a scoped query contains correct `platform`, `community`, `query_family`, `exact_query`, and timezone-aware `retrieved_at`, alongside existing canonical fields. Old, malformed, and ID-less posts remain excluded as before.
8. A post returned for two work items is classified and stored no more than once per run, preserving first-seen provenance. Stored duplicates and due retries retain their existing behavior.
9. SQLite table definition/migration behavior and Notion mapping/sync tests show no changes; discovery metadata is not persisted or synced.
10. Missing OpenCLI, unsupported verified scope command, OpenCLI nonzero exit/timeout, missing OpenRouter key, request timeout/HTTP error, and malformed LLM output fail safely without secret/raw-content disclosure and without blocking other planned work items/platforms.

## Test and Verification Plan

| Level | Coverage |
| --- | --- |
| Unit: config/qualification | OpenRouter defaults, overrides, URL normalization, no secret diagnostics, bearer header, optional attribution behavior, unchanged prompt/body and parser contract. |
| Unit: adapter | Assert exact command arrays for the verified scope syntax; one invocation per work item; JSON list/line normalization; timestamp/lookback behavior; provenance metadata; subprocess failures and malformed output. |
| Unit: run | Deterministic work-item expansion, Reddit's 36 pairings, non-Reddit behavior decision, no OR aggregation, forbidden-query absence, global dedupe, stage-one gate preservation, retry and dry-run behavior. |
| Regression: database/Notion | Run existing database and Notion tests unchanged to prove no schema, state, or mapping changes. |
| Integration smoke | Mock OpenRouter HTTP and OpenCLI subprocess for deterministic end-to-end collection-to-SQLite; then perform an operator-authorized `--dry-run` against verified OpenCLI with safe, redacted observation. |
| Suite and graph | `venv/bin/python -m pytest -q`; refresh GitNexus; rerun impacts; run `detect_changes(scope="all")`; treat partial/truncated graph output as unresolved. |

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| "DeepSeek Flash 0731" is not the current public OpenRouter slug. | Default to catalog-verified `deepseek/deepseek-chat-v3.1`; require confirmation before substituting a different paid/free model. Keep a runtime model override. |
| OpenCLI version-specific Reddit scope syntax is unknown. | Probe installed `--help`, test the command array, and block rather than using an invented flag or unverified `r/` query text. |
| 36 Reddit searches increase latency/rate-limit exposure. | Maintain the existing 60-second per-call timeout and continuation policy; log only aggregate safe counters; observe a dry-run before scheduling. Rate/concurrency limits are not changed in this scope. |
| Query overhaul reduces stage-one matches because old qualifying keywords no longer align with targeted query text. | Keep the gate unchanged per invariant, add representative matching content tests, and use early dry-run metrics to assess recall before any separate gate-tuning proposal. |
| In-memory metadata is lost after restart and cannot audit a stored lead's retrieval origin. | Intentional scope boundary required by the no-schema-change invariant. Propose a future migration separately if durable provenance becomes necessary. |
| Credential supplied in a conversational channel could be exposed. | Never persist/log it; rotate it if exposure policy requires; use only ignored local secret storage/secret manager. |

## Rollback Notes

- Revert the isolated provider/config, adapter, orchestration, test, and documentation commit(s) to restore Codex Everywhere settings and aggregated discovery behavior. No database rollback is required because schema and persisted records remain unchanged.
- To stop live collection immediately, remove `OPENROUTER_API_KEY` from the runtime secret store or disable the existing scheduler; provider failures will remain safely classified under existing retry/fallback semantics.
- If scoped OpenCLI calls are operationally too expensive or noisy, disable the scheduler and rollback the query work-item change. Do not collapse to global broad searches without a reviewed follow-up plan.

## Decisions Requiring Tushar's Review

1. Approve the verified default `deepseek/deepseek-chat-v3.1` for the requested "DeepSeek Flash 0731" label, or provide an OpenRouter catalog URL/slug for a different desired model. The plan deliberately rejects unsupported guessed slugs and does not assume a free tier.
2. Approve handling Reddit scope as an implementation prerequisite: execute only after the installed OpenCLI `reddit search --help` confirms a query-plus-community form; otherwise stop with a concrete blocker rather than degrading to global search.
3. Confirm whether `twitter` and `facebook` should continue receiving each of the 12 individual queries without community metadata, or whether the overhaul should be Reddit-only. The proposed default preserves configured platform coverage while scoping Reddit as required.
4. Confirm the selected initial 12 exact queries/family labels above. They satisfy the specified families and paired-context requirement but are the first operational query set, not a claim of exhaustive market vocabulary.

## Definition of Done

- All acceptance criteria and full test suite pass.
- The documented installed OpenCLI syntax supports separately scoped community-plus-query calls, and a safe dry-run confirms the expected work-item expansion.
- OpenRouter uses the approved model/default endpoint and never exposes credentials.
- `SYSTEM_PROMPT`, LLM JSON format/parser, SQLite schema, database behavior, and Notion sync are demonstrably unchanged.
- Documentation contains only non-secret OpenRouter setup guidance.
- GitNexus impact and changed-flow scans are clean/non-partial, and the change is ready for review without any application code being edited before explicit approval.

APPROVAL_STATUS: PENDING_USER_REVIEW

STOP: Review the plan with Tushar. Do not start implementation until Tushar explicitly approves this exact plan in a later message.
