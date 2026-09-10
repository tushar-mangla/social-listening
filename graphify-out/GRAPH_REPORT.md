# Graph Report - .  (2026-09-10)

## Corpus Check
- 19 files · ~38,334 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 234 nodes · 340 edges · 18 communities detected
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]

## God Nodes (most connected - your core abstractions)
1. `lead()` - 10 edges
2. `main()` - 9 edges
3. `get_db_connection()` - 9 edges
4. `_request_batch()` - 9 edges
5. `use_temporary_database()` - 7 edges
6. `lead()` - 7 edges
7. `run_opencli()` - 7 edges
8. `_set_dry_run_argv()` - 6 edges
9. `classification()` - 6 edges
10. `ensure_dotenv_loaded()` - 6 edges

## Surprising Connections (you probably didn't know these)
- None detected - all connections are within the same source files.

## Communities

### Community 0 - "Community 0"
Cohesion: 0.09
Nodes (32): _bounded_error(), build_keyword_fallback(), classify_posts(), _failure(), get_provider_diagnostics(), is_retryable_category(), parse_response(), _prompt_posts() (+24 more)

### Community 1 - "Community 1"
Cohesion: 0.16
Nodes (21): add_lead(), _compute_next_retry(), get_db_connection(), get_due_for_retry(), get_existing_status_map(), get_unsynced_leads(), initialize_db(), lead_exists() (+13 more)

### Community 2 - "Community 2"
Cohesion: 0.16
Nodes (16): classify_and_store(), _dedupe_posts(), is_qualified_candidate(), LoggerWriter, main(), _pace_between_attempts(), _rate_limit_cooldown(), Main entrypoint for the social listening loop. (+8 more)

### Community 3 - "Community 3"
Cohesion: 0.14
Nodes (18): analyze_post(), fetch_and_process_leads(), fetch_reddit_posts(), Fetches posts from a single subreddit using its RSS feed., Fetches posts from specified subreddits, analyzes them, and saves real leads to, Analyzes a Reddit post from RSS feed to determine if it's a real recruitment age, build_notion_properties(), get_notion_client() (+10 more)

### Community 4 - "Community 4"
Cohesion: 0.18
Nodes (17): fetch_leads(), OpenCLIExecutionError, OpenCLIRateLimitError, parse_timestamp(), Raised when OpenCLI reports an HTTP 429 response., Parses a timestamp (ISO string, Twitter RFC 2822, epoch int/float) into a timezo, Raised when the installed OpenCLI cannot scope Reddit searches., Fetches leads from a given platform using opencli, filtering by keywords and tim (+9 more)

### Community 5 - "Community 5"
Cohesion: 0.22
Nodes (14): lead(), _set_dry_run_argv(), test_classify_and_store_respects_batch_cap(), test_consecutive_provider_failures_trigger_keyword_fallback(), test_enrich_and_persist_retains_provider_failure(), test_excluded_keyword_short_circuits_provider(), test_keyword_gate_rejects_job_seeker_before_provider_call(), test_main_dry_run_skips_notion_but_persists() (+6 more)

### Community 6 - "Community 6"
Cohesion: 0.2
Nodes (14): ensure_dotenv_loaded(), _first_env(), get_provider_api_key(), get_provider_base_url(), get_provider_chat_url(), get_provider_config_summary(), get_provider_model(), load_dotenv() (+6 more)

### Community 7 - "Community 7"
Cohesion: 0.27
Nodes (12): classification(), post(), _provider_env(), test_all_qualifying_roles_qualify_with_allowed_icp_intent(), test_invalid_json_body_is_unclassified(), test_job_seekers_direct_employers_and_advice_threads_are_not_qualified(), test_missing_api_key_is_provider_error(), test_provider_failure_is_retained_for_each_post() (+4 more)

### Community 8 - "Community 8"
Cohesion: 0.21
Nodes (5): Strict qualification, redaction, retry, and provider-config acceptance tests., test_confidence_boundary_and_intent_matrix(), test_duplicate_and_missing_results_are_unclassified(), test_strict_response_validation_rejects_bad_shapes(), _valid_item()

### Community 9 - "Community 9"
Cohesion: 0.27
Nodes (9): lead(), _payload(), Repair cycle 1 regression tests: redaction, dedup, monotonic evidence, batch IDs, test_classify_and_store_dedupes_within_call(), test_qualified_evidence_monotonic_on_reaffirmation(), test_strict_batch_id_mismatch_marks_entire_batch_unclassified(), test_terminal_leads_never_reclassified_and_run_dedupes(), use_tmp_db() (+1 more)

### Community 10 - "Community 10"
Cohesion: 0.4
Nodes (9): lead(), Repair cycle 2: qualified + qualified must not reference classified_at unbound., test_due_retry_selection_respects_cap_and_only_errors(), test_error_rows_track_attempts_and_retry_schedule(), test_only_qualified_unsynced_rows_are_selected(), test_persists_classification_failure_and_reclassifies_same_post(), test_qualified_reaffirmation_does_not_raise_unbound_local(), test_qualified_row_never_downgrades_reverse_order() (+1 more)

### Community 11 - "Community 11"
Cohesion: 0.18
Nodes (0): 

### Community 12 - "Community 12"
Cohesion: 0.2
Nodes (0): 

### Community 13 - "Community 13"
Cohesion: 0.38
Nodes (6): archive_page(), deduplicate_by_post_url(), get_all_pages_from_database(), Retrieves all pages from the Notion database using notion.search as a workaround, Archives a Notion page., Finds and archives duplicate pages based on the 'Post URL' property,     keeping

### Community 14 - "Community 14"
Cohesion: 0.5
Nodes (0): 

### Community 15 - "Community 15"
Cohesion: 1.0
Nodes (1): Backward-compatible shim: canonical implementation lives in qualification.py.

### Community 16 - "Community 16"
Cohesion: 1.0
Nodes (0): 

### Community 17 - "Community 17"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **57 isolated node(s):** `Repair cycle 2: qualified + qualified must not reference classified_at unbound.`, `Strict qualification, redaction, retry, and provider-config acceptance tests.`, `Repair cycle 1 regression tests: redaction, dedup, monotonic evidence, batch IDs`, `Retrieves all pages from the Notion database using notion.search as a workaround`, `Archives a Notion page.` (+52 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 15`** (2 nodes): `Backward-compatible shim: canonical implementation lives in qualification.py.`, `classifier.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 16`** (2 nodes): `logger.py`, `setup_logging()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 17`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What connects `Repair cycle 2: qualified + qualified must not reference classified_at unbound.`, `Strict qualification, redaction, retry, and provider-config acceptance tests.`, `Repair cycle 1 regression tests: redaction, dedup, monotonic evidence, batch IDs` to the rest of the system?**
  _57 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.09 - nodes in this community are weakly interconnected._
- **Should `Community 3` be split into smaller, more focused modules?**
  _Cohesion score 0.14 - nodes in this community are weakly interconnected._