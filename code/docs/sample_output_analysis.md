# Sample Output Analysis

All 32 rows of `dataset/sample_output.csv` were parsed and checked against `dataset/sample_deletion_requests.csv`. The two files contain the same ids in the same order, `case_01` through `case_32`. This document separates the written contract from patterns that the canonical rows add.

Nothing here is a production label. The implementation may use these rows as a regression oracle because the challenge publishes them as the correct sample answers. It must not copy their resource ids onto the 518 evaluation cases.

## 1. Contract checks that the sample satisfies

Checked mechanically on every step:

- Every object has exactly the keys `step_no`, `phase`, `system_id`, `resource_id`, `operation`, `state`, `evidence_id`. No extras, no missing keys.
- `step_no` is an integer, starts at 1, and increases by 1.
- Phase order never goes backwards.
- Every operation/state pair matches the allowed-operations table. There are no exceptions.
- Within each phase, the tuple `(operation order, system_id, resource_id)` is sorted ascending.
- `COMPLETE` rows contain only `VERIFICATION` steps, and every `evidence_id` is a non-empty `evidence_NN` id that exists in the manifest.
- `INCOMPLETE` findings have a non-empty `evidence_NN` id. Remediation and verification on those rows use `""`.
- Every cited file has `captured_at` <= the case's `audit_at`. Zero late citations. `evidence_03` is cited at a capture time equal to `audit_at`.
- JSON is compact (`","` and `":"` with no extra spaces). The grader ignores key order and whitespace, and the file uses both orders anyway.

Key order is not stable and is not a requirement:

- 24 rows use `step_no`, `phase`, `system_id`, `resource_id`, `operation`, `state`, `evidence_id`.
- 8 rows (`case_01`, `case_02`, `case_04`, `case_05`, `case_06`, `case_07`, `case_08`, `case_10`) use alphabetical key order, starting with `evidence_id`.

There is no `NOT_APPLICABLE` row and no empty array. The problem statement's `case_000,NOT_APPLICABLE,[]` example is not one of these 32 cases.

## 2. Status against the workflow claim

| reported_status | Canonical COMPLETE | Canonical INCOMPLETE |
| --- | ---: | ---: |
| COMPLETE | 6 | 11 |
| PARTIALLY_COMPLETE | 1 | 4 |
| NOT_STARTED | 3 | 7 |

`reported_status` agrees with the canonical status on 13 of 32 rows. It is not an input to the decision beyond being a claim.

## 3. Explicit schema versus sample-only patterns

### Explicit, and confirmed

- Seven fields, all required, names and enumerations as in the problem statement.
- `step_no` consecutive from 1.
- Phase order, then operation-table order, then `system_id`, then `resource_id`.
- `COMPLETE` is verification only, with evidence.
- `INCOMPLETE` future steps use an empty evidence string.
- Findings cite evidence captured at or before `audit_at`.

### Inferred from the 32 rows

These are regular in the sample. They are not written as a separate table in the problem statement. The implementation should follow them and lock them with regression tests, because every public answer uses them.

1. **One policy action, one finding operation.**
   - `DELETE` and the record still exists: `REPORT_REMAINING_RECORD` / `PRESENT`, then `DELETE_RECORD` / `ABSENT`, then `VERIFY_RECORD_ABSENT`.
   - `REDACT` or `ANONYMIZE` and direct identifiers remain: `REPORT_EXPOSED_PII` / `PRESENT`, then `REDACT_RECORD` or `ANONYMIZE_RECORD`, then the matching verify.
   - Enabled connector: `REPORT_ACTIVE_DATA_FLOW` / `ACTIVE`, then `DISABLE_DATA_FLOW` / `DISABLED`, then `VERIFY_DATA_FLOW_DISABLED`.
   - Backup that can still be restored: `REPORT_RESTORE_RISK` / `ACTIVE`, then `BLOCK_RESTORE` / `BLOCKED`, then `VERIFY_RESTORE_BLOCKED`. The archive is not deleted.
   - Already-compliant records produce no finding and no remediation.

2. **Verification on an incomplete case covers the required end state, not only the remediated rows.** Already-absent accounts and retained security logs appear as verification steps with `evidence_id` `""` even when they were not findings. Examples: `case_06` verifies `account_006` absent although the only finding is `search_001`; `case_09` verifies the account absent and `audit_record_4902` present although the only finding is the backup. A mechanical check that "every remediation has a verify" passes. The converse fails on 21 rows: verification includes extra end-state checks.

3. **A compliant security audit log is `VERIFY_RECORD_PRESENT`, not a redaction.** It is included when the case's evidence contains one for the subject. Early cases whose cited files do not contain one (`case_01`, `case_02`, `case_04` through `case_08`, `case_10`) do not invent one.

4. **Several verification steps may cite the same file.** `case_26` uses `evidence_92` for all six verifications. `case_04` uses two files because the account and the analytics profile are in different artifacts (`evidence_54` and `evidence_56`).

5. **The citation is the artifact that shows the state, which can be a file that does not itself contain the word "deleted".** `case_01` cites `evidence_54` for `VERIFY_RECORD_ABSENT` of `account_001`. That SQL file does not mention `account_001`. The resource id is introduced by `activity_3342`. The snapshot is the proof of absence by omission after the id is known. See §6.

6. **Sample citations are all `file_id`s.** No `activity_NN` or `audit_NN` value appears. The contract allows both. Do not conclude they will be absent from hidden cases.

7. **System ids in the sample** are `account_service`, `search_service`, `support_platform`, `analytics_platform`, `security_service`, `integration_service`, `backup_service`, `export_service`, `identity_service`. Resource prefixes are `account_`, `search_`, `support_`, `analytics_`, `audit_record_`, `data_flow_`, `backup_`, `export_`, `tombstone_`. This is the sample's vocabulary, not the closed set. Activity and the rules also contain cache, marketing, email delivery, legal hold, and object storage.

## 4. Operation counts

`COMPLETE` (10 cases, 34 steps, all verification):

| Operation | Steps |
| --- | ---: |
| VERIFY_RECORD_ABSENT | 10 |
| VERIFY_RECORD_PRESENT | 7 |
| VERIFY_RECORD_ANONYMIZED | 7 |
| VERIFY_RECORD_REDACTED | 4 |
| VERIFY_DATA_FLOW_DISABLED | 3 |
| VERIFY_RESTORE_BLOCKED | 3 |

`INCOMPLETE` (22 cases, 41 findings, 41 remediations, 77 verifications):

| Operation | Steps |
| --- | ---: |
| REPORT_REMAINING_RECORD | 21 |
| REPORT_EXPOSED_PII | 11 |
| REPORT_ACTIVE_DATA_FLOW | 6 |
| REPORT_RESTORE_RISK | 3 |
| DISABLE_DATA_FLOW | 6 |
| BLOCK_RESTORE | 3 |
| DELETE_RECORD | 21 |
| REDACT_RECORD | 6 |
| ANONYMIZE_RECORD | 5 |
| VERIFY_RECORD_ABSENT | 40 |
| VERIFY_RECORD_PRESENT | 17 |
| VERIFY_RECORD_REDACTED | 6 |
| VERIFY_RECORD_ANONYMIZED | 5 |
| VERIFY_DATA_FLOW_DISABLED | 6 |
| VERIFY_RESTORE_BLOCKED | 3 |

Finding counts equal the matching remediation counts. `REPORT_EXPOSED_PII` splits into redact (support messages, tombstone) and anonymize (analytics). The 21 deletes match the 21 remaining-record findings. The extra verifications are the already-satisfied end states.

## 5. Worked patterns

The ids below are public sample ids. They illustrate the pattern. They are not templates for production rows.

### Simple absence

`case_01` is `COMPLETE` with one step: `VERIFY_RECORD_ABSENT` on `account_service` / `account_001`, evidence `evidence_54`. The workflow also said `COMPLETE`. The request text is an ordinary English closure request. No security log is verified, because none is in the cited evidence for this subject.

`case_02` is the same shape for `account_002`, but the workflow had said `PARTIALLY_COMPLETE`. The canonical status is still `COMPLETE`. One verification step is enough when that is the only relevant end state.

### Absence plus retained and anonymized records

`case_03`, `case_21`, and `case_25` verify, in operation order: account absent, security audit present, analytics anonymized. `case_04` has no security row in its evidence, so it verifies only account absent and analytics anonymized, using two different files.

`case_26`, `case_27`, and `case_28` are the full compliant set: account absent, security present, support redacted, analytics anonymized, data flow disabled, backup restore blocked. Six verifications, one evidence file each case (`evidence_92`). `case_26` and `case_28` were reported `NOT_STARTED`. The evidence shows the work is already done. `case_28`'s request text warns that a similar email belongs to someone else. The steps do not include that other person's search record.

### Remaining record only

`case_05`: workflow `COMPLETE`, canonical `INCOMPLETE`. Finding `account_005` present (`evidence_54`, the failover-only row), delete it, verify it absent. No extra security step.

`case_06`, `case_07`, `case_08`, `case_10`: the account is already gone, and one downstream copy remains (search, support attachment, export, support replica). The finding names the copy. Verification names both the already-absent account and the copy that still must disappear. `case_07`'s evidence is the PDF attachment `evidence_58`. `case_10` uses the historical email and `evidence_61`.

### Restore risk and active flow, with the profile already gone

`case_09`, `case_14`, `case_17`: the only finding is `REPORT_RESTORE_RISK`. Remediation is `BLOCK_RESTORE`. Verification is account absent, security audit present, restore blocked.

`case_15`: the only finding is `REPORT_ACTIVE_DATA_FLOW` on `data_flow_9846` (`evidence_01` heartbeat `enabled=true`). Same end-state shape with `VERIFY_DATA_FLOW_DISABLED` instead of the restore check.

`case_05`'s activity log also contains a `SYNC_RECORD` onto `account_failover_replica` after a `SUCCESS` delete. The canonical finding is `REPORT_REMAINING_RECORD`, not an active flow. The sync already happened. The row is present. An enabled connector is the active-flow case. A finished sync is a remaining record.

### Mixed violations, operation order rather than system order

`case_11` is the clearest ordering example. Findings, after the operation table then system id:

1. `REPORT_REMAINING_RECORD` `search_service` `search_052`
2. `REPORT_EXPOSED_PII` `analytics_platform` `analytics_2034`
3. `REPORT_EXPOSED_PII` `support_platform` `support_864`
4. `REPORT_ACTIVE_DATA_FLOW` `integration_service` `data_flow_9522`

Remediation follows the table, so the flow is disabled before any record edit, and delete sorts before redact before anonymize:

5. `DISABLE_DATA_FLOW` `data_flow_9522`
6. `DELETE_RECORD` `search_052`
7. `REDACT_RECORD` `support_864`
8. `ANONYMIZE_RECORD` `analytics_2034`

Verification then adds the account and the security log, which were not remediated:

9. `VERIFY_RECORD_ABSENT` `account_4248`
10. `VERIFY_RECORD_ABSENT` `search_052`
11. `VERIFY_RECORD_PRESENT` `audit_record_9394`
12. `VERIFY_RECORD_REDACTED` `support_864`
13. `VERIFY_RECORD_ANONYMIZED` `analytics_2034`
14. `VERIFY_DATA_FLOW_DISABLED` `data_flow_9522`

`case_18`, `case_29`, and `case_30` repeat this shape with different ids. The support rows are `REDACT` because the message is shared or still identifiable and must be kept. The analytics rows are `ANONYMIZE` because they are still attributable. The search rows are `DELETE`.

`case_16` puts `DELETE_RECORD` for `account_service` before `search_service`. Both operations are the same, so system id decides. That is the opposite of "delete the downstream copy first". Follow system id.

### Tombstone

`case_31` request text allows an internal deleted-account reference. Status `COMPLETE`. Steps: account absent, security audit present, `tombstone_440` redacted (`identity_service`). In `evidence_51` the tombstone's name, email, phone, and email hash are null and `subject_reference` is `user_541`.

`case_32` is `INCOMPLETE`. The account is gone, but `tombstone_9178` still has the name, email, phone, and hash. Finding `REPORT_EXPOSED_PII`, remediation `REDACT_RECORD`, verification of account absent, security present, and tombstone redacted.

### Delete versus anonymize under `analytics_`

`case_12` finds `analytics_9914` as `REPORT_REMAINING_RECORD` and deletes it. It does not anonymize it. The cited log line is `contact_lookup_completed` with `email_opt_in=true` and a correlation hash, not an analytics profile with a cohort. Other `analytics_` resources that still contain an email are `REPORT_EXPOSED_PII` plus `ANONYMIZE_RECORD` (`case_11`, `case_22`). The prefix does not determine the action. The record type and the remaining identifiers do.

`case_19` redacts a support message and deletes a search document. The request text says the conversation also concerns another customer, which matches `rule_05`.

## 6. Activity claims versus canonical state

Activity rows near `reported_at` contain most of the resource ids that later appear in the steps. They do not contain the correct state. Representative contradictions:

| Case | Activity claim | Canonical state |
| --- | --- | --- |
| case_05 | `DELETE_RECORD` `account_005` `SUCCESS`, then sync to the failover replica | Record still present on the failover snapshot |
| case_10 | `DELETE_RECORD` `support_002` `SUCCESS` | Support row still present, deletion marker false |
| case_16 | `DELETE_RECORD` `search_1007` `SUCCESS` | Search record still a finding |
| case_24 | Account and search deletes `SUCCESS`, plus a replication sync | Both records still findings |
| case_25 | Account delete `FAILED` | Account is absent; case is `COMPLETE` |
| case_09 | Account delete `FAILED` | Account is verified absent; the real gap is restore access |

`SUCCESS` is not absence. `FAILED` is not presence. The evidence snapshot at or before `audit_at` decides. Activity is useful as a candidate-id source and as a claim to be checked.

Security audit resource ids often do not appear in the deletion-worker cluster at all. They show up in the evidence (handover lines, service export, snapshot bundle) linked by `user_id`. The planner has to add `VERIFY_RECORD_PRESENT` from that evidence even when no activity row mentions the audit record.

## 7. The `account_001` link

`account_001` occurs in `system_activity.csv` once: `activity_3342` at `2026-08-20T16:41:43Z`, `DELETE_RECORD`, `SUCCESS`, detail text that names the resource and not the email. It does not occur in any evidence file. `evidence_54`, the cited proof, contains four other profiles, including `account_005` and two name-alikes, and not `account_001`.

`case_01`'s `reported_at` is `2026-08-20T16:42:00Z`, 17 seconds later, and that timestamp is not shared with another sample case. Later sample accounts do not use `user_NN` to `account_NN` (`user_43` to `account_7566`). A numbering shortcut would pass `case_01` and fail the rest.

This is the sharpest sample gap: the resource id and the proving file are in different artifacts, and the id is not written next to the email. The implementation has to recover that link without hardcoding it, then test the same recovery against all 32 cases. Shared `reported_at` values make a pure time join wrong for the later cases. Their resources are identifiable from evidence contents. `case_01` is the one that may need the activity row as the id source and the SQL snapshot as the state source.

## 8. What the sample does not teach

- No `NOT_APPLICABLE` serialization other than the problem statement's `[]` illustration.
- No `activity_id` or `audit_id` citation, though both are legal.
- No cache, marketing, email-delivery, legal-hold, or object-storage step.
- No case where two resources in the same operation and system have digit lengths that distinguish lexicographic and numeric `resource_id` order.
- No case where primary and replica disagree on a column of a shared key. They only disagree by extra replica rows.
- No image citation. `case_07` does show that a PDF can be the sole cited proof of a remaining attachment.

Use the sample to lock schema, ordering, policy-to-operation mapping, claim rejection, replica presence, tombstones, and historical email. Use synthetic fixtures for the gaps above. Do not treat a sample id as a production answer.
