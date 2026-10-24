# Architecture Plan

This is a design for the deletion-audit agent. It does not include implementation. The recommendation is based on the files profiled in `dataset_analysis.md` and the canonical rows analyzed in `sample_output_analysis.md`.

## 1. Options

### A. Fully deterministic Python engine

Parse every CSV, SQL file, JSON file, log, text handover, and PDF with ordinary code. Apply identity resolution, time, and `deletion_rules.csv` in code. Emit `output.csv` with no model call.

Strengths: reproducible, free of token cost, easy to debug, easy to defend in the interview, fast on a 2.9 MB evidence set. Hidden-test behavior stays stable across machines if PDF text extraction and ordering are pinned.

Gap: eleven screenshots have no text sidecar. `evidence_04` shows `account_5762` present on 2026-09-26 after a log recorded HTTP 404 for that account on 2026-09-15. Production `case_34` audits that subject on 2026-09-27. An engine that never reads pixels will miss that fact when no later structured file repeats it. Nine of the eleven screenshots were not opened in this phase, so more of them may be the only positive observation.

### B. LLM reasoning pipeline

Prompt a model per case, or in batches, and ask it to return `steps_json`.

Strengths: multilingual request text and messy logs look like language problems. Screenshots can go to a vision model.

Gaps, given this dataset:

- The score is exact resource ids, exact operations, exact array order, and exact evidence ids. The public sample is fully determined once the records are parsed. A model that paraphrases an id or swaps two systems fails the field and sequence metrics.
- Re-runs will drift unless temperature is zero and the prompt is frozen, and even then JSON validity and sort order are weaker than a comparator in code.
- Evidence for one case is small, but a naive prompt that pastes the global activity file (4,011 rows) or every evidence file will burn tokens on decoys.
- Interview defense is weaker: "the model decided" does not explain why a failover row outranks a `SUCCESS` delete.

### C. Hybrid: deterministic policy engine, model only where pixels or a genuinely ambiguous text remain

Recommended.

- Code owns identity, time, policy, step construction, sorting, and CSV writing.
- Code parses SQL, JSON, logs, the handover text, and PDFs.
- Screenshots are extracted into the same observation records as everything else, then thrown away. The policy engine never sees an image.
- Request-text classification is a deterministic multilingual lexicon first. The 32 sample texts and the six explicit production non-deletion texts are regular. A model is not required for that classification unless a held-out fixture shows the lexicon is wrong.
- If a vision or OCR call is used, it is a batch extraction with cached structured output, and the usage ledger records the real token counts. If local OCR is good enough and calls no API, the usage report says zero model calls.

## 2. Why C fits this dataset

| Criterion | A | B | C |
| --- | --- | --- | --- |
| Hidden-test accuracy | High on text and SQL; blind on unique screenshot facts | Unstable on ids and order | High if vision output is normalized before policy |
| Reproducibility | Highest | Lowest | High: policy is code; image extract is cached |
| Cost | Zero | High if evidence is pasted per case | Zero, or one small vision batch |
| Tokens | None | Large | Only the image pass, if any |
| Debuggability | One observation can be traced to a file and a line | Hard | Same as A after extraction |
| Evidence traceability | `evidence_id` chosen by code | Model may cite a plausible id | Code chooses the id from the winning observation |
| Runtime | Seconds | Minutes and network | Seconds plus an optional image pass |
| Interview | Strong on the rules; must explain the image gap | Weak on exactness | Strong: rules in code, vision only as a parser |

The sample answers are a pure function of parsed observations plus the rules plus a stable sort. That function should not be a language model. The part that is not a pure function of text is the screenshot.

## 3. Pipeline

```text
dataset/
  -> loaders
  -> identity graph
  -> intent decision
  -> evidence parsers -> Observation records
  -> per-case timeline at audit_at
  -> policy decisions
  -> step planner and sorter
  -> output.csv
  -> regression against sample_output.csv
  -> evaluation report and usage report
```

For `NOT_APPLICABLE`, the pipeline stops after intent and writes `[]`. It does not look up records for those rows, so a non-deletion request cannot accidentally gain remediation steps.

## 4. Modules

Proposed layout, not yet created except for `code/docs/`:

| Module | Responsibility |
| --- | --- |
| `code/main.py` | CLI. Load, run all cases, write root `output.csv`. No network by default. |
| `code/load_dataset.py` | Read the nine CSVs. Reject unexpected columns. Parse timestamps as UTC. |
| `code/identity.py` | Build aliases. Case-insensitive email, punctuation-insensitive phone, exact email hash, stable `user_id`. Apply audit-log history. Refuse name-only matches. |
| `code/intent.py` | Decide deletion versus not from `request_text`. Lexicon for the languages present (English, French, Spanish, Japanese, Korean, and the accented Latin texts). Negation ("do not close", "don't delete") stays non-deletion. |
| `code/parse_sql.py` | `sqlite3` in memory, read-only. Emit one observation per row per table, tagged with replica role. |
| `code/parse_json.py` | Bundles, service exports, catalog files, single-collection reports. |
| `code/parse_logs.py` | One dialect detector, then extract state-bearing events. Drop router and connection noise. |
| `code/parse_text.py` | Handover lines. |
| `code/parse_pdf.py` | Text extraction into observations. Dependency decision deferred to implementation; prefer a small pure-Python extractor already available, otherwise document one pinned library. |
| `code/parse_images.py` | OCR or a cached vision pass. Output must use the same observation schema. No policy logic here. |
| `code/observations.py` | The normalized record. See §5. |
| `code/timeline.py` | For one case, keep observations at or before `audit_at`, join them through the alias graph, and reduce to the latest state per `(system_id, resource_id, replica)`. |
| `code/policy.py` | Map category, condition, and observed state to a required end state using `deletion_rules.csv` only. |
| `code/planner.py` | Build findings, remediation, and verification. Sort. Number steps. Choose `evidence_id`. |
| `code/write_output.py` | Header, 518 rows, lexicographic `case_id` order, compact JSON, empty evidence as `""`. |
| `code/evaluation/score_sample.py` | Compare to `sample_output.csv` on status, exact steps, fields, and sequence. |
| `code/evaluation/fixtures.py` | The three or more participant-authored cases. Not copies of production labels. |
| `code/evaluation/usage.py` | Ledger. Zeros if no model was called. |
| `code/evaluation/evaluation_report.md` | Written by the eval run, later. |
| `code/evaluation/usage_report.md` | Written by the final full run, later. |

Parsers do not import the planner. The planner does not import file formats. That split is what keeps a new log dialect from changing policy.

## 5. Observation schema

Every parser emits records of this shape. Fields that do not apply stay null. Parsers do not emit steps.

- `evidence_id`: manifest `file_id`, or `activity_id`, or `audit_id`.
- `captured_at`: manifest time for files; event time for activity and audit rows.
- `observed_at`: inner snapshot or event time, which may be earlier than `captured_at`.
- `system_id`: the system the step will name (`account_service`, not the log shipper).
- `replica_role`: `primary`, `read`, `regional`, `reporting`, `failover`, or `unspecified`.
- `resource_id`
- `record_type`: a `deletion_rules.csv` category when the artifact states one, otherwise a parser tag such as `contact_lookup` that policy must map deliberately.
- `aliases`: emails, phones, hashes, user ids found on the row.
- `presence`: `present`, `absent`, or `unknown`. `unknown` is for noise and for partial files that simply do not mention the subject.
- `identifiers_exposed`: true when name, email, phone, or email hash is still populated.
- `anonymized`: true when a profile remains and those identifiers are null, or the artifact says `ANONYMIZED`.
- `redacted`: true when the artifact says `REDACTED` or the identifying fields were cleared on a record that must be kept.
- `flow_enabled`: true, false, or null.
- `restore_blocked`: true, false, or null.
- `retention_until`: when present.
- `shared_context` and `sole_subject`: true, false, or null, for support rules.
- `source_locator`: file path plus line, row, or JSON pointer, for debugging. Not written to `output.csv`.

Activity rows enter the same schema with `presence` left `unknown` unless the detail text actually establishes a state. A `SUCCESS` delete is a claim. It can supply a candidate `resource_id` once the row is tied to the subject. It does not set `presence` to `absent`.

## 6. Identity

1. Index current identities by folded email, normalized phone, exact hash, and `user_id`.
2. Walk `user_audit_log.csv` in time order and attach historical emails, phones, and hashes to the same `user_id`.
3. Resolve the request email against current, then historical. All 518 production emails resolved this way in the profile, 100 of them only historically.
4. From that `user_id`, collect every alias that existed at or before `audit_at`. Ignore audit events after `audit_at` if any appear. None did for the 518 cases.
5. Match evidence and activity on those aliases. Do not match on name. The three duplicate names and the lookalike rows inside `evidence_54` are the test.
6. `LINK_RESOURCE_IDENTITY` rows add a resource id when the email and `user_id` agree with the alias set. They are claims about linkage, confirmed when the same pair appears in evidence.
7. Resource ids that appear only on activity rows with no alias are not globally assigned. Attach them only when a tested case-link says they belong to this request. `case_01` / `account_001` is the regression test for that rule. `user_N` to `account_N` padding is forbidden; `user_43` is `account_7566`.

Two production cases share one email and one `user_id` (`case_33`, `case_52`) at different audit times. The timeline is per case, not per user.

## 7. Timeline and replicas

For each linked resource:

- Discard observations whose file `captured_at` or inner `observed_at` is after `audit_at`.
- Group by system, resource, and replica role.
- Keep the latest observation in each group.
- The resource is present if any replica's latest observation says present.
- The resource is absent only if the latest eligible observation for every replica that actually spoke about it says absent, or a single-homed explicit negative lookup is the latest word and no replica later shows the row.
- A partial inventory that never mentions the subject does not count as an absence observation. `presence` stays `unknown` and the reducer ignores it.
- Conflicting field values on one key were not found in the SQL diffs. If they appear, the latest timestamp wins per replica, and any non-compliant replica keeps the case incomplete.

Enabled connector plus a remaining downstream row produces both an active-flow finding and a remaining-record finding. A past `SYNC_RECORD` that already created a replica row produces only the remaining-record finding, matching `case_05`.

## 8. Policy to steps

End states:

| Required action | Compliant observation | If not compliant |
| --- | --- | --- |
| DELETE | Explicit absence | Finding `REPORT_REMAINING_RECORD`, remediate `DELETE_RECORD`, verify `VERIFY_RECORD_ABSENT` |
| REDACT | Record present, direct identifiers gone | Finding `REPORT_EXPOSED_PII`, remediate `REDACT_RECORD`, verify `VERIFY_RECORD_REDACTED` |
| ANONYMIZE | Record present, not attributable | Finding `REPORT_EXPOSED_PII`, remediate `ANONYMIZE_RECORD`, verify `VERIFY_RECORD_ANONYMIZED` |
| RETAIN security log or legal hold | Record present inside the retention or hold window | If missing, that is a compliance failure. The sample never deletes these. If the record is present, verify `VERIFY_RECORD_PRESENT` and do not remediate it. If identifiers on a security log look like a different category, do not invent a redact rule; `rule_12` says retain. |
| RETAIN backup | Archive kept and restore blocked | If restore is still allowed: `REPORT_RESTORE_RISK`, `BLOCK_RESTORE`, `VERIFY_RESTORE_BLOCKED`. Do not emit `DELETE_RECORD` for the archive. |
| Active data flow | `enabled` false | `REPORT_ACTIVE_DATA_FLOW`, `DISABLE_DATA_FLOW`, `VERIFY_DATA_FLOW_DISABLED` |
| Tombstone | `user_id` kept, direct identifiers null | Otherwise `REPORT_EXPOSED_PII` and `REDACT_RECORD` |

Support messages use `rule_05` (redact) when the artifact shows shared context or the record type is `SUPPORT_MESSAGE` and the sample's identifiable messages were redacted rather than deleted. Support attachments use `rule_06` (delete) when the artifact says the file belongs only to the subject, as `evidence_58` and the `object_19` link row do. If an attachment is shared, the rules file does not give a second attachment action. Flag that row for a fixture rather than guessing a delete.

`case_12` requires the category mapper to treat a marketing-style contact lookup as `DELETE`, not as analytics anonymization. The mapper should key off `record_type` and fields (`email_opt_in`, `MARKETING_PROFILE`, `CACHE_ENTRY`, `EMAIL_DELIVERY_LOG`) before it keys off the resource prefix.

A case is `COMPLETE` when every linked relevant resource is already in its compliant end state and no flow or restore path is active. Steps are the verification list only.

A case is `INCOMPLETE` when any relevant resource is non-compliant. Findings and remediation list only the violations. Verification lists every relevant end state, including ones that are already true, with empty `evidence_id`. That matches the 21 sample rows that verify records they do not remediate.

Relevant means: linked to the subject by an alias or a confirmed resource id, in a category the rules cover, with an observation at or before `audit_at`. Decoys with a similar email stay unlinked.

## 9. Evidence id selection

For a `COMPLETE` verification or an `INCOMPLETE` finding, cite the `evidence_id` of the winning observation.

- Prefer the latest observation that establishes the state the step asserts.
- If a file and an activity row disagree, cite the file when the file is the later direct read. Cite an `activity_id` only when no file establishes the state and the activity row itself is the proof the contract allows.
- Do not cite a file that merely sits near the case in time if its contents do not establish that resource's state.
- Multiple steps may share one `evidence_id`, as in `case_26`.
- Remediation and post-remediation verification always use `""`.

## 10. Sort and serialization

1. Phases: `FINDING`, `REMEDIATION`, `VERIFICATION`.
2. Inside a phase, the allowed-operations table order.
3. `system_id` lexicographic ascending.
4. `resource_id` lexicographic ascending.
5. `step_no` from 1 in that order.

Do not add a downstream-before-source pass. `case_16` would fail it.

Rows of `output.csv` sorted by `case_id` lexicographic ascending. Document the numeric-sort ambiguity in the README so a grader mismatch is visible. JSON compact, with the problem statement's key order for readability. The grader ignores key order.

## 11. Usage accounting

`code/evaluation/usage.py` is a ledger appended by any model client:

- provider, model name, call count, input tokens, output tokens;
- a price table in code, with the currency and the rate written next to the estimate;
- totals, per-request averages over 518, and per-model subtotals.

If the image parser is local and intent stays lexical, the final run records zero calls, zero tokens, and zero cost, and the report says why. This planning session's IDE image reads are not part of that run and must not be entered as if they were API usage. No token number from this design phase is a measurement of the solution.

## 12. What this design refuses to do

- Hardcode `case_id`, expected status, or sample resource ids into the planner.
- Trust `reported_status` or `reported_result`.
- Treat omission from a partial extract as absence, except where an explicit negative lookup or a tested scoped snapshot says so.
- Match on name similarity.
- Read organizer-only files. None are in this checkout.
- Send evidence to a model when a parser already produced an observation.

## 13. Phase 2 implementation decisions

The foundation now exists under `code/`. It does not write `output.csv` and it does not choose `deletion_status`.

- `FoundationAuditor.build_context` classifies the request, resolves the subject, and reconstructs eligible replica state. Policy application and step planning stay in the next phase.
- Activity `reported_result` values become claim observations with `presence="unknown"`. The timeline drops claims, so a `SUCCESS` delete does not become absence.
- Paired SQL tables in one file can show a scoped omission for an id that appears on the other table. An id listed on neither table, including `account_001` in `evidence_54`, is not an absence. The public sample cites `evidence_54` for `account_001`; that link is unresolved and is not invented here.
- Empty SQL inventories stay parsed and carry an explicit warning. They are not absence proofs.
- Log dialects covered: key/value, JSON lines, bracket traces, pipe-separated operations, and cloud `message=` payloads. Trace ids copy lookup keys onto the completed event. HTTP 404, `rows=0`, and `result=miss` are absence. Workflow completion is not deletion.
- PDFs use the standard library: ASCII85 plus flate, then literal text operands. Font streams are skipped. The legal register is one row per order, not a cross join of every user to every order.
- All 11 PNGs return `requires_processing` and zero observations. No screenshot text is invented. Local OCR is not installed.
- Step order is phase, then the allowed-operations table, then `system_id`, then `resource_id`. The default resource comparison is lexicographic. Tests can select numeric comparison without changing the default.
- The sample harness scores `dataset/sample_output.csv` against itself. Contract fixtures are synthetic and are not production labels.

## 14. Phase 3 decision engine

`DeletionAuditor.audit` classifies the request, resolves identity, reconstructs state at `audit_at`, applies `code/policy/decide.py`, and emits ordered steps. `code/evaluation/predict.py` scores those predictions against the 32 public rows only after prediction. The self-score of the sample against itself is not a prediction score.

Policy, evidence precedence, image extraction, and the unresolved links are in `policy_engine.md`. Screenshots are read from the packaged `code/ingestion/image_facts.py` cache. Known replica system ids stay distinct. Non-canonical store names fall back to the category's system. Absence observed before `requested_at` is not treated as the state at `audit_at`.

## 15. Phase 4 verification review

The sample evaluator now reports operation precision and recall, and it prints each missing step with its evidence, aliases, activities, and a cause class. That comparison runs after prediction. `code/evaluation/dry_run.py` audits all 518 requests in memory and does not write `output.csv`.

Trace keys propagate only inside one trace, and an explicit null is not a key. Empty collections and `snapshot_scope` rows are not closed-world absence. The public-sample score is unchanged because none of the 28 missing steps has a unique subject key in evidence that is eligible at `audit_at`. The class counts and the contradictions are in `policy_engine.md`.

