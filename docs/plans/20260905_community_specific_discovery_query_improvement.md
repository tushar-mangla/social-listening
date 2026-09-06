# FEATURE_PLAN: Community-Specific RecruitmentOS Discovery Query Improvement

**Date:** 2026-09-05  
**Repository:** `/Users/tusharmangla/RecruitmentOS/social_listening`  
**Mode:** `FEATURE_PLANNING`  
**Status:** Pending explicit user approval before implementation

## Evidence Gate

`EVIDENCE_GATE: PASS`

Evidence collected before planning:

- `listening_loop/config.py` currently defines a flat `KEYWORDS` list and five broad Reddit communities. The requested target communities are not yet configured.
- `listening_loop/opencli_adapter.py:fetch_leads` currently combines all keywords into one quoted `OR` expression and calls `run_opencli` once per platform. `run_opencli` builds `opencli <platform> search <query>`, adds Reddit `--sort new`, and requests JSON output.
- `listening_loop/run.py:main` currently calls retrieval once per platform, applies the existing stage-one gate, performs run-wide post-ID deduplication, excludes already-stored posts, includes due retries, and isolates platform/classification failures.
- Existing focused coverage is in `tests/test_opencli_adapter.py` and `tests/test_run.py`; the user-provided baseline is 48 passing tests. Existing tests patch the current retrieval interface and must be updated or adapted without changing the stage-one, qualification, database, or Notion contracts.
- GitNexus impact analysis was run for `fetch_leads`, `run_opencli`, and `main`. Each returned `LOW` risk with exact graph coverage. Retrieval changes affect the `main` execution flow and the `Listening_loop` module. The index reports one commit behind `HEAD`; implementation must refresh the index before code edits.
- OpenCLI community-scoping syntax is not established by the repository. Implementation must first capture `opencli --version` and `opencli reddit search --help` in the operator environment and use only documented, verified syntax.

## Goal

Improve social-listening discovery precision and provenance by executing 12 targeted recruitment-agency intent queries independently across the configured platforms and Reddit communities, while preserving the active qualification provider, qualification behavior, persistence behavior, synchronization behavior, stage-one gate, negative filters, and existing LLM contracts.

## Assumptions and Non-Goals

### Assumptions

- The existing `listening_loop.run` command remains the operational entry point.
- `config.PLATFORMS` remains the source of enabled platforms. Reddit expands each query across `LEAD_SUBREDDITS`; non-Reddit platforms execute each query once with no community value.
- A query-family record has a stable family identifier and an exact query string. Ordering is deterministic: configured family order, configured query order, platform order, then Reddit community order.
- Retrieval provenance is in-memory/run-report data only. It is not part of the LLM prompt and is not persisted as a new database field.
- If the installed OpenCLI cannot document a community-scoping form compatible with Reddit search, implementation stops with a blocker and does not guess flags or silently substitute an unscoped search.

### Non-Goals and Invariants

- No provider, model, credential, endpoint, request-header, or qualification transport changes. The currently verified active provider remains active.
- Do not modify `listening_loop/qualification.py` or `SYSTEM_PROMPT`.
- Do not modify the LLM response JSON structure, parser, validation contract, batching semantics, or classifier status behavior.
- Do not modify SQLite schema, migrations, database constraints, database persistence semantics, or Notion synchronization/property mapping.
- Do not modify `QUALIFYING_KEYWORDS`, `EXCLUDED_KEYWORDS`, the stage-one keyword gate, or negative-filter behavior.
- Do not modify the legacy `listening_loop/fetch_and_sync_real_leads.py` path.
- Do not introduce an aggregate `OR` search, a new negative query filter, a new platform, or a second storage system.

## Current Behavior and Impact Map

| Component | Current responsibility | Planned discovery-only change |
| --- | --- | --- |
| `listening_loop/config.py` | Runtime constants, platforms, Reddit communities, flat discovery keywords | Add the exact structured query families, set the exact Reddit communities, and remove the six broad standalone terms from scheduled discovery. Preserve stage-one constants. |
| `listening_loop/opencli_adapter.py` | OpenCLI subprocess execution, JSON parsing, timestamp parsing, post normalization | Add a per-query/community invocation contract, verified Reddit scope construction, and provenance fields on normalized leads. Preserve safe subprocess behavior and time filtering. |
| `listening_loop/run.py` | Pipeline orchestration, stage-one gate, global dedupe, retries, classification, persistence, sync | Iterate query work items, isolate each query failure, aggregate structured metrics, and retain global post-ID dedupe before qualification. |
| `tests/test_opencli_adapter.py` | Adapter command, error, parsing, and normalization coverage | Add exact command/per-query/community and provenance assertions while retaining existing error and timestamp coverage. |
| `tests/test_run.py` | Gate, orchestration, dedupe, classification, retry, dry-run, and failure coverage | Add query iteration, cross-query dedupe, failure isolation, and run-report assertions; preserve all existing behavioral assertions. |
| `tests/test_resilience_repair.py` | Additional adapter/run resilience coverage | Update only retrieval call fixtures if the explicit per-query interface requires it; retain resilience expectations. |
| `listening_loop/qualification.py`, `listening_loop/database.py`, `listening_loop/notion_sync.py` | Qualification, persistence, and synchronization | No changes. |

GitNexus direct callers requiring compatibility review are the retrieval callers in `run.main` and adapter tests. The broader affected execution flow is `main`; classification and persistence remain downstream consumers whose input shape must stay compatible.

## User Journeys

1. An operator runs the existing social-listening command for all platforms or one selected platform. The run schedules each configured exact query independently instead of issuing one broad aggregate search.
2. For Reddit, each exact query is executed separately for `recruiting`, `staffing`, and `Recruitment` using the installed OpenCLI syntax verified before implementation. Each returned lead carries its platform, community, family, exact query, and UTC retrieval timestamp in memory.
3. If the same post matches several query/community combinations, the run report records duplicate removal and the post is passed to the existing stage-one and qualification pipeline at most once per run, retaining first-seen provenance.
4. If one query fails, times out, returns malformed output, or has unsupported scope syntax, the remaining independent work items continue where the scope probe has already passed. The failed item records a sanitized error count in the structured run report.
5. Posts rejected by the unchanged stage-one gate never reach the active qualification provider. Qualifying posts continue through the existing classification, SQLite, retry, and optional Notion paths without contract changes.
6. At the end of the run, operators can inspect query-level metrics containing community, family, exact query, retrieval count, duplicate count, stage-one pass count, qualification outcomes, and errors without any new database schema.

## Contracts

### Discovery Configuration Contract

`config.LEAD_SUBREDDITS` must be exactly:

```python
["recruiting", "staffing", "Recruitment"]
```

Add `DISCOVERY_QUERIES` as a deterministic mapping with exactly these four families and three exact queries per family:

```python
{
    "business_development": [
        '"recruitment agency" "client acquisition"',
        '"staffing agency" "getting clients"',
        '"recruitment agency" "business development"',
    ],
    "outreach_performance": [
        '"recruitment agency" "cold email"',
        '"staffing agency" "reply rate"',
        '"recruitment agency" "outreach automation"',
    ],
    "candidate_database_ats": [
        '"recruitment agency" "candidate database"',
        '"staffing agency" "ATS automation"',
        '"recruitment agency" "candidate matching"',
    ],
    "workflow_operations": [
        '"recruitment agency" "workflow automation"',
        '"staffing agency" "CRM integration"',
        '"recruitment agency" "recruitment operations"',
    ],
}
```

The six broad standalone discovery terms to remove from scheduled discovery are `need a recruiter`, `applicant tracking system`, `candidate ghosting`, `hiring is hard`, `recruiting software`, and `recruitment automation`. This removal applies to discovery scheduling only; existing stage-one qualifying and exclusion constants remain unchanged.

### OpenCLI Adapter Contract

- Before implementation, inspect and record non-sensitive output from `opencli --version` and `opencli reddit search --help`.
- Expose a retrieval interface that accepts one exact query plus platform and optional community scope. It must never construct an `OR` aggregate.
- For Reddit, construct community scope only from a syntax explicitly documented by the installed command. If no supported syntax exists, raise/report a clear unsupported-scope condition and stop implementation rather than guessing.
- Preserve the existing subprocess timeout, nonzero-exit handling, malformed JSON handling, safe diagnostics, timestamp parsing, missing-ID filtering, and lookback filtering.
- Every normalized lead retains current canonical fields and adds `platform`, `community`, `query_family`, `exact_query`, and timezone-aware UTC `retrieved_at`. `source` remains available for existing persistence consumers.

### Run Report Contract

Create a structured run report in memory and emit it through the existing run reporting/logging path without changing SQLite. Each query-level record must contain:

```text
community
query_family
exact_query
posts_retrieved
stage_one_passed
luna_qualified
luna_rejected
errors
```

`errors` must be a bounded/sanitized representation or count that cannot expose raw post content or secrets. Counts must be attributable to the exact `(platform, community, query_family, exact_query)` work item; because the required field list omits `platform`, retain platform in the surrounding run-report record or top-level context so cross-platform records remain distinguishable. Define and test whether `luna_qualified` and `luna_rejected` count classifier outcomes only, excluding stage-one rejects and duplicate posts.

### Frontend, API, Database, and Synchronization Contract

- No frontend or application HTTP API is involved.
- No database migration or SQLite schema change is permitted.
- No new provenance columns may be sent to or required by database/Notion code. Existing persistence and synchronization inputs remain accepted.
- The qualification request and response contracts are unchanged because the qualification module and prompt are outside this feature.

## Implementation Sequence

1. Refresh the GitNexus index, rerun upstream impact analysis for `fetch_leads`, `run_opencli`, and `main`, and preserve the current low-risk findings in implementation notes.
2. Run `opencli --version` and `opencli reddit search --help`. Select only a documented community-scoping syntax. If none supports the required per-query Reddit community execution, stop and report the blocker before application edits.
3. Add focused configuration tests first. Assert the exact three communities, four family identifiers, 12 exact query strings, deterministic order, and absence of the six forbidden standalone discovery terms from the scheduled query set. Assert stage-one keyword and exclusion constants are unchanged.
4. Update `listening_loop/config.py` with `DISCOVERY_QUERIES` and the exact `LEAD_SUBREDDITS`. Remove broad terms from discovery scheduling without altering stage-one constants or runtime provider configuration.
5. Add adapter tests for one exact query per invocation, verified Reddit scope arguments, non-Reddit unscoped behavior, metadata propagation, and preservation of existing JSON/error/time filtering. Update adapter signatures and implementation to pass query-family/community context.
6. Update `listening_loop/opencli_adapter.py` to execute and normalize one work item at a time. Keep command construction testable so tests can assert no `OR` aggregate and no undocumented flags.
7. Add run orchestration tests for all work-item expansion, per-query failure isolation, global first-seen post-ID dedupe, duplicate metrics, stage-one metrics, classifier outcome metrics, and structured report emission. Preserve retry selection, batch caps, dry-run behavior, and Notion sync behavior.
8. Update `listening_loop/run.py` to iterate the work items, apply the unchanged stage-one gate, deduplicate globally before classification, classify/store through the existing path, and finalize the structured report even when individual work items fail.
9. Run the focused tests, then the complete suite and confirm all existing 48 tests remain passing with the added focused coverage. Verify no changes to qualification, prompt/parser, database, or Notion files.
10. Run a controlled dry-run/smoke test with a low lookback and safe instrumentation. Confirm expected Reddit invocation cardinality of `3 communities x 12 queries = 36` per enabled Reddit pass, no aggregate queries, query isolation, and report counts without logging raw content.
11. Re-run GitNexus change detection for all worktree changes, inspect affected processes, and review the final diff for scope violations before implementation completion.

## Acceptance Criteria

1. `DISCOVERY_QUERIES` contains exactly four named families and exactly 12 queries matching the contract above.
2. `LEAD_SUBREDDITS` equals `['recruiting', 'staffing', 'Recruitment']` exactly and in that order.
3. None of the six broad standalone terms is scheduled as a discovery query, while `QUALIFYING_KEYWORDS`, `EXCLUDED_KEYWORDS`, and `is_qualified_candidate` behavior remain unchanged.
4. The adapter executes each exact query independently. No command contains a generated `OR` aggregate.
5. Reddit commands use only the community-scoping syntax proven by the installed OpenCLI help output. Unsupported syntax causes a clear implementation blocker rather than a guessed invocation.
6. With Reddit enabled, the scheduler creates 36 independently observable community/query work items for the 12 queries. Other enabled platforms execute each query separately without claiming Reddit community scope.
7. Normalized leads include all existing canonical fields plus correct `platform`, `community`, `query_family`, `exact_query`, and timezone-aware UTC `retrieved_at` values.
8. A post returned by multiple work items is sent to classification at most once per run, retains first-seen provenance, and increments `duplicates_removed` for later occurrences.
9. A failure in one query records an error for that work item and does not prevent subsequent queries/platforms from running.
10. The structured run report includes `community`, `query_family`, `exact_query`, `posts_retrieved`, `duplicates_removed`, `stage_one_passed`, `luna_qualified`, `luna_rejected`, and `errors`, with platform context and sanitized values.
11. Stage-one rejects do not invoke qualification; existing classification, retry, SQLite, dry-run, and Notion behavior remains intact.
12. The full suite remains green: all existing 48 tests plus the new focused discovery tests pass.
13. No application files outside `listening_loop/config.py`, `listening_loop/opencli_adapter.py`, `listening_loop/run.py`, and the focused test files are changed, and specifically no qualification, prompt, database, schema, or Notion files are changed.

## Test Plan

- **Configuration unit tests:** exact family/query contents, exact Reddit list, stable ordering, forbidden-term exclusion, and unchanged stage-one constants.
- **Adapter unit tests:** command argument capture, one-query invocation, documented Reddit scope, non-Reddit behavior, JSON and JSON-lines parsing, timeout/nonzero/missing executable handling, timestamp/lookback filtering, and provenance fields.
- **Orchestration unit tests:** work-item expansion, per-query exception continuation, cross-query/platform global dedupe, first-seen metadata, report count calculations, empty results, all-failed results, and classifier outcome accounting.
- **Regression tests:** existing adapter, run, classifier, qualification, database, Notion, and resilience tests must continue to pass without changing their protected contracts.
- **Smoke verification:** safe subprocess instrumentation or mocked OpenCLI captures command count and arguments; no raw post bodies, credentials, or unbounded stderr are emitted.
- **Graph verification:** after implementation, refresh the stale index as needed and run `detect_changes(scope="all")`; partial or truncated graph results are not considered clean.

## Risks and Mitigations

- **OpenCLI syntax mismatch:** the installed CLI may not support community-scoped Reddit search. Mitigation: probe help/version first and block rather than guessing.
- **Query fan-out increases runtime and rate pressure:** 36 Reddit invocations are expected. Mitigation: retain subprocess timeouts, isolate failures, preserve deterministic ordering, and report per-query metrics.
- **Duplicate volume across overlapping queries:** repeated posts could inflate classification cost. Mitigation: global post-ID dedupe before classification and explicit duplicate metrics.
- **Interface compatibility with existing tests/callers:** changing retrieval arguments can break patches and external callers. Mitigation: inspect GitNexus callers, use a clear compatibility adapter where needed, and update focused fixtures while preserving normalized lead fields.
- **Metric ambiguity:** a post may be retrieved, stage-one rejected, duplicated, or classified through fallback. Mitigation: define each counter at work-item boundaries and test mutually understandable counting rules.
- **Scope drift into protected pipeline behavior:** discovery metadata could leak into persistence or qualification. Mitigation: enforce file allowlist and regression assertions for unchanged downstream contracts.

## Rollback Notes

- Revert only the discovery-query changes in the three listening-loop modules and their focused tests; do not touch protected qualification, persistence, or synchronization files.
- If the OpenCLI probe fails, leave the application unchanged and report the installed syntax as the blocker.
- If runtime fan-out is problematic after release, temporarily disable the affected platform through the existing `--platform` control while retaining the deterministic configuration for follow-up; do not reintroduce an aggregate query.

## Decisions Requiring Tushar Review

- Confirm that non-Reddit platforms should run all 12 queries once each while only Reddit expands across the three communities.
- Confirm the run-report delivery mechanism: structured JSON log/event versus an in-memory report returned by a testable helper and serialized by the existing CLI logging path. Either choice must avoid SQLite changes.
- Confirm whether `luna_qualified` and `luna_rejected` count only terminal classifier outcomes, or include provider-fallback outcomes under a separate existing status category.
- Confirm the exact OpenCLI community-scope syntax after the operator-environment probe; no implementation should proceed without it.

## Definition of Done

- Tushar explicitly approves this exact plan.
- The OpenCLI version/help probe verifies a supported Reddit community-scoping form.
- The three named application modules and focused tests implement the exact 12-query contract, per-query isolation, global dedupe, and structured metrics.
- Protected qualification, prompt/parser, stage-one/negative filters, database schema, and Notion synchronization remain unchanged.
- All existing 48 tests and all new focused tests pass.
- Safe smoke verification and complete-suite verification pass.
- GitNexus impact/change checks are refreshed and reviewed, with no unresolved partial/truncated result.
