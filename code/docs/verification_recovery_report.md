# Verification recovery report

Baseline before these experiments: status 32/32, exact rows 15/32, positional fields 847/1158, sequence 15/32, precision 165/165, recall 165/193, missing 28, extra 0. Unit tests were 34. The 518-request dry run was valid.

## Experiment A — identity lineage separate from state

A resource id is owned by the audit subject when some observation at or before `audit_at` carries that subject's email, phone, email hash, or user id, and no observation carries a different subject's identifiers. The file's package time does not block the link. The row is not used as state.

Measured result:

| Metric | Baseline | After A |
| --- | --- | --- |
| Status accuracy | 32/32 | 32/32 |
| Exact-row accuracy | 15/32 | 15/32 |
| Field accuracy | 847/1158 | 861/1158 |
| Sequence accuracy | 15/32 | 15/32 |
| Operation precision | 165/165 | 166/166 |
| Operation recall | 165/193 | 166/193 |
| Missing steps | 28 | 27 |
| Extra steps | 0 | 0 |

Recovered: `case_26` `VERIFY_RECORD_ABSENT` for `account_5684`, citing `evidence_92`. The owner is the 2026-09-09 snapshot inside `evidence_02`. The state is the eligible 404 in `evidence_92`. `support_5281` and `support_6477` stayed on the exposed `evidence_92` rows. Kept.

## Experiment B — workflow scope versus the ten-minute window

`system_activity.csv` has no case id, user id, trace id, or correlation id. The only explicit target text is `Target resource:`. Those rows are the early accounts and related records already in scope. The other deletion-worker rows, such as `account_6440` and `account_410`, name a resource and a result, and they are interleaved across subjects that share a `reported_at`. Widening the ten-minute window was already measured to attach the wrong accounts. This experiment leaves that window unchanged and records scope as `ResourceScope` with source `named_target_only`. A worker row without the target phrase is not in scope even inside the window.

Measured delta versus experiment A: no change. Extra operations stayed 0. Missing operations stayed 27 until experiment C.

## Experiment C — historical state only when nothing eligible exists

JSON snapshots already store the snapshot time on `observed_at` and the file time on `captured_at`. The timeline was still dropping any row whose package was late, so a lineage hit had no state to join.

The added rule reconstructs those rows only for a resource that has no eligible observation. A compliant result may be emitted when the case is already `INCOMPLETE`, with an empty `evidence_id`. A later row cannot win over an eligible row. It cannot be a finding, and it cannot make the case `COMPLETE`.

Measured result after A and C:

| Metric | Baseline | After A + C |
| --- | --- | --- |
| Status accuracy | 32/32 | 32/32 |
| Exact-row accuracy | 15/32 | 17/32 |
| Field accuracy | 847/1158 | 889/1158 |
| Sequence accuracy | 15/32 | 17/32 |
| Operation precision | 165/165 | 172/172 |
| Operation recall | 165/193 | 172/193 |
| Missing steps | 28 | 21 |
| Extra steps | 0 | 0 |

Recovered verifications, seven in total:

| Case | Operation | Resource | Evidence |
| --- | --- | --- | --- |
| case_26 | VERIFY_RECORD_ABSENT | account_5684 | evidence_92 |
| case_09 | VERIFY_RECORD_ABSENT | account_3960 | empty |
| case_09 | VERIFY_RECORD_PRESENT | audit_record_4902 | empty |
| case_23 | VERIFY_RECORD_PRESENT | audit_record_4128 | empty |
| case_24 | VERIFY_RECORD_PRESENT | audit_record_7095 | empty |
| case_29 | VERIFY_RECORD_PRESENT | audit_record_3954 | empty |
| case_30 | VERIFY_RECORD_PRESENT | audit_record_1707 | empty |

`case_09` and `case_24` became exact rows. The security rows come from the 2026-09-15 snapshot inside `evidence_02`, or from the 2026-09-16 events inside `evidence_06`, and the cases were already incomplete for an admissible reason. Repeatable. Kept.

Synthetic coverage: a late package supplies ownership without replacing an early 404 or an early exposed support record; a competing owner blocks the link; a historical security event fills only a resource with no eligible state; a later package does not make the event eligible for citation.

## Experiment D — snapshot absence

No change to absence inference. A partial export is not an inventory. SQL absence is still only an id present on one side of a primary/replica pair. Account omission is still limited to an anchored `Target resource:` account missing from a profile snapshot captured between `reported_at` and `audit_at`. That is what cites `evidence_54` for the early accounts even though `account_001` is not a row in the SQL. Widening it would invent absences. Measured delta: 0. The existing account-absence verifications still match.

## Experiment E — replicas

No change to merge order. Within one replica, the latest observation wins, so a later absence replaces an earlier present on that replica. Across replicas of the same canonical system, a present copy is kept, so an absent primary does not hide a present failover. `account_failover_replica` stays its own system id. Synthetic tests cover both. Measured sample delta: 0.

## Policy check

`deletion_rules.csv` has 15 rules. For a state that meets each rule's condition, `decide()` returns that rule's `required_action`: DELETE, REDACT, ANONYMIZE, or RETAIN. A security log whose `retention_until` is before the audit produces no treatment. The category behavior is checked against the file rather than left untested.

## Remaining 21 operations

Identifier-free state, ten operations. The resource exists in an eligible file, and every identifier column is null. No other file assigns an owner at or before the audit.

| Case | Resource | State file | Why it stays out |
| --- | --- | --- | --- |
| case_03 | analytics_9406 | evidence_94 | null lookup key; the neighboring trace is a different trace |
| case_21 | account_6440 | evidence_92 | 404 with a null profile |
| case_21 | analytics_5335 | evidence_92 | null identifiers; the later snapshot is also null |
| case_25 | account_3136 | evidence_92 | 404 with a null profile |
| case_25 | analytics_1895 | evidence_92 | null identifiers |
| case_26 | analytics_4566 | evidence_92 | null identifiers |
| case_27 | account_3866 | evidence_92 | 404 with a null profile; the identifying snapshot is dated 2026-09-17, after the audit |
| case_27 | analytics_4574 | evidence_92 | null identifiers |
| case_28 | account_5482 | evidence_92 | 404 with a null profile |
| case_28 | analytics_6077 | evidence_92 | null identifiers |

Activity without a subject, seven operations. The worker text names the resource and not the person. There is no shared workflow id, and the events of different subjects overlap.

`account_5521` (case_18), `account_5037` (case_20), `account_4990` (case_22), `account_410` (case_23), `account_7012` (case_29), `account_4163` (case_30), `account_8858` (case_32).

Unsupported by participant evidence, four operations. A search of the evidence JSON, SQL, and logs does not contain the id. The activity stream also does not contain the two audit records.

| Case | Resource | Cited by the sample | What exists |
| --- | --- | --- | --- |
| case_04 | account_004 | evidence_54 | neither the id nor an activity |
| case_18 | audit_record_6645 | empty | no file and no activity |
| case_20 | audit_record_5569 | empty | no file and no activity |
| case_31 | account_4857 | evidence_51 | activity_3682 only; evidence_51 does not contain the id |

These four are exact-match targets the supplied data does not establish. They are not filled in from the sample answer.

## Production run

`python code/main.py` writes repository-root `output.csv` through `DeletionAuditor`, the same auditor the sample scorer uses. The run processed 518 requests, parse failures 0, contract violations 0, invalid evidence references 0. Status counts: COMPLETE 162, INCOMPLETE 349, NOT_APPLICABLE 7. Rows are sorted by `case_id`. No `COMPLETE` row has an empty step list. One intermediate run marked `case_168` complete with no steps because its only state was an uncitable later package; that status effect was removed. Historical verifications are added only when the case is already incomplete.

## Generalization

The retained rules are about clocks, identifier intersection, and named targets. They do not mention case ids or sample resource lists. They will not recover a hidden case whose only join would be time proximity or a null identifier. They will recover the same pattern as `account_5684` and the late security snapshots whenever the files contain those facts.
