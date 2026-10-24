# Policy engine

This is the decision record for the Phase 3 auditor. `problem_statement.md` is the specification. Public sample rows are a score, not a second rule table, and they are not read while a prediction is built.

## Applicability

`classify_request` is lexical. A deletion stem authorizes deletion unless it sits in a negation window (`must not`, `do not`, `ne pas`, and the same shape in the other listed forms). Additional authorizing phrases are `profile is gone`, `cannot identify me`, and `already been removed`. Those cover requests that ask whether an account and identifiable analytics have already been removed, or ask to confirm the profile is gone.

`remove me from marketing lists only` stays non-deletion. The `remov*` stem has to take an object such as `my`, `the`, `records`, or `this`. A marketing-list opt-out does not authorize account deletion. Access, correction, and export requests stay non-deletion. `NOT_APPLICABLE` returns `steps_json=[]`.

The earlier seven non-deletion predictions were not forced to six. Six texts are explicit non-deletion requests. The seventh is the marketing-list opt-out, which the lexicon still treats as non-deletion.

## Identity

Joins use case-insensitive email, digit-normalized phone, exact email hash, and `user_id`. Names are stored and never joined. Account ids are not padded from `user_N`. An email that matches more than one user stays ambiguous and produces no resource steps.

`LINK_RESOURCE_IDENTITY` rows are accepted only when the named email resolves to the named user. Nested `subject_reference` values inside SQL `record_json` are identifiers. A finance-register `ORD-` note stays `FINANCE_RETENTION_NOTE` and is not a legal hold. A legal-hold row is in scope only when its own record carries the subject.

## Categories and treatments

The category comes from the record type or the SQL collection name, not from the resource prefix.

| Category | Treatment when the record is still in the prohibited state |
|---|---|
| `USER_PROFILE`, `SECONDARY_IDENTIFIER`, `SEARCH_INDEX_ENTRY`, `CACHE_ENTRY`, `SUPPORT_ATTACHMENT`, `USER_EXPORT`, `MARKETING_PROFILE` | Delete the record |
| `SUPPORT_MESSAGE`, `EMAIL_DELIVERY_LOG` | Redact direct identifiers |
| `ACCOUNT_TOMBSTONE` | Keep the stable user reference. Remove name, email, phone, and email hash |
| `ANALYTICS_PROFILE`, `PRODUCT_TELEMETRY` | Anonymize while the row is still attributable |
| `SECURITY_AUDIT_LOG` | Retain while `retention_until` is absent or still in the future |
| `LEGAL_HOLD_RECORD` | Retain. Redact when direct identifiers are still exposed |
| `DATA_FLOW` | Disable when the connector is enabled |
| `BACKUP_ARCHIVE` | Block restore. Do not delete the archive |

`CONTACT_LOOKUP` is a marketing profile and is deleted. A support `contact_query` or deletion-marker check with no conversation excerpt is a support attachment and is deleted. A support row with message text or shared context stays a message and is redacted.

A present retained security log or a redacted tombstone is compliant. Compliance is a verification step, not a finding. A `SUCCESS` delete in `system_activity.csv` is a claim. The timeline drops claims, so the claim does not become absence.

Direct identifiers are name, email, phone, and email hash. A user id alone does not make a tombstone non-compliant. Analytics stay attributable when they are not marked anonymized and still carry a direct identifier or another linkable identifier. An anonymized analytics row with empty identifiers is compliant only when that row is actually linked to the subject. Absence of an analytics row is not treated as proof that some other analytics row was anonymized.

## Evidence precedence

An observation is eligible when both `captured_at` and the inner `observed_at` are at or before `audit_at`. A file captured later is ignored for that case.

Within one canonical system and resource, a present replica outranks absence. The latest present observation wins. Replica system ids that are themselves canonical (`account_failover_replica`, `account_replication_cluster`) stay distinct. `support_replica` and `profile_service` are source labels, not systems, and map to `support_platform` and `account_service`. Any other unknown store name is replaced by the category's system (`analytics_identity_store` becomes `analytics_platform` for an analytics profile). Prefixes are used only when the source named no system. String similarity is not a join.

An absence whose observation time is before `requested_at` does not prove absence at `audit_at`. A later eligible observation can still show the record present.

A workflow detail that contains `Target resource:` can name a resource for that request when the event is inside ten minutes of `reported_at`, is at or before `audit_at`, and no eligible observation assigns the resource to someone else. Other deletion-worker rows are not joined by time. Shared `reported_at` values interleave unrelated accounts.

If that named account has no eligible observation, and a user-profile snapshot captured at or after `reported_at` and at or before `audit_at` does not list it, the planner records a low-confidence absence on that snapshot. A snapshot that never mentions the account is still a partial extract. The rule is limited to accounts the workflow explicitly targeted. It is not a global closed-world assumption.

## Steps

Findings cite the evidence id of the winning observation. Remediation and the future checks that follow it use an empty evidence id. A `COMPLETE` row has only verification steps, and each one cites eligible evidence. An `INCOMPLETE` row has findings, remediation, and verification. Already-compliant records on an incomplete case contribute verification with an empty evidence id, because that check is part of the future confirmation rather than a new proof.

Order is `FINDING`, then `REMEDIATION`, then `VERIFICATION`. Inside a phase the order is the allowed-operations table, then `system_id`, then lexicographic `resource_id`. `step_no` is assigned after that sort. Status is `COMPLETE` only when there is at least one treatment and none of them is a violation or a conflict. Otherwise an authorized deletion is `INCOMPLETE`.

## Images

All eleven screenshots are stored as structured observations in `code/ingestion/image_facts.py`. The image parser emits those observations and keeps the original file id. The cache is source-controlled so a packaged run does not need the chat that read the pixels. Visually confirmed facts are the identifiers, states, and timestamps written on each row. Relationships marked in `limitations` are not joins. `search_428` and `search_1874` stay separate. `evidence_42` is a customer reference for `user_17`, not a tombstone id. `evidence_46` lists filenames and does not name a customer, so those rows are not deletion resources.

## Unresolved links

These gaps are left open because the available evidence does not support a general join. They are not special cases in the planner.

- `evidence_54` is a four-account failover snapshot plus a primary extract. It does not contain `account_001`. The sample cites that file for `account_001` absence. The only participant-facing mention of `account_001` is a deletion-worker claim. A later partial snapshot is not proof that every unnamed account is absent, so the id is not inserted by hand.
- `account_004` does not appear in activity or in evidence. The sample cites `evidence_54`. There is no general rule that discovers it.
- Multi-user exports such as `evidence_92` contain HTTP 404 accounts and analytics rows whose email, phone, hash, and customer reference are null. The same file also contains other subjects. Assigning those rows by activity time, or by sharing a file with an identified row, attaches them to the wrong subject. They stay unlinked.
- `analytics_9406` in the 2026-09-26 readback log has a null lookup key and a different trace id from the account lookup. It is not joined to that account.
- Several incomplete-case account and security-log checks in the sample have empty evidence ids, and the resource itself is missing from every file eligible at `audit_at`. Some of those rows exist only in a file captured after `audit_at` (the 2026-09-18 service log for an audit on 2026-09-15). Post-audit files are not used. A deletion-worker `SUCCESS` line names a resource and does not identify the person.
- Legal-hold activity rows that say `Policy action completed for legal_hold_N` do not name a user. They are not attached by time. A hold is linked only through `subject_reference` on the record.

## Phase 4 verification coverage

`code/evaluation/missing_steps.py` compares predictions with the public sample only after the auditor has returned. It classifies each missing step and does not feed those rows back into the planner.

A same-trace `lookup_key` is copied from the start line onto the completion line. The literal values `null`, `none`, and `n/a` are not keys, so they do not block a real key on that trace and they do not spread onto a different trace. Checked across the log files, no completion line was dropping a real key that an earlier line on the same trace had already stored. The public-sample score did not change.

`snapshot_scope` records which systems were captured and when. It does not list the resource population, so it is not a closed-world scope. An empty `customer_profiles` array does not prove that a named account is absent. Paired SQL absence still requires the resource id to appear on the other table in the same file. A longer id such as `account_41038` is not a match for `account_410`.

The 28 missing public-sample steps, after that review:

| Class | Count | Meaning |
|---|---|---|
| A Parser omission | 0 | The id is in a file and no observation was emitted |
| B Identity-resolution omission | 11 | An eligible observation exists and its identity fields are empty |
| C Temporal-state reconstruction omission | 6 | The only observation is captured after `audit_at` |
| D Resource-association omission | 7 | An activity names the resource and does not name the subject |
| E Policy or verification-coverage omission | 0 | A linked compliant resource produced no verification step |
| F Unverifiable from participant-facing evidence | 4 | The cited file or the whole participant dataset does not contain the resource |

Every one of those 28 has `independently_established=false`. No class E gap remains: every compliant resource the planner can link already gets one verification step.

Phase 5 tested using inner event time when the file package is later. That lowered exact-row accuracy from 15/32 to 12/32 and was reverted. The write-up is `exact_match_investigation.md`.

`evidence_54` names four failover accounts and three primary accounts. It does not name `account_001` or `account_004`. `account_004` also has no activity row. `evidence_51` has an empty account collection and tombstones for two users. It does not name `account_4857`. `evidence_92` repeats that pattern for several accounts and analytics rows whose email, phone, hash, and customer reference are null, in a file that also contains other subjects. Later bundles sometimes repeat those resources with a subject key, and those bundles are captured after the case `audit_at`. Two security-log ids in the public answers do not appear in any participant file or activity. Those links stay unresolved.
