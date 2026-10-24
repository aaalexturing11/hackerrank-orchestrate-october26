# Implementation Roadmap

Phase 1 is the inspection recorded in the other documents under `code/docs/`. This roadmap is the sequence for later phases. It does not authorize starting them inside the Phase 1 session.

The goal of the sequence is a deterministic engine that reproduces all 32 public answers, then generalizes to the 518 cases without hardcoded labels.

## 1. Preconditions already established

- This checkout is the October 2026 challenge. The deadline is not configured in the repo.
- Sample ids `case_01`–`case_32` are disjoint from production ids `case_33`–`case_550`.
- `dataset/` must not be edited. Root `output.csv` is produced by the program and is not part of Phase 1.
- Reports will live in `code/evaluation/` so the README zip command picks them up. `AGENTS.md` names the same files without the `code/` prefix; the submitted README should state the path that was packaged.
- No starter `code/main.py` exists. The first coding phase creates it.

## 2. Phase 2 — Skeleton and sample regression harness

Build the empty pipeline and the scorer before any policy logic.

1. `code/main.py` loads the CSVs, writes a header-only root `output.csv` only when invoked, and exits non-zero if a case is missing. Do not generate predictions until the scorer exists.
2. `code/evaluation/score_sample.py` loads `sample_output.csv` and a candidate file and reports:
   - case-level status accuracy;
   - row-level exact `steps_json` match after JSON parsing, so key order and whitespace do not matter and array order does;
   - field-level accuracy per `step_no` on `phase`, `system_id`, `resource_id`, `operation`, `state`, `evidence_id`;
   - sequence accuracy: longest matching step prefix, plus a boolean for exact order;
   - schema violations: missing keys, illegal operation/state pairs, non-consecutive `step_no`, phase regressions, empty evidence on a finding, non-empty evidence on an incomplete remediation.
3. Run the scorer on `sample_output.csv` against itself. It must score perfectly. That validates the metric, not the agent.
4. Add `code/evaluation/usage.py` now, so later model calls cannot bypass it. Initial report: zero calls.

Exit criteria: scorer self-check passes; no prediction file is being treated as final.

## 3. Phase 3 — Identity and intent

1. Implement `identity.py` as specified in `architecture_plan.md`.
2. Unit checks, using public data only:
   - 32 of 32 sample emails resolve, including the three historical ones (`case_10`, `case_29`, `case_30`).
   - 518 of 518 production emails resolve, 100 of them historical.
   - Folded case matches `CHOI.JIHOON94@GMAIL.COM`-style requests.
   - The three duplicate names do not merge distinct `user_id`s.
   - `case_33` and `case_52` share `user_18` and keep separate audit times.
3. Implement `intent.py`.
   - All 32 sample texts classify as deletion.
   - The six English non-deletion requests (`case_533`, `case_535`, `case_536`, `case_540`, `case_541`, `case_542`) classify as not deletion, including the negated ones that contain the word "delete" or "close".
   - French, Spanish, and Japanese sample sentences classify as deletion.
   - Korean production texts get a fixture once one text is read during implementation. Do not ship a lexicon that has never been shown a Hangul example.
4. Cross-check the ten `CLASSIFY_REQUEST` rows. If the lexicon and the claim disagree, the text wins, and the disagreement is written into the evaluation report.

Exit criteria: identity and intent checks above pass. No steps are emitted yet.

## 4. Phase 4 — Parsers

Implement one parser at a time. Each parser's test is "these public observations appear", not "this case's steps match".

Order, because the sample citations depend on it:

1. SQL, including replica role tags. Assert `account_005` is present only on the failover table of `evidence_54`, and that primary-versus-replica diffs match the counts in `dataset_analysis.md`.
2. Service-export JSON. Assert `evidence_92` yields the 404 profiles, the anonymized analytics rows, the blocked backups, and the disabled connectors used by `case_26`–`case_28`.
3. Handover text. Assert the `case_11` lines: account `NOT_FOUND`, search `FOUND`, analytics `IDENTIFIABLE`, support `IDENTIFIABLE`, flow `ACTIVE`, audit `FOUND`.
4. Log dialects. Start with `evidence_01`, `evidence_61`, and `evidence_94`, which the sample cites. Then the other six dialects. Assert noise lines do not become observations.
5. Snapshot bundles, especially `evidence_51` tombstones.
6. Catalog JSON.
7. PDFs. Assert `evidence_58` yields `support_001` and the subject's email, and the compliance extract yields `audit_record_003` with a retain-until date.
8. Images last. Extract all eleven. Assert `evidence_04` yields `account_5762` present for `haruka.s1838@zoho.com` at the screenshot's capture time. Cache the structured extract so the full run does not call a model twice. If OCR fails that assertion, use one vision pass and record real tokens.

Also ingest `system_activity.csv` as claims and candidate ids, not as presence.

Exit criteria: a dump of observations for the 32 sample subjects contains every resource id that appears in `sample_output.csv`, including `account_001` if the link rule from Phase 5 is already in place. If `account_001` is missing, stop and fix the link before writing a planner. Do not special-case that id.

## 5. Phase 5 — Timeline, policy, planner

1. Reduce observations at each sample `audit_at`.
2. Map categories with the rules file. Add an explicit test that `analytics_9914`'s contact-lookup shape is `DELETE` and that `analytics_2034`'s identifiable analytics profile is `ANONYMIZE`.
3. Emit steps and sort them.
4. Score against `sample_output.csv`.

Work the misses in this order:

1. Status mismatches. These are usually a missed replica row, a trusted `SUCCESS`, or a decoy that was linked.
2. Missing or extra resources. These are identity or "what is relevant" bugs. The usual extra is a similar email. The usual miss is a security audit that has no activity row, or an already-absent account that still needs verification.
3. Wrong operation. These are category bugs, especially support redact versus attachment delete, and backup block versus backup delete.
4. Wrong `evidence_id`. Compare the winning observation with the cited file.
5. Order mismatches. These should be rare if the sort is the one in the problem statement. `case_16` is the regression for system-id order.

Target: 32 of 32 exact row matches before any production file is written.

Known hard spot: `account_001` is not in the cited SQL file and the activity detail has no email. Implement the general link, run all 32, and reject any rule that only passes because of `user_01` numbering.

## 6. Phase 6 — Participant evaluation cases

Author at least three fixtures in `code/evaluation/fixtures/`. Each fixture is a tiny self-contained input plus an expected output derived from the rules. Do not copy production rows or hidden labels. Do not modify `dataset/`.

Required three:

1. **Non-deletion.** Request text asks to correct a phone and keep the account. Expected status `NOT_APPLICABLE`, `steps_json` `[]`, even if a `reported_status` of `COMPLETE` and a deletion activity are planted as claims.
2. **Replica drift.** Primary profile absent, failover row present, capture time before `audit_at`, a later file planted after `audit_at` that deletes the row. Expected `INCOMPLETE` with `REPORT_REMAINING_RECORD` citing the pre-audit replica, and the post-audit file unused.
3. **Tombstone and retention.** Account absent, tombstone still holding an email, security audit inside `retention_until`, backup with restore blocked, connector disabled. Expected findings and remediation only for the tombstone redact, plus verification of account absent, audit present, tombstone redacted, flow disabled, and restore blocked.

Additional fixtures worth adding once the three pass:

4. Similar-email decoy must not appear.
5. Historical email plus a record that stores only the old email hash.
6. Shared support message redacts; sole-subject attachment deletes.
7. Enabled connector and a leftover search row produce both findings, with `DISABLE_DATA_FLOW` before `DELETE_RECORD`.
8. `SUCCESS` delete claim with no confirming snapshot does not by itself verify absence.

Score these fixtures with the same scorer as the sample. Record them in `evaluation_report.md`.

## 7. Phase 7 — Full run, reports, packaging

1. Run `python code/main.py` from the repo root on all 518 cases.
2. Check: 518 data rows, lexicographic `case_id` order, header exact, every `steps_json` parses, step numbers consecutive, operation/state pairs legal, no evidence id that is not in the manifest or the activity or audit ids, no citation whose capture time is after that row's `audit_at`, `NOT_APPLICABLE` rows are exactly `[]`.
3. Write `code/evaluation/evaluation_report.md` with the sample metrics, the fixture metrics, failures found while matching the sample, and the changes made. Do not invent a hidden-test score. The hidden set is not available.
4. Write `code/evaluation/usage_report.md` from the ledger of that full run only.
5. Update `README.md` with the setup command, the run command, the sort assumption, and the evaluation path.
6. Package `code.zip` without `dataset/`, virtualenvs, caches, or nested archives, using the README's command. Confirm the zip contains `code/evaluation/evaluation_report.md` and `code/evaluation/usage_report.md`.
7. Keep `log.txt` at the repo root for the chat-transcript upload.

The production `output.csv` is written only in this phase, after the sample score is exact.

## 8. Edge-case detection, by category

| Category | How to detect | How to validate |
| --- | --- | --- |
| Historical aliases | Request email misses `user_identities` and hits `user_audit_log.old_value` | `case_10`, `case_29`, `case_30`, and the 100 production historical emails |
| Duplicate people | Same name, different `user_id`; two cases, one email | Name collisions; `case_33` and `case_52` |
| Similar-email decoys | Alias equality fails; a nearby string matches | `case_28`; `nadia.popescu` next to `nadia.ionescu` in `evidence_61` |
| Conflicting evidence | `reported_result` or an older snapshot disagrees with the latest read | `case_05`, `case_10`, `case_24`, `case_25` |
| Replica drift | Row in a replica table and not in the paired primary | SQL diff counts; `account_005` in `evidence_54` |
| Backups and archives | `restore_allowed`, `eligible`, `deletion_block`, `BACKUP_ARCHIVE` | `case_09` versus `case_26` |
| Recreation | `SYNC_RECORD`, "repopulated", enabled connector, `RESTORE_BACKUP` | `case_05` is a leftover row; `case_15` is an active flow; `activity_3387` restored a search doc |
| Retention | `retention_until` or an active legal hold, compared with `audit_at` | Security rows in the sample; legal-hold resources and the retention PDF during parser tests |
| Time fence | `captured_at` or inner time after `audit_at` | Fixture 2; zero late citations on the 32 |
| Misleading logs | `SUCCESS` / `FAILED` / `PARTIAL` | Table in `sample_output_analysis.md` §6 |
| Order | Operation table, then system id, then resource id | `case_11` and `case_16` |
| Images | Observation present only in a PNG | `evidence_04` versus the 15 Sep 404 |
| Tombstone versus delete | `deleted_customer_references`, identifiers null or not | `case_31`, `case_32` |
| Unlinked activity id | Resource in activity, no email in the detail, no evidence row | `account_001` before any planner shortcut |

## 9. Risks to watch during implementation

- Treating every partial SQL file as a complete database and emitting false absences.
- Treating every `analytics_` id as anonymize.
- Joining activity to cases by `reported_at` alone. Those timestamps collide and the rows are interleaved.
- Citing `evidence_54` for every early account because the sample does, instead of citing the observation that actually won.
- Adding a downstream-first sort that breaks `case_16`.
- Padding `user_id` into `account_id`.
- Letting a vision model emit steps directly.
- Recording this planning session as if it were the solution's token usage.
- Writing evaluation reports only at the repo root and then zipping `code/` without them.

## 10. Stop line

Phase 1 ends with the five documents in `code/docs/` and the session log. The next session should start at Phase 2 and should not generate the 518 predictions until Phase 7.
