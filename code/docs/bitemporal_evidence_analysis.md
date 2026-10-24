# Bitemporal evidence analysis

The public-sample baseline before this phase was 32/32 status accuracy and 15/32 exact rows. A previous experiment treated an inner event time as enough to make a whole later package eligible for identity, state, and citation. That run scored 30/32 status and 12/32 exact rows and was not kept. This phase separates those clocks instead of reversing the package gate.

## Clocks

| Clock | Where it lives | What it means |
| --- | --- | --- |
| `event_at` / `snapshot_at` / `state_observed_at` | `Observation.observed_at` | When the row says the fact happened or the snapshot was taken |
| `package_created_at` | `Observation.captured_at` and the evidence manifest | When the file or export was assembled |
| `audit_at` | the deletion request | The moment the answer must describe |

`valid_from` and `valid_until` are not present as columns on the evidence records. Identity history still uses the audit-log effective time. Retention uses `retention_until` on the record.

## What each clock may support

State and citations still require both clocks. `Observation.eligible_at()` returns false when the package was captured after `audit_at`, and also when the inner observation is after `audit_at`. A finding, and a verification on a `COMPLETE` case, may cite only a package that passes that test.

Identity lineage uses the inner time only. A snapshot or log packaged later can show that a resource belonged to a subject at an earlier `observed_at`. That link is dropped when another subject's identifiers also appear on the resource, and it is dropped when the inner time is after the audit. The later package is not added to the state timeline.

Historical state is a third, narrower use. If the resource has no observation that passes `eligible_at()`, and the inner event is at or before the audit, that event may establish state for a case that is already `INCOMPLETE`. The step cites nothing, because the package is after the audit. The later event never replaces an eligible observation of the same resource. It cannot turn a case `COMPLETE`, and it cannot become a finding: a finding has to cite an admissible file.

## Rejected reading

Using `observed_at` as the only eligibility test lets a later export overwrite an earlier admissible state. On the public sample that removed the `evidence_54` account citations for the early cases and replaced the exposed `support_5281` and `support_6477` rows from `evidence_92` with a later redacted copy. Status fell to 30/32 and exact rows fell to 12/32.

## Chosen reading

`evidence_02` was packaged on 2026-09-17 and contains a 2026-09-09 profile snapshot for `account_5684` plus 2026-09-15 security-log snapshots. `evidence_92` was packaged on 2026-09-15 and contains the 404 for `account_5684` with an empty profile. Lineage takes the September 9 ownership. State stays the eligible 404. The September 17 profile of `account_3866` is dated 2026-09-17, which is after the September 15 audits, so it is not ownership at those audits.

`evidence_06` was packaged on 2026-09-18 and contains 2026-09-16 events for `account_3960` and `audit_record_4902`. Those events supply state only because no eligible observation of those resources exists, and only on a case that is already incomplete. They are not citations.

## Hidden-test implication

The same split applies to every request. A package after `audit_at` cannot create a cited finding, cannot erase an earlier eligible exposure, and cannot by itself mark a deletion complete. Hidden cases that only differ by file name and timestamp follow the same rules. Cases whose resources never carry a subject key still cannot be joined.
