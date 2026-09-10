# MAINTENANCE_PLAN: Scheduler File Logging Verification

**Date:** 2026-09-09  
**Repository:** `/Users/tusharmangla/RecruitmentOS/social_listening`  
**Status:** Pending explicit user approval before any scheduler execution or application change

## Goal

Verify the existing scheduler's logging behavior with one bounded, operator-approved run, then analyze the resulting files. The requested `logs/` directory and the requested `.log` files already exist and are actively used; no application-code logging implementation is currently required.

## Evidence and Current Behavior

| Evidence | Finding |
| --- | --- |
| `listening_loop/logger.py:4-39` | Central `setup_logging()` creates `<project>/logs`, configures the named `listening_loop` logger at `INFO`, and formats records as timestamp, logger name, level, and message. |
| `listening_loop/logger.py:8-9,20-29` | File handlers write `logs/info.log` at `INFO` and above and `logs/error.log` at `ERROR` and above. The names are `.log`, not the requested `.logs` spelling. |
| `listening_loop/logger.py:31-35` | A console `StreamHandler` also receives `INFO` and above with the same formatter. |
| `listening_loop/run.py:13,16-28` | The canonical pipeline imports this logger and redirects process stdout to `logger.info` and stderr to `logger.error`, so its `print()`-based progress/error reporting is persisted. |
| `listening_loop/install-scheduler.sh:23-52` and `listening_loop/run.sh:1-16` | On macOS, `launchd` invokes `run.sh` immediately and every 10,800 seconds; `run.sh` runs `venv/bin/python -m listening_loop.run`. launchd stdout/stderr are also captured in `logs/launchd.log`. |
| `logs/info.log` and `logs/launchd.log` | Existing 2026-09-09 output proves a scheduler cycle reached the pipeline, handled four sequential Reddit HTTP 429 failures, halted discovery intentionally, wrote final metrics, inserted zero new leads, and completed the wrapper cycle. |
| `logs/error.log` | Exists and is currently empty. This is consistent with the observed failures being handled through `print()` and therefore logged at `INFO`, not an indication that file logging is absent. |
| `.gitignore:59` | `*.log` is ignored, so generated operational logs are not intended for source control. |

The current logger does not rotate files. Also, because the `info.log` handler accepts `INFO` and above, any future `ERROR` records will appear in both `info.log` and `error.log`; this is standard threshold behavior but is not a mutually exclusive split.

## Assumptions and Non-Goals

**Assumptions**

- The existing `venv`, OpenCLI authentication, provider credentials, and optional Notion configuration are valid before an operator starts a live run.
- A bounded direct dry-run is safer evidence before enabling/reloading the persistent three-hour launchd job.
- Existing uncommitted changes in `listening_loop/config.py`, `listening_loop/install-scheduler.sh`, and `listening_loop/run.sh` are user work and must be preserved.

**Non-goals**

- Do not add a second logger, change paths to `.logs`, modify log levels, rotate files, or change scheduler cadence without a separately approved follow-up.
- Do not start a long-running scheduler, execute live collection, alter SQLite data, or edit application source during planning.
- There is no frontend, HTTP API, database migration, or data-schema change in this verification-only plan.

## User Journeys

1. An operator needs evidence that scheduled social-listening output is available for later troubleshooting.
2. The operator runs one bounded dry-run of the canonical entry point, then checks `info.log`, `error.log`, and `launchd.log` for the run's start, result, and any failures.
3. After reviewing the bounded result and external-service impact, the operator may install/load the existing three-hour launchd scheduler and monitor the same files.

## Affected Components and Caller Map

| Component | Role | Change in this plan |
| --- | --- | --- |
| `listening_loop/logger.py` | Central logger and handlers | Inspect only; no change. |
| `listening_loop/run.py:main` | Canonical CLI pipeline and stdout/stderr routing | Inspect only; bounded execution target after approval. |
| `listening_loop/run.sh` | Scheduler wrapper | Inspect only; invokes the canonical CLI. |
| `listening_loop/install-scheduler.sh` | macOS launchd installer/loader | Inspect only; only execute after explicit operational approval. |
| `logs/info.log`, `logs/error.log`, `logs/launchd.log` | Generated observability artifacts | Analyze only; ignored by Git. |
| `tests/test_run.py`, `tests/test_resilience_repair.py` | Known direct test callers of `run.main` | Preserve; run focused regression coverage. |

GitNexus impact analysis for `listening_loop.run.main` reports one direct upstream dependent, `LOW` risk, exact coverage, and no affected indexed processes. Its index is two commits behind HEAD, so this assessment is planning evidence only and must be refreshed before any code modification. `setup_logging` is not represented in the current graph index; direct source inspection is the authoritative evidence for that module.

## Contracts

- **Logging contract:** `logs/` is created on logger import. `info.log` receives `INFO`, `WARNING`, `ERROR`, and `CRITICAL`; `error.log` receives `ERROR` and `CRITICAL`; the console receives `INFO` and above. Format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`.
- **Scheduler contract:** macOS launchd executes `listening_loop/run.sh` at load and each three hours. The wrapper invokes `-m listening_loop.run`; launchd captures wrapper stdout/stderr in `logs/launchd.log`.
- **Pipeline contract:** `--dry-run` still collects, classifies, and persists candidates to SQLite, but skips Notion sync. It does not make a scheduler verification free of external collection/provider or database side effects.
- **Frontend/API/database/schema:** Not applicable. No endpoint, UI, entity, permission, migration, validation rule, or database constraint changes are planned.

## Acceptance Criteria

1. Before any command, the operator records line counts/timestamps for all three log files without deleting history.
2. One approved bounded command completes or terminates through the existing four-consecutive-discovery-error guard; it must not be run as a persistent background process.
3. `logs/info.log` gains a timestamped run-start/configuration record and a terminal metrics/result record for the bounded invocation.
4. `logs/error.log` is analyzed for `ERROR`/`CRITICAL` records. An empty file is acceptable when all failures are handled through `print()`/INFO; unexpected traceback or credential output is not acceptable.
5. The analysis explicitly distinguishes expected platform rate limits (the current evidence is Reddit HTTP 429) from scheduler, Python, provider, database, and Notion failures.
6. The full test suite remains green before an implementation follow-up is considered.
7. Persistent scheduler installation/loading happens only after explicit approval of the observed bounded-run result and operator confirmation that live external collection is wanted.

## Implementation and Verification Sequence

1. Preserve the current logs and capture a baseline after approval:
   ```bash
   wc -l logs/info.log logs/error.log logs/launchd.log
   stat -f '%N %Sm' logs/info.log logs/error.log logs/launchd.log
   ```
2. Run one bounded canonical dry-run, restricted to a single platform and a one-hour lookback:
   ```bash
   venv/bin/python -m listening_loop.run --dry-run --platform reddit --hours 1
   ```
   This is intentionally a foreground command. It can still invoke OpenCLI and the configured classifier and can write SQLite rows; stop and report provider/authentication failures instead of retrying repeatedly.
3. Analyze only records written after the baseline. Check terminal outcomes and failures:
   ```bash
   tail -n 100 logs/info.log
   tail -n 100 logs/error.log
   tail -n 100 logs/launchd.log
   rg -n 'ERROR|CRITICAL|Traceback|429|Provider|Run metrics|Added a total|cycle done' logs/info.log logs/error.log logs/launchd.log
   ```
4. Run regression coverage:
   ```bash
   venv/bin/python -m pytest -q
   ```
5. Only after the bounded result is reviewed and live scheduling is explicitly authorized, install/load the existing macOS job:
   ```bash
   bash listening_loop/install-scheduler.sh
   ```
   Confirm the immediate `RunAtLoad` execution via `logs/launchd.log`, then monitor using `tail -f logs/launchd.log` and the two application files. Do not leave a tail process running as part of automation.
6. Record an operational outcome: normal completion, handled external rate limiting, recoverable provider/database failure, or an unhandled error requiring a separate approved remediation plan.

## Test Plan

- Run `venv/bin/python -m pytest -q` to preserve pipeline behavior.
- Execute the bounded direct dry-run above as the integration test for logger creation, stdout redirection, and file output.
- Verify error routing mechanically, without triggering live failure, only in a future code-test addition if needed: a test would emit `logger.error("sentinel")` to a temporary logger path and assert the sentinel appears in both threshold-based handlers. No such test is needed to prove the existing files/handlers in this verification-only plan.
- Do not test a live launchd schedule in CI; it depends on macOS service state, external OpenCLI authentication, and provider availability.

## Risks, Error States, and Rollback

| Risk/error state | Handling |
| --- | --- |
| Reddit/OpenCLI HTTP 429 or unavailable session | Existing pipeline logs the handled failure to `info.log` and halts after four consecutive discovery failures. Do not repeatedly restart it; wait for rate-limit recovery. |
| Missing venv | `run.sh` exits with a clear message; create the venv only under separately approved setup work. |
| Missing provider/Notion credentials | Treat as an operational configuration failure; redact values from log review and do not commit them. |
| Log growth | No rotation exists. Stop using the scheduler and create a follow-up plan before logs exhaust available disk space. |
| Persistent scheduler must be disabled | Run `launchctl unload ~/Library/LaunchAgents/com.social-listening.digest.plist`; generated logs and the SQLite database are not rolled back or deleted. |

## Decisions Requiring Tushar's Review

1. Approve the bounded run despite its permitted external collection, provider requests, and SQLite writes under `--dry-run`.
2. Decide whether handled discovery failures should remain INFO events or be promoted to WARNING/ERROR in a separate logging-enhancement plan.
3. Decide retention policy and rotation limits before any long-lived scheduler is relied upon.
4. Confirm whether the intended semantics are the existing threshold-based duplicate error entries or mutually exclusive informational versus error files.

## Definition of Done and Binary Completion Contract

**Complete only when:** an approved bounded run has been executed; its terminal outcome and timestamps are present in the expected log files; error records have been classified; the focused/full test command has passed; and any launchd activation is explicitly authorized and evidenced separately.

**Not complete when:** only file existence was checked, a live scheduler is loaded without bounded-run review, logs are inspected without relating them to a run outcome, tests fail, or an unhandled traceback/secret is found without a follow-up approved plan.
