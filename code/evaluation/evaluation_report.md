# Evaluation report

The auditor is deterministic. It does not call a language or vision model at runtime. Public-sample labels are read only by the scorer, after predictions are produced. They are not an inference lookup.

## Public sample

Measured by `python -m code.evaluation.predict` on 24 October 2026. The run was repeatable: a second prediction matched the first status and `steps_json` byte for byte.

| Metric | Result |
| --- | --- |
| Cases | 32 |
| Status accuracy | 32/32 (1.0000) |
| Exact-row accuracy | 17/32 (0.5312) |
| Field accuracy (positional) | 889/1158 (0.7677) |
| Aligned field accuracy | 1032/1158 (0.8912) |
| Sequence accuracy | 17/32 (0.5312) |
| Operation precision | 172/172 (1.0000) |
| Operation recall | 172/193 (0.8912) |
| Missing operations | 21 |
| Extra operations | 0 |

Aligned field accuracy matches a step on phase, system, resource, and operation, then compares fields. It does not replace the positional field score. Every emitted operation matches the canonical operation, state, system, and resource. The positional field gaps are the 21 missing steps shifting later positions. No emitted step cites the wrong evidence id for the same operation and resource.

Status is correct for every public case: the 17 exact rows and the 15 partial rows agree on `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`.

## Additional evaluation cases

These cases use synthetic records. They do not copy public `case_id` values or sample resource assignments. `python -m unittest code.tests.test_foundation code.tests.test_reasoning` ran 41 tests, all passing, including the three below.

### 1. Later package must not replace an admissible state

Expected: an early 404 for `account_10` stays `VERIFY_RECORD_ABSENT` and cites `evidence_early` when the case is otherwise complete. An early exposed support message stays `REPORT_EXPOSED_PII` citing `evidence_early`. A later package that names the same account, and a later redacted copy of the support record, are not cited.

Actual: the planner returned that absence verification with `evidence_early`, the exposed-PII finding with `evidence_early`, and no step citing `evidence_late`.

### 2. Competing ownership stays unresolved

Expected: if one late snapshot ties `account_10` to the audit subject and another ties it to a different email, the early anonymous 404 is not assigned. The step list is empty.

Actual: the step list was empty.

### 3. A present failover copy is not hidden

Expected: a primary absence and an earlier present failover row for the same account produce `REPORT_REMAINING_RECORD` citing the failover file.

Actual: the only finding was `REPORT_REMAINING_RECORD` with evidence `evidence_failover`.

A related test confirmed the other replica direction: on one replica, a later absence replaces an earlier present, and the verification cites the later file.

## Failures found and corrections made

- Treating every inner timestamp as eligibility let a later package overwrite admissible state. Public exact-row accuracy fell from 15/32 to 12/32 and status accuracy fell from 32/32 to 30/32. That rule was removed.
- Separating ownership from state recovered `account_5684`: the 2026-09-09 snapshot inside `evidence_02` identifies user 26, and the eligible 404 in `evidence_92` is the audit-time state.
- A historical event is now used as state only when the resource has no eligible observation and the case is already incomplete. The verification cites nothing. This recovered the six security and account checks inside `evidence_02` and `evidence_06` whose packages are after the audit, and it made `case_09` and `case_24` exact.
- An intermediate production run marked `case_168` `COMPLETE` with an empty step list, because its only state was an uncitable later package. Gap state no longer changes status. `case_168` stays `INCOMPLETE`.
- `python code/main.py` previously printed dataset counts and did not write `output.csv`. It now runs `DeletionAuditor` and writes the root file.
- Screenshot text is stored in `code/ingestion/image_facts.py`, so image evidence does not depend on a live vision model.

## Remaining public discrepancies

Twenty-one canonical operations are still absent. None can be assigned without breaking a constraint that the evidence actually supports.

Null identifiers, ten operations. The resource is in an eligible file and every subject field is null. A second file, when it exists, is also null. `analytics_9406` is a lookup on trace `rb-095409-021` with `lookup_key=null` and null email, phone, hash, and customer reference. The next log line is a different trace and a different resource.

| Case | Resource |
| --- | --- |
| case_03 | analytics_9406 |
| case_21 | account_6440, analytics_5335 |
| case_25 | account_3136, analytics_1895 |
| case_26 | analytics_4566 |
| case_27 | analytics_4574 |
| case_28 | account_5482, analytics_6077 |

`account_3866` is the exception inside this group. `evidence_92` is a 404 with a null profile at 2026-09-15. `evidence_02` later shows `user_27` and `ananya-nair@gmail.com` on a snapshot captured at 2026-09-17, after the case audit. That later snapshot is a unique candidate, and it is not admissible at the audit. Using it would explain a 15 September absence with a 17 September profile, including the possibility that the profile was recreated after the audit.

Activity text without a subject, seven operations: `account_5521`, `account_5037`, `account_4990`, `account_410`, `account_7012`, `account_4163`, `account_8858`. Each deletion-worker detail names the resource and a result. It does not name a person, case, or correlation id. The events of different subjects overlap, so time proximity does not isolate one owner. No evidence file contains these ids.

Impossible from the participant files, four operations:

| Case | Resource | What the files contain |
| --- | --- | --- |
| case_04 | account_004 | not present in `evidence_54` or anywhere else, and not in the activity log |
| case_18 | audit_record_6645 | no file and no activity |
| case_20 | audit_record_5569 | no file and no activity |
| case_31 | account_4857 | `activity_3682` only; `evidence_51` does not contain the id |

No further rule was added in this final pass. The 17/32 implementation is unchanged aside from locating the dataset relative to `code/main.py`.

## Production validation

`python code/main.py` was run twice. Both writes of `output.csv` had SHA-256 `945dc6236c87f29551f47a923de381f58c7991825b2f84bea09ca427adcffad5`. Elapsed times were 2.45 seconds and 2.43 seconds.

| Check | Result |
| --- | --- |
| Requests processed | 518 |
| Rows in `output.csv` | 518, one per request |
| Header | `case_id,deletion_status,steps_json` |
| Order | lexicographic `case_id`, which is string order |
| Parse failures | 0 |
| Schema issues | 0 |
| `COMPLETE` | 162, none with an empty step list |
| `INCOMPLETE` | 349 |
| `NOT_APPLICABLE` | 7, each with `[]` |
| Steps | 2547 (FINDING 631, REMEDIATION 631, VERIFICATION 1285) |

Hidden labels for the 518 requests are not in this repository. These figures are execution and contract checks, not accuracy against a hidden answer key.
