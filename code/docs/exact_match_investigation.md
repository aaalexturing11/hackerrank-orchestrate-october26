# Exact-match investigation

This note records the Phase 5 attempt to recover the 28 public-sample verification steps. Predictions are still produced without reading `sample_output.csv`. The sample is used only after prediction.

## Baseline

Before this phase the auditor scored:

| Metric | Value |
|---|---|
| Status | 32/32 |
| Exact row | 15/32 |
| Positional field | 847/1158 |
| Sequence | 15/32 |
| Operation precision | 165/165 |
| Operation recall | 165/193 |
| Missing / extra operations | 28 / 0 |

## Hypothesis 1 — Scope is weaker than state

A deletion-worker event might put a resource in the audit scope without proving absence. The check could then be emitted with empty evidence on an incomplete case.

What the activity rows actually contain: `Deletion worker submitted primary profile account_6440 to account_service.` There is no email, user id, case id, or trace shared with the request. The same minute contains deletes for other accounts. `reported_at` values are shared across cases, so a window around that timestamp attaches the wrong account. A previous 45-minute same-file rule did the same thing and was removed.

Rejected. A workflow claim establishes that some deletion was attempted. It does not establish which person owns the resource.

## Hypothesis 2 — Trace and snapshot lineage

Same-trace `lookup_key` propagation is already implemented. A scan of the logs found no completion line that dropped a real key stored earlier on that trace. Null analytics rows use a different trace id from the account lookup (`analytics_9406` is `rb-095409-021`; the account lookup is `rb-085737-009`).

`evidence_02` (`customer_data_snapshot_bundle_20260917.json`) is the useful counterexample. The file manifest time is `2026-09-17T12:00:00Z`. Inside it:

- `account_5684` sits in a snapshot declared `captured_at` `2026-09-09T12:00:00Z` with `customer_reference` `user_26` and the subject's email.
- Security rows such as `audit_record_4128` (`user_23`), `audit_record_7095` (`user_24`), `audit_record_3954` (`user_29`), and `audit_record_1707` (`user_30`) sit in a snapshot declared `2026-09-15T12:00:00Z`.
- Several analytics rows in that same noon snapshot have `user_id`, email, phone, and hash null. Two others in the same array name `user_29` and `user_30`. The null rows are not children of those users.
- `account_3866` is in a snapshot declared `2026-09-17T12:00:00Z`, the same instant as the package.

`evidence_06` is a log packaged `2026-09-18`. Its lines for `account_3960` and `audit_record_4902` have event times on `2026-09-16` before `case_09`'s audit, on traces that do name the subject.

`evidence_92`, which the sample cites, still has null identity fields on the 404 accounts and the anonymized analytics rows. The identifying copy of those accounts is in the later bundle.

## Hypothesis 3 — Package time should not hide an earlier event

Experiment: treat `observed_at` as the eligibility clock and keep the file's `captured_at` only as the citation clock. Snapshot `updated_at` was not used as that clock. A later file could supply identity and state for an event that occurred before `audit_at`, while a step could be cited only from a file packaged by `audit_at`.

Measured result:

| Metric | Baseline | Experiment |
|---|---|---|
| Status | 32/32 | 30/32 |
| Exact row | 15/32 | 12/32 |
| Positional field | 847/1158 | 789/1158 |
| Sequence | 15/32 | 12/32 |
| Precision | 165/165 | 163/163 |
| Recall | 165/193 | 163/193 |
| Missing / extra | 28 / 0 | 30 / 0 |

What broke:

- `case_01` and `case_02` stopped citing `evidence_54`. The omission helper treated a later profile package as the latest snapshot, that package cannot be cited, and the verification was dropped.
- Support rows in `evidence_92` that still expose an email were overridden by a later packaged snapshot of the same resource that no longer carries the email. The sample still cites `evidence_92` for `REPORT_EXPOSED_PII` on `support_5281` and `support_6477`.
- Class C (event only in a post-audit package) fell to 0, and new class E gaps appeared. Recall went down.

The experiment was reverted. A regression test now locks the rule: an event timestamp before `audit_at` inside a file packaged after `audit_at` is not eligible.

Why the revert matches the contract: `problem_statement.md` says evidence created later must not change the answer. The manifest `captured_at` is when that evidence file was created. Inner snapshot labels are claims inside a file the audit did not yet have. Using them changed answers, including two previously exact rows, and hid exposed identifiers that the citable file still shows.

## Hypothesis 4 — Empty collections and paired snapshots are closed worlds

`evidence_51` has `"records": []` for `customer_profiles` and names `user_541` only on a tombstone and a security row. It does not contain the string `account_4857`. An empty array does not say which account ids were in scope.

`evidence_54` has four failover profile rows and three primary rows. `account_001` and `account_004` are on neither table. Paired absence is limited to an id that appears on the other table. `snapshot_scope` names systems and a capture time. It does not list the resource population.

`account_004` has no activity row either. `audit_record_6645` and `audit_record_5569` do not appear in any participant file or activity.

These stay unresolved. No observation is invented.

## Hypothesis 5 — Verification coverage bug

Class E was 0 on the baseline: every compliant resource the planner can link already produces one verification. The class E rows in the experiment were artifacts of the reverted clock, not a missing branch in the planner.

## What remains missing on the restored baseline

All 28 are verifications. None has a subject key in a file packaged at or before `audit_at`.

| Class | Count | Cases |
|---|---|---|
| B. Eligible row, empty identity | 11 | `case_03`, `case_21`, `case_25`, `case_26`, `case_27`, `case_28` |
| C. Only copy is packaged after `audit_at` | 6 | `case_09`, `case_23`, `case_24`, `case_29`, `case_30` |
| D. Activity names the resource and not the subject | 7 | `case_18`, `case_20`, `case_22`, `case_23`, `case_29`, `case_30`, `case_32` |
| F. Resource is absent from the cited file or from the dataset | 4 | `case_04`, `case_18`, `case_20`, `case_31` |

The identifying snapshot for several of the class B accounts is inside `evidence_02`, packaged two days after the audit that cites `evidence_92`. Using that package is hypothesis 3, which failed the regression check.

## Hidden-test check for any future rule

A rule that reads a file packaged after `audit_at` fails questions 2, 6, and 8 in the phase brief: the contract forbids later evidence, the experiment created false state (redacted support replacing exposed support), and it changed previously exact rows. It is not a candidate for the 518-case run.

## Alignment diagnostic

Positional field accuracy compares step *i* with step *i*. A missing verification shifts every later field. `aligned_field_accuracy` compares steps that share phase, system, resource, and operation. The positional number remains the reported field accuracy.
