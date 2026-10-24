# Dataset Analysis

Inspection date: 2026-10-24. All counts below were computed by reading the participant files under `dataset/`. No dataset file was modified. `dataset/output.csv` is the blank template and was not filled in.

Coverage of this inspection:

- All nine CSVs were loaded and profiled, including every `steps_json` array in `sample_output.csv`.
- All 94 evidence paths in `evidence_files.csv` exist on disk. The disk tree has 94 files and no extras.
- All 24 SQL files were executed read-only in an in-memory SQLite database. Every script parsed.
- JSON, log, and text evidence were opened and structurally summarized.
- PDF text was extracted for all four PDFs: the delivery-address attachment, the disputed-order register, the customer statement, and the compliance-journal extract.
- Two of the eleven PNGs were inspected visually: `evidence_04` (account admin console) and `evidence_42` (deleted-account reference). The other nine PNGs were inventoried from the manifest and file sizes only. Their pixels were not read in this phase.

There is no `code/` starter, no `generator/` directory, and no root `output.csv` yet. `README.md` refers to `code/main.py` and `code/evaluation/main.py`, but those files are not in the checkout.

## 1. Population split

| File | Rows | Role |
| --- | ---: | --- |
| `deletion_requests.csv` | 518 | Cases that require predictions |
| `sample_deletion_requests.csv` | 32 | Public cases |
| `sample_output.csv` | 32 | Canonical answers for the public cases |
| `user_identities.csv` | 850 | Current identity snapshot |
| `user_audit_log.csv` | 306 | Historical identity changes |
| `system_activity.csv` | 4011 | Global operational claims |
| `deletion_rules.csv` | 15 | Policy |
| `evidence_files.csv` | 94 | Evidence manifest |
| `output.csv` | 0 data rows | Header `case_id,deletion_status,steps_json` only |

The 32 sample requests are a separate population.

- Sample ids are `case_01` through `case_32`, contiguous, already sorted.
- Production ids are `case_33` through `case_550`, contiguous (518 ids, none missing inside that range), not sorted in the file.
- Case-id intersection is empty.
- Two sample email addresses also appear on production requests: `priya.raman@gmail.com` and `leonie.g9352@outlook.com`. Those are the same identity records used as public examples and as hidden-eval subjects. Sample labels must not be copied onto the production rows. The audit times differ.
- One production subject has two cases: `ingrid.dahl@outlook.com` is `case_33` (`audit_at` 2026-07-19) and `case_52` (`audit_at` 2026-06-19). Each case is decided at its own `audit_at`.

## 2. CSV profiles

Null convention in the CSVs: empty fields are absent. No `null`, `None`, or `NA` tokens appeared. JSON evidence uses real JSON `null`. SQL uses SQL `NULL`. Step `evidence_id` uses `""` when the contract requires an empty citation.

Every timestamp column uses `YYYY-MM-DDTHH:MM:SSZ`. No offsets, no fractional seconds, no naive local times in the CSVs. Treat them as UTC. String order matches chronological order for this format.

### 2.1 `deletion_requests.csv`

Columns: `case_id`, `email`, `requested_at`, `reported_status`, `reported_at`, `audit_at`, `request_text`.

- 518 unique `case_id`. No empty cells.
- 517 distinct emails. The duplicate is `ingrid.dahl@outlook.com`.
- `reported_status`: `COMPLETE` 254, `PARTIALLY_COMPLETE` 152, `NOT_STARTED` 112.
- Time order on every row: `requested_at` <= `reported_at` <= `audit_at`.
- Ranges: requested 2026-01-05 to 2026-09-24; audit 2026-01-29 to 2026-10-01.
- 375 distinct `request_text` values. 80 texts are reused, maximum reuse 14. Several texts are templates shared across many cases, so text identity is not a case family key and must not be hardcoded.
- Scripts: 456 Latin, 38 Latin with non-ASCII letters (accents and similar), 12 Hangul, 12 CJK plus kana. Sample adds Spanish, French, and one Japanese request. No Arabic, Cyrillic, Devanagari, Hebrew, or Thai turned up in a script scan.

Email resolution against the identity tables, case-insensitive:

- 418 production emails match the current snapshot.
- 100 match a historical email only.
- 0 are unresolved.
- Historical examples include case differences (`CHOI.JIHOON94@GMAIL.COM` versus the later stored address). Fold case for email equality.

Non-deletion text that was read directly:

- `case_533`: replace the mobile number and leave the account active.
- `case_535`: portable download, keep the account.
- `case_536`: login reset, do not close the account.
- `case_540`: copy of invoices, leave the profile and purchase history.
- `case_541`: change the email and continue using the service.
- `case_542`: copy of information held, do not delete or change anything.

All six have `reported_status` `NOT_STARTED`. They are the explicit English `NOT_APPLICABLE` candidates. A stem search does not find further obvious English non-deletion texts. Ten `CLASSIFY_REQUEST` activity rows claim a non-deletion classification for ten account ids. Those rows do not carry `case_id` or an email, and they are claims. The text classifier has to decide. The ten claims and the six explicit texts are not yet joined; that join is an implementation task, not a license to trust the activity row.

### 2.2 `sample_deletion_requests.csv`

Same columns as production. 32 rows, 32 emails, all resolved: 29 current, 3 historical (`case_10`, `case_29`, `case_30`). Reported status: `COMPLETE` 17, `NOT_STARTED` 10, `PARTIALLY_COMPLETE` 5. Every sample request that was read authorizes deletion, including indirect phrasing ("close my account", "remove that search result", French suppression, Spanish eliminación, Japanese 削除). Canonical statuses are in `sample_output_analysis.md`. There is no `NOT_APPLICABLE` sample.

### 2.3 `sample_output.csv`

32 rows, ids aligned with the sample requests. `deletion_status`: `INCOMPLETE` 22, `COMPLETE` 10, `NOT_APPLICABLE` 0. `steps_json` is compact JSON. Structural findings are in `sample_output_analysis.md`.

### 2.4 `user_identities.csv`

Columns: `user_id`, `name`, `email`, `phone`, `email_hash`, `updated_at`. 850 rows, no empty cells.

- `user_id`, `email`, `phone`, and `email_hash` are each unique.
- `name` has three collisions: Mateo Ríos (`user_02`, `user_262`), Thandiwe Ndlovu (`user_04`, `user_413`), Gabriel Costa (`user_08`, `user_143`). Name equality is not an identity key.
- `email_hash` is 64 hex characters and equals SHA-256 of the stored email string for every row.
- `updated_at` ranges from 2023-06-22 to 2026-08-30.
- For all 518 production cases, the resolved subject's `updated_at` is at or before `audit_at`. No production case needs the current snapshot rolled forward past the audit. Historical emails are still required, because 100 requests use an address that was already replaced by `audit_at`.

Phones are human-formatted international numbers (`+971 50 482 7316`, `+1 (202) 555-0103`). Matching must normalize punctuation.

### 2.5 `user_audit_log.csv`

Columns: `audit_id`, `user_id`, `event_time`, `field_name`, `old_value`, `new_value`. 306 unique audit ids, 196 distinct users. `field_name`: `email` 107, `email_hash` 107, `phone` 92. No empty old or new values.

Email changes and hash changes share timestamps:  paired email-plus-hash events are the norm, and a hash change was not observed without the email change at the same time in the pairing check. 105 users have an email change. The largest alias set is 3 distinct emails. 92 users have a phone change. Event times run from 2024-12-14 to 2026-06-03. No audit event falls after the `audit_at` of a production case for that user.

`audit_id` is a legal `evidence_id` under the contract. The public sample never cites one. The log is still required to build the alias set.

### 2.6 `system_activity.csv`

Columns: `activity_id`, `event_time`, `event_type`, `source_system`, `target_system`, `resource_id`, `reported_result`, `details`. 4011 unique ids and 4011 unique timestamps, from 2026-01-04 to 2026-10-01. No empty cells. 3948 distinct resource ids.

`event_type` counts:

| event_type | rows |
| --- | ---: |
| DELETE_RECORD | 890 |
| UPDATE_RECORD | 672 |
| SYNC_RECORD | 447 |
| INDEX_RECORD | 400 |
| SEND_EMAIL | 368 |
| REFRESH_CACHE | 284 |
| RETAIN_RECORD | 206 |
| ANONYMIZE_RECORD | 204 |
| REDACT_RECORD | 173 |
| CREATE_EXPORT | 155 |
| CHECK_DATA_FLOW | 89 |
| DISABLE_DATA_FLOW | 36 |
| BLOCK_RESTORE | 36 |
| CHECK_RESTORE_ACCESS | 28 |
| LINK_RESOURCE_IDENTITY | 12 |
| CLASSIFY_REQUEST | 10 |
| RESTORE_BACKUP | 1 |

`reported_result`: `SUCCESS` 2914, `FAILED` 721, `PARTIAL` 376. Failures concentrate on `DELETE_RECORD` (368), `REDACT_RECORD` (117), and `ANONYMIZE_RECORD` (64). `BLOCK_RESTORE`, `DISABLE_DATA_FLOW`, `CHECK_DATA_FLOW`, and `CHECK_RESTORE_ACCESS` are recorded only as `SUCCESS` in this file. That does not make them true.

`source_system` (11 values): `deletion_worker` 1466, `account_service` 1100, `profile_service` 440, `notification_service` 368, `support_platform` 232, `security_service` 196, `export_service` 155, `integration_service` 31, `data_catalog` 12, `privacy_intake` 10, `backup_service` 1.

`target_system` (19 values): `account_service` 980, `search_service` 954, `analytics_platform` 566, `email_delivery_service` 368, `cache_service` 284, `archive_service` 196, `support_platform` 193, `object_store` 155, `integration_service` 126, `backup_service` 65, `account_replication_cluster` 55, `export_service` 34, `identity_service` 11, `legal_service` 10, `privacy_case_management` 10, plus one each of `account_failover_replica`, `object_storage`, `marketing_platform`, `security_service`.

Resource-id prefixes include `account_`, `search_`, `analytics_`, `support_`, `email_delivery_`, `cache_`, `audit_record_`, `export_`, `data_flow_`, `backup_`, `tombstone_`, `legal_hold_`, `object_`, and `marketing_`. Digit length is usually 4 (3607), sometimes 3 (402), rarely 2 (2). Ids are not a single zero-padded width.

Detail text collapses to 28 templates. The important ones:

- Deletion worker submitted a profile, or received a final result from a named system, or reported the operation completed, or stopped on an error, or completed internal work without confirming state.
- "Policy action completed for `<resource>`."
- "Connector status check confirmed that data flow `<resource>` remains enabled."
- "Active connector repopulated downstream resource `<resource>`."
- "Restore-access check confirmed that archive `<resource>` can still be restored."
- "Restore job repopulated downstream resource `<resource>`." One row: `activity_3387`, backup `backup_9287` restored `search_4882`.
- "Privacy intake classified request for `<account>` as non-deletion; no destructive action was authorized." Ten rows.
- "Data catalog linked `<resource>` to `<email>` and `<user_id>`." Twelve `LINK_RESOURCE_IDENTITY` rows. One of them states that `object_19` belongs only to one subject. These rows are the explicit identity joins and the sole-subject attachment fact. They are still claims if a later snapshot disagrees, but they are the best structured link when evidence text also contains the same email.

`deletion_worker` details often name a resource and no email. The email join has to come from evidence, from `LINK_RESOURCE_IDENTITY`, or from another activity row about the same resource. See the `account_001` gap in `sample_output_analysis.md`.

Systems that appear in activity and in the rules, but not in the 32 sample step lists: `cache_service`, `email_delivery_service`, `marketing_platform`, `legal_service`, `archive_service`, `object_store`. The engine has to handle them. The sample is not a closed system list.

### 2.7 `deletion_rules.csv`

Fifteen rules, transcribed in `challenge_contract.md`. Categories cover profiles, secondary identifiers, search, cache, support messages, support attachments, analytics, telemetry, exports, marketing, email delivery logs, security audit logs, legal holds, backup archives, and account tombstones. Actions are only `DELETE`, `REDACT`, `ANONYMIZE`, and `RETAIN`.

### 2.8 `evidence_files.csv`

Columns: `file_id`, `file_path`, `origin`, `captured_at`. 94 unique ids, `evidence_01` through `evidence_94`, paths unique, capture times almost unique (93 distinct). Range: 2026-01-29 to 2026-10-01. Paths are relative to `dataset/` (`evidence/...`).

`origin` is the producing system or export job (30 values), not the case id. High-volume origins: `central_observability_export` 12, `records_assurance_snapshot_bundle` 12, `service_resource_export` 11, `customer_data_inventory_capture` 11, `service_readback_logs` 11.

## 3. Evidence inventory

| Kind | Files | Bytes | Parser |
| --- | ---: | ---: | --- |
| `.log` | 26 | 516,200 | Several text dialects, all line-oriented |
| `.json` | 28 | 331,815 | Four JSON shapes |
| `.sql` | 24 | 334,058 | SQLite `executescript`, read-only |
| `.png` | 11 | 1,499,214 | Screenshot OCR or a vision model. No structured sidecar |
| `.pdf` | 4 | 262,447 | Text extraction works on all four |
| `.txt` | 1 | 4,534 | Line-oriented handover records |

Total evidence payload is about 2.9 MB. A full parse is cheap. The screenshots are the only format that cannot be read as text.

### 3.1 SQL

Every file starts with a comment naming the capture time and topology, then a transaction of `CREATE TABLE` and `INSERT`. Seven table layouts:

1. **Inventory** (11 files, `customer_data_inventory_*.sql`). Tables: `customer_profiles`, `customer_search_documents`, `customer_analytics_profiles`, `customer_exports`, `support_records`, `security_audit_records`, `backup_restore_entries`, `connector_subscriptions`, `snapshot_scope`. Row counts per table are small (often 0–7). `snapshot_scope` records which origin systems the capture included and the capture time. These are partial extracts. A missing person is not proof of absence. A present row is proof of presence at `updated_at`.
2. **Read replica** (5 files). `customer_data_primary` and `customer_data_read_replica`, each `resource_id`, `origin_system`, `collection_name`, `record_json`, `updated_at`.
3. **Regional replicas** (3 files). Primary plus `customer_data_replica_ap_south` and `customer_data_replica_eu_west`.
4. **Reporting replica** (2 files). Primary plus `customer_data_reporting_replica`.
5. **Data failover** (1 file, `evidence` path `customer_data_failover_replica_20260920.sql`). Primary plus `customer_data_failover_replica`, same record-json shape.
6. **Account failover** (1 file, cited as `evidence_54`). Wide profile columns on `customer_profiles_primary` and `customer_profiles_failover_replica`: `resource_id`, `user_id`, `full_name`, `email`, `phone`, `account_status`, `updated_at`.
7. **Search primary** (1 file, `evidence_57`). `search_documents_primary` only.

Replica comparison, primary versus each replica table:

| Snapshot | Extra rows only on replica | Field conflicts on shared keys |
| --- | ---: | ---: |
| read replica 2026-09-21 | 1 | 0 |
| read replica 2026-08-27 | 1 | 0 |
| read replica 2026-08-02 | 1 | 0 |
| read replica 2026-07-08 | 1 | 0 |
| read replica 2026-06-13 | 2 | 0 |
| regional 2026-05-19 ap-south | 1 | 0 |
| regional 2026-05-19 eu-west | 0 | 0 |
| regional 2026-04-24 ap-south | 0 | 0 |
| regional 2026-04-24 eu-west | 2 | 0 |
| regional 2026-03-30 ap-south | 1 | 0 |
| regional 2026-03-30 eu-west | 0 | 0 |
| reporting 2026-03-05 | 1 | 0 |
| reporting 2026-02-08 | 1 | 0 |
| data failover 2026-09-20 | 0 | 0 |
| account failover 2026-09-02 | 1 | 0 |

The account-failover extra row is `account_005` / `user_05`, status `ACTIVE`, present on the failover table and absent from the primary table in that file. That is the public illustration of replication drift. No shared key had different column values. Drift here means a replica still holds a row the primary no longer has.

Inventory and replica files also contain other people's rows (decoys). `evidence_54` includes profiles whose names resemble sample subjects but are different people (`Mateo Rios Gil`, `Priya Ramanathan`). Match on email, phone, hash, or `user_id`, not on a similar name.

Account status values observed in inventory samples include `ACTIVE` and `DELETION_PENDING`. `DELETION_PENDING` is not absence. Analytics rows with email, phone, and hash all null are the anonymized shape. Support rows sometimes keep only `customer_reference` and drop requester name, email, and phone. Backup `restore_allowed` is 0 or 1. Connector `enabled` is 0 or 1. Security rows carry `subject_reference`, `event_code`, and `retention_until` (dates in 2031–2034 on the rows sampled, so they are inside a retention window for every 2026 audit).

### 3.2 JSON

Four shapes.

**Snapshot bundles** (`customer_data_snapshot_bundle_*.json`, 12 files). Top level: `exported_at`, `source` `records_assurance_service`, `snapshots[]`. Each snapshot has `captured_at`, `data_store`, `collection`, `records`. Collections observed across bundles: `customer_profiles` 25, `customer_search_documents` 18, `support_conversations` 11, `customer_analytics_reports` 11, `connector_configurations` 11, `security_audit_events` 12, `backup_catalog` 9, `ticket_attachments` 7, `customer_export_jobs` 6, `operational_record_history` 3, `retained_order_records` 2, `deleted_customer_references` 1. Data stores include `account_service`, `search_service`, `analytics_platform`, `backup_service`, `export_service`, `integration_service`, `security_service`, `support_platform`, `support_storage_service`, `legal_service`, `identity_service`, `privacy_treatment_service`, `backup_restore_service`.

`evidence_51` (`customer_data_snapshot_bundle_20260915.json`) is the tombstone example. `account_service` / `customer_profiles` is an empty record list. `identity_service` / `deleted_customer_references` holds `tombstone_440` for `user_541` with name, email, phone, and email hash all null and `account_status` `DELETED`, and `tombstone_9178` for `user_542` with those direct identifiers still populated. `security_service` holds the two audit records cited by `case_31` and `case_32`. Empty profile list in this bundle is scoped to the export; it is evidence about the subjects included in the file, not about every user in the company.

**Service resource exports** (11 files, `service_resource_export_*.json`). Top level: `exported_at`, `region` `global`, `source` `records_assurance_gateway`, `service_exports`. `evidence_92`, which the sample cites 36 times, contains:

- `account_service.profile_lookups`: `resource_id`, `status_code` (200 or 404), `profile` object or null, `observed_at`. A 404 with `profile: null` is an explicit absence lookup.
- `analytics_platform.profiles`: `resource_id`, `email`, `phone`, `email_hash`, `customer_reference`, `audience_cohort`, `observed_at`. Null identifiers with a remaining cohort are the anonymized shape. A populated email is still attributable.
- `backup_service.restore_entries`: `resource_id`, `customer_reference` or `customer_email`, `archive_key`, `restore_allowed`, `observed_at`.
- `export_service.exports`: `resource_id`, `owner_email`, `owner_phone`, `object_key`, `customer_reference`, `observed_at`.
- `integration_service.connectors`: `resource_id`, `connector_name`, `enabled`, `last_delivery_status`, `customer_email` or `customer_reference`, `observed_at`.
- `search_service.index_queries`, `security_service.audit_records`, `support_platform.tickets` are present in the same file. Not every export contains every service. Some monthly exports omit `backup_service` or `export_service`.

**Catalog rows** (`connector_configurations`, `customer_export_manifest`, `security_audit_ledger`). Each record is `recorded_at`, `system`, `resource_id`, `record_type`, `result`, `subject_reference`. Record types seen: `USER_PROFILE`, `ANALYTICS_PROFILE`, `DATA_FLOW`, `SEARCH_INDEX_ENTRY`, `SECURITY_AUDIT_LOG`, `SUPPORT_MESSAGE`, `BACKUP_ARCHIVE`, `USER_EXPORT`, `LEGAL_HOLD_RECORD`. Results seen: `NOT_FOUND`, `FOUND`, `IDENTIFIABLE`, `ANONYMIZED`, `ACTIVE`, `BLOCKED`, `DISABLED`, `REDACTED`.

**Single-collection reports.** `evidence_56` analytics report: `resource_id`, `user_id`, `email`, `phone`, `email_hash`, metrics. The cited `analytics_901` row has all identifiers null. `evidence_59` export jobs: `resource_id`, `owner_email`, `download_available` true for `export_001`.

### 3.3 Text handover

`evidence_03`, `customer_account_handover_20261001.txt`, capture equal to several `audit_at` values of `2026-10-01T12:00:00Z`. Lines are:

`timestamp | system_id | resource_id | RECORD_TYPE | RESULT | subject`

Types in the file: `USER_PROFILE`, `ANALYTICS_PROFILE`, `BACKUP_ARCHIVE`, `USER_EXPORT`, `DATA_FLOW`, `SEARCH_INDEX_ENTRY`, `SECURITY_AUDIT_LOG`, `SUPPORT_MESSAGE`, `SUPPORT_ATTACHMENT`. Results: `NOT_FOUND`, `FOUND`, `IDENTIFIABLE`, `ANONYMIZED`, `ACTIVE`, `BLOCKED`, `DISABLED`, `REDACTED`. This is the clearest explicit state vocabulary in the dataset. `case_11` is a direct reading of the lines for `novak.tomasz@icloud.com` and `user_32`: search `FOUND`, analytics `IDENTIFIABLE`, support message `IDENTIFIABLE`, data flow `ACTIVE`, account `NOT_FOUND`, security audit `FOUND`.

### 3.4 Logs

At least eight dialects, all UTF-8 text:

- key=value (`service_events_*.log`, `support_replica.log`, `resource_lookup_trace_*.log`)
- JSON lines (`structured_service_events_*.log`)
- RFC5424 syslog (`syslog_archive_*.log`)
- bracketed traces (`application_trace_*.log`)
- pipe-delimited (`operations_stream_*.log`)
- cloud `requestId` / `message` (`cloud_runtime_export_*.log`)
- diagnostic `record_lookup` lines (`search_index_diagnostic`, `notification_delivery`)

Many lines are transport noise: `export_started`, `connection_acquired`, `cache_lookup result=miss`, `consumer_lag`, thumbnail failures. Those cache lookups are the service's own lookup cache, not a customer `CACHE_ENTRY`, unless the line is actually about a `cache_` resource.

State-bearing events include `profile_lookup_completed` (`rows`, `http_status`), `index_query_completed` (`result=hit`), `contact_lookup_completed`, `connector_heartbeat` (`enabled=true`), `restore_candidate_evaluated` (`eligible`, `deletion_block`), `deletion_marker_check` (`marker_found`), and diagnostic lines with `record_type` plus `FOUND` / `NOT_FOUND` / `IDENTIFIABLE`.

`evidence_01` shows the claim-versus-evidence problem in one file. `account_5762` for `haruka.s1838@zoho.com` returns `rows=0` and HTTP 404 on 2026-09-15. The admin screenshot `evidence_04`, captured 2026-09-26, shows that same account present. The later screenshot is the newer observation. A 404 is absence only if it is the latest eligible observation for that resource. Production `case_34` uses this email and an `audit_at` of 2026-09-27, after the screenshot. This is why images cannot be skipped.

`support_replica.log` (`evidence_61`) shows `support_002` with `rows=1` and `marker_found=false` for the historical address `nadia.ionescu@yahoo.com`. The deletion activity for that resource is `SUCCESS`. The log is the proof the record remains. A similar address, `nadia.popescu@yahoo.com` / `support_5914`, is a different person and is not in the `case_10` steps.

### 3.5 PDFs

Text extraction succeeded on all four. They are business documents, not verdict stamps.

- `evidence_58`, delivery-address correction, cited by sample `case_07`. It names `support_001`, the subject's name, email, and phone, and says the uploader was the customer. Rule `rule_06` deletes an attachment that belongs only to the subject. The canonical step is `REPORT_REMAINING_RECORD` / `DELETE_RECORD`, not redaction.
- `evidence_55`, compliance journal extract. It names `audit_record_003`, `user_03`, "Account closure recorded", and "retain until 25 Aug 2027". That is a security-audit retention fact.
- `legal_retention_register_20260529.pdf`. Disputed-order and tax rows for several `user_id` values, with retain-until dates in 2033. It does not use the `legal_hold_` resource ids. It may support `LEGAL_HOLD_RECORD` or it may be a finance record that is out of scope. Do not delete those rows on a guess. Confirm during implementation whether any sample or structured `LEGAL_HOLD_RECORD` points at the same orders.
- `account_history_report_20260718.pdf`. A customer statement for `user_18` / Ingrid Dahl, statement id `NST-2026-0718-1842`. `activity_4009` links export `export_1842` to that same statement id. The PDF is a copy of an export, which `rule_09` says to delete.

### 3.6 Images

Eleven PNGs, about 121–156 KB each, all Northstar Shop product screenshots. Manifest:

| file_id | File | Origin | Captured |
| --- | --- | --- | --- |
| evidence_04 | account_admin_console_20260926.png | account_admin_portal | 2026-09-26T11:00:00Z |
| evidence_09 | search_index_inspector_20260901.png | search_index_admin | 2026-09-01T06:00:00Z |
| evidence_14 | connector_management_console_20260807.png | integration_admin | 2026-08-07T08:00:00Z |
| evidence_19 | analytics_profile_view_20260713.png | analytics_platform | 2026-07-13T10:00:00Z |
| evidence_23 | customer_export_console_20260618.png | export_service | 2026-06-18T12:00:00Z |
| evidence_28 | support_ticket_console_20260524.png | support_platform | 2026-05-24T07:00:00Z |
| evidence_32 | backup_restore_console_20260429.png | backup_service | 2026-04-29T09:00:00Z |
| evidence_37 | security_audit_explorer_20260905.png | security_service | 2026-09-05T07:00:00Z |
| evidence_42 | deleted_account_reference_20260310.png | identity_service | 2026-03-10T06:00:00Z |
| evidence_46 | object_storage_browser_20260213.png | object_storage | 2026-02-13T08:00:00Z |
| evidence_60 | marketing_profile_console.png | marketing_platform | 2026-09-16T07:20:00Z |

`evidence_04` shows `user_11`, `account_5762`, email `haruka.s1838@zoho.com`, phone, and a live customer page as of 24 Sep 2026. That positive presence is not duplicated by the 15 Sep log, which recorded a 404. `evidence_42` shows a retained reference for `user_17` with linked order, support, and finance records, and no name, email, or phone on the screen that was read. Sample steps do not cite any PNG. Production cases can still depend on them. Nine screenshots were not visually read in this phase; the implementation must parse all eleven.

## 4. How the files join

```text
deletion_requests.email
    -> user_identities.email            (case-insensitive)
    -> user_audit_log old/new email     (case-insensitive)
    -> user_id, current and historical phone, current and historical email_hash

user_id / email / phone / email_hash
    -> evidence contents                (not the manifest)
    -> system_activity.details          (when the text contains an identifier)
    -> LINK_RESOURCE_IDENTITY rows      (resource_id + email + user_id)

resource_id
    -> later or earlier observations of the same resource
    -> activity rows about that resource
```

`evidence_files.csv` does not identify the user. A file becomes relevant when its contents contain an alias or a resource already tied to an alias.

Latest eligible observation wins, separately per replica. File `captured_at` and the inner `observed_at` / event time both have to be `<= audit_at`. An older `FOUND` does not survive a newer `NOT_FOUND` on the same store. A newer replica row does survive an older primary deletion.

Partial extracts (inventory SQL, small snapshot bundles, logs that never queried the subject) do not prove absence. Explicit negative lookups do: HTTP 404, `rows=0`, `NOT_FOUND` on a named resource, `profile: null` on a named lookup. The public sample also treats omission of `account_001` from `evidence_54` as absence after the resource id was established elsewhere. That file is tiny and full of other people, so "omission equals absence" is only safe when the snapshot is a lookup of that subject or the canonical sample shows that reading. Applying it to every partial file would mark unrelated users deleted. The implementation plan treats this as a tested rule, not as a global default.

## 5. Ambiguities found in the data

1. **Lexicographic versus numeric `case_id` sort.** Production ids are not zero-padded. See `challenge_contract.md` §9.
2. **`resource_id` ascending** has the same string-versus-number question. No public pair settles it.
3. **Ten non-deletion activity claims versus six explicit request texts.** The activity rows are not keyed by `case_id`. Classify the text. Use the activity only as a cross-check.
4. **`account_001` has no identifier in evidence or in the activity detail.** The only occurrences are `activity_3342` (a `SUCCESS` delete claim 17 seconds before `case_01`'s unique `reported_at`) and the canonical sample row, which cites `evidence_54` for absence. Later cases do not follow `user_N` = `account_N` (`user_43` is `account_7566`). A padding shortcut is unsafe. Recovering `account_001` requires a tested link from the case to that activity, then the snapshot proves the state. Do not hardcode the id.
5. **Shared `reported_at`.** Many production and sample cases share a timestamp such as `2026-09-02T12:00:00Z`, and their activity rows are interleaved. A time window alone cannot assign resources to a case.
6. **Analytics resources are not one policy action.** Attributable analytics profiles are anonymized. `analytics_9914` in `evidence_01` is a `contact_lookup_completed` event with `email_opt_in=true` and a correlation hash, and the canonical action is `DELETE_RECORD`. Category comes from record type and fields, not from the `analytics_` prefix.
7. **Legal-hold PDF versus `legal_hold_` resources.** Both exist. They were not fully joined in this phase.
8. **Evaluation report path.** `code/evaluation/` versus a top-level `evaluation/` inside the zip. See `challenge_contract.md`.
9. **Inner snapshot time versus manifest time.** Bundles contain older inner `captured_at` values. The state time is the inner observation, provided the file itself was captured at or before `audit_at`.
