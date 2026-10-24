# Challenge Contract

Source of truth for the October 2026 HackerRank Orchestrate challenge, **Ghost Data Still Exists**. This document extracts the rules that govern the deletion-audit agent. Each rule cites the section it comes from.

Confirmed identity of this checkout:

- Repository title in `README.md`: "HackerRank Orchestrate - October 2026".
- Problem title in `problem_statement.md`: "Ghost Data Still Exists".
- `AGENTS.md` describes the October 2026 challenge and says the end time is not configured.
- No September challenge statement, deadline, or dataset is present.
- Participant-facing data lives only under `dataset/`. There is no `generator/` tree and no organizer answer file in this checkout.

Two packaging paths disagree. `AGENTS.md` §6.8 says `code.zip` must include `evaluation/evaluation_report.md` and `evaluation/usage_report.md`. `README.md` ("Evaluation") says to place those files at `code/evaluation/` so the documented zip of `README.md` plus `code/` includes them. Implementation should write the reports to `code/evaluation/` and mention that path in the submitted README. The logical content required by both documents is the same.

## 1. What the agent must decide

For every row in `dataset/deletion_requests.csv`, the agent determines whether deletion was actually requested and, if it was, whether that deletion is complete at `audit_at`.

Explicit, `problem_statement.md` "What You Need to Build" and `AGENTS.md` §6.5:

- Status is `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`.
- `NOT_APPLICABLE` applies when the person did not request deletion. Access, correction, export, portability, marketing opt-out, and other non-deletion actions stay in this class even if the rest of the row looks like a deletion case (`AGENTS.md` §6.5).
- A deletion is `COMPLETE` only when all of the following hold (`problem_statement.md` "What You Need to Build"; `AGENTS.md` §6.5):
  - every relevant copy has received the treatment required by `deletion_rules.csv`;
  - no active sync, import, or restore path can recreate the data;
  - retained records contain only the identifiers the rules permit;
  - records that must be retained are still available.
- Otherwise an authorized deletion is `INCOMPLETE`.

`reported_status` is not the decision. It is a workflow claim and may be `COMPLETE`, `PARTIALLY_COMPLETE`, or `NOT_STARTED` (`problem_statement.md` "Input"; `AGENTS.md` §6.2). The 32 public samples confirm the claim is often wrong: 11 rows reported `COMPLETE` are canonically `INCOMPLETE`, and 3 rows reported `NOT_STARTED` are canonically `COMPLETE`. See `sample_output_analysis.md`.

## 2. What counts as a deletion request

Explicit, `problem_statement.md` "Rules" and `AGENTS.md` §6.5:

- Decide from `request_text`, which may be in more than one language.
- A request for access, correction, export, or another non-deletion action is `NOT_APPLICABLE`.
- `NOT_APPLICABLE` uses `steps_json` `[]`. No findings, remediation, or verification are authorized (`problem_statement.md` "Required Output").

The public sample does not contain a `NOT_APPLICABLE` row. The problem statement's `case_000` line is an illustration, not a row in this dataset. Production requests do include explicit non-deletion text (correction, portable export, invoice copy, login help). Those rows are profiled in `dataset_analysis.md`. `CLASSIFY_REQUEST` activity rows that say "non-deletion" are claims, not the decision.

## 3. Identity resolution

Explicit, `problem_statement.md` "Rules" and `AGENTS.md` §6.5–§6.6:

- Resolve current and historical identifiers.
- The request `email` may be a current address or a historical one (`AGENTS.md` §6.2).
- Match through current identifiers, historical identifiers, hashes, resource IDs, system IDs, and timestamps (`AGENTS.md` §6.6).
- Do not infer case membership from `evidence_files.csv` alone. The manifest has no user or case column.

Data facts that constrain the resolver, from files actually read:

- `user_identities.csv` is the current snapshot: `user_id`, `name`, `email`, `phone`, `email_hash`, `updated_at`.
- `user_audit_log.csv` records changes to `email`, `email_hash`, and `phone` only. Names are not versioned there.
- Every current `email_hash` equals SHA-256 of the email string exactly as stored (850 of 850). Case differs across historical values, so email matching must be case-insensitive, while a hash must be compared to the hash that was stored, not recomputed from a differently cased request string.
- `user_id` is the stable subject reference that an account tombstone may keep (`problem_statement.md` introduction; `AGENTS.md` §6.5).

Tombstone rule, explicit: preserve the stable internal `user_id` and remove name, email, phone, email hash, and any other direct identifiers required by the applicable `REDACT` rule (`AGENTS.md` §6.5; `deletion_rules.csv` `rule_15`).

## 4. Time

Explicit, `problem_statement.md` "Rules" and `AGENTS.md` §6.2, §6.6:

- Reconstruct state at `audit_at`.
- Use only information available at or before `audit_at`.
- Evidence captured later must not change the answer.
- `requested_at` is when the request was submitted. `reported_at` is when the workflow made its claim. Neither replaces `audit_at`.

Timestamp form in every CSV column checked: `YYYY-MM-DDTHH:MM:SSZ` (UTC, second precision, `Z` suffix). Compare as UTC instants. A capture time equal to `audit_at` is eligible; the public sample cites `evidence_03` at `2026-10-01T12:00:00Z` for cases whose `audit_at` is that same instant.

Inner observation times inside a file can be earlier than the file's `captured_at`. Both gates apply: the file's manifest `captured_at` must be `<= audit_at`, and the inner event or snapshot time used as the observation should also be `<= audit_at`.

## 5. Claims versus evidence

Explicit, `problem_statement.md` "Rules" and `AGENTS.md` §6.6:

- Activity logs, workflow statuses, and operation results are claims.
- They become proof only when the available evidence establishes the resulting state.
- A finding must cite the participant-visible `file_id`, `activity_id`, or `audit_id` that proves it.
- A `COMPLETE` verification step must cite the evidence that proves the compliant state.
- Remediation steps, and verification steps that describe future checks on an `INCOMPLETE` case, use `evidence_id` `""`.

`system_activity.reported_result` is `SUCCESS`, `FAILED`, or `PARTIAL`. The sample shows all three can be false relative to later evidence. Examples are recorded in `sample_output_analysis.md`. Do not treat `SUCCESS` as deletion, and do not treat `FAILED` as proof the record remains.

## 6. Policy

The policy file is `dataset/deletion_rules.csv` (15 rules). `problem_statement.md` "Rules" and `AGENTS.md` §6.5 require applying it to every relevant record, including tombstones, active data flows, and restore risks. Do not delete a record the policy says to retain, redact, anonymize, or keep as a tombstone.

| rule_id | data_category | condition | required_action |
| --- | --- | --- | --- |
| rule_01 | USER_PROFILE | Always | DELETE |
| rule_02 | SECONDARY_IDENTIFIER | Always | DELETE |
| rule_03 | SEARCH_INDEX_ENTRY | Always | DELETE |
| rule_04 | CACHE_ENTRY | Always | DELETE |
| rule_05 | SUPPORT_MESSAGE | Conversation contains shared customer, agent, or order context that must be retained | REDACT |
| rule_06 | SUPPORT_ATTACHMENT | Attachment belongs only to the deletion subject | DELETE |
| rule_07 | ANALYTICS_PROFILE | Record is still attributable to a user | ANONYMIZE |
| rule_08 | PRODUCT_TELEMETRY | Record is still attributable to a user | ANONYMIZE |
| rule_09 | USER_EXPORT | Always | DELETE |
| rule_10 | MARKETING_PROFILE | Always | DELETE |
| rule_11 | EMAIL_DELIVERY_LOG | Log contains a user email address | REDACT |
| rule_12 | SECURITY_AUDIT_LOG | Record is within the supplied retention period | RETAIN |
| rule_13 | LEGAL_HOLD_RECORD | A supplied legal hold is active | RETAIN |
| rule_14 | BACKUP_ARCHIVE | Restore access can be blocked | RETAIN |
| rule_15 | ACCOUNT_TOMBSTONE | Account is deleted and only a stable internal user_id is needed to preserve references to retained records | REDACT |

Actions used by the rules are `DELETE`, `REDACT`, `ANONYMIZE`, and `RETAIN`. There is no fifth action.

How those actions become steps is specified in §8. The mapping from a compliant retained record to `VERIFY_RECORD_PRESENT`, and from a blocked backup to `VERIFY_RESTORE_BLOCKED`, is fixed by the allowed-operations table plus the sample. It is not a separate column in `deletion_rules.csv`.

Conditions are data-dependent. "Always" does not need a predicate. The other conditions must be read from the record: shared support context, sole-subject attachment, remaining attribution, email still present in a delivery log, retention period versus `audit_at`, legal hold still active, and whether restore can be blocked.

## 7. Replicas, recreation, and retention

Explicit:

- SQL captures may be a primary database, a regional replica, a reporting replica, or a failover replica (`README.md` "Dataset"; `AGENTS.md` §6.1).
- Compare tables and snapshot time when investigating replication drift (`AGENTS.md` §6.6).
- An active sync, import, or restore path that can recreate prohibited data blocks `COMPLETE` (`problem_statement.md` "What You Need to Build").
- Backups are not automatically deleted. `rule_14` says retain a backup archive when restore access can be blocked, and the finding operation for an unsafe backup is `REPORT_RESTORE_RISK` (`problem_statement.md` "Allowed Operations").

Measured on the SQL files (details in `dataset_analysis.md`): drift in this dataset is extra rows on a replica, not conflicting column values on a shared key. A row that exists only on a failover, read, regional, or reporting replica is still present. Primary absence does not make the deletion complete.

A completed sync that already left a copy behind is a remaining record. An enabled connector that can copy again is an active data flow. Those are different operations. The sample uses both, on different resources.

## 8. Steps, operations, and states

Explicit schema, `problem_statement.md` "Required Output". Every object has exactly these fields:

| Field | Type | Allowed values |
| --- | --- | --- |
| `step_no` | number | Integers starting at 1, consecutive, no gaps |
| `phase` | string | `FINDING`, `REMEDIATION`, `VERIFICATION` |
| `system_id` | string | System that holds the resource. Not a closed enum in the spec. Values must come from the evidence. |
| `resource_id` | string | Resource identifier from the evidence. Do not invent ids. |
| `operation` | string | One operation from the table below |
| `state` | string | The state paired with that operation |
| `evidence_id` | string | `file_id`, `activity_id`, `audit_id`, or `""` |

No optional fields appear in the schema. The sample objects contain exactly this set and no others.

Allowed pairs (`problem_statement.md` "Allowed Operations"; `AGENTS.md` §6.4). Do not invent phases, operations, or states.

| Phase | Operation | State | Meaning |
| --- | --- | --- | --- |
| FINDING | `REPORT_REMAINING_RECORD` | `PRESENT` | A record that should have been deleted still exists. |
| FINDING | `REPORT_EXPOSED_PII` | `PRESENT` | The record may remain, but identifiers that should have been redacted or anonymized are still exposed. |
| FINDING | `REPORT_ACTIVE_DATA_FLOW` | `ACTIVE` | An active process can copy or recreate the user's data. |
| FINDING | `REPORT_RESTORE_RISK` | `ACTIVE` | A backup or restore path can bring deleted data back. |
| REMEDIATION | `DISABLE_DATA_FLOW` | `DISABLED` | Stop the process that can copy or recreate the data. |
| REMEDIATION | `BLOCK_RESTORE` | `BLOCKED` | Prevent the affected backup from restoring the user's data. |
| REMEDIATION | `DELETE_RECORD` | `ABSENT` | Remove the entire record. |
| REMEDIATION | `REDACT_RECORD` | `REDACTED` | Keep the record and remove the identifying fields required by policy. |
| REMEDIATION | `ANONYMIZE_RECORD` | `ANONYMIZED` | Keep the record after irreversibly unlinking it from the user. |
| VERIFICATION | `VERIFY_RECORD_ABSENT` | `ABSENT` | Confirm the record no longer exists. |
| VERIFICATION | `VERIFY_RECORD_PRESENT` | `PRESENT` | Confirm a policy-required retained record still exists. |
| VERIFICATION | `VERIFY_RECORD_REDACTED` | `REDACTED` | Confirm the required identifying fields were removed. |
| VERIFICATION | `VERIFY_RECORD_ANONYMIZED` | `ANONYMIZED` | Confirm the record can no longer be linked to the user. |
| VERIFICATION | `VERIFY_DATA_FLOW_DISABLED` | `DISABLED` | Confirm the data flow is inactive. |
| VERIFICATION | `VERIFY_RESTORE_BLOCKED` | `BLOCKED` | Confirm the affected data cannot be restored. |

Each operation has exactly one legal state. The sample has zero exceptions.

### 8.1 Which steps exist for each status

Explicit, `problem_statement.md` "Required Output" and `AGENTS.md` §6.3:

- `COMPLETE`: only `VERIFICATION` steps, each proving the state at `audit_at`, each with a non-empty `evidence_id`.
- `INCOMPLETE`: findings, the complete ordered remediation plan, and the checks that must pass afterward. Findings cite evidence. Remediation and future verification use `evidence_id` `""`.
- `NOT_APPLICABLE`: `[]`.

`AGENTS.md` §6.5 adds: for an incomplete case, report every relevant policy violation and recreation risk supported by participant-visible evidence, and verification must cover the required final state for each remediated record or process.

The sample goes further than "each remediated record". Incomplete cases also verify end states that were already true and were not remediated, such as an account already absent and a security audit log that must remain. That pattern is documented as sample-derived in `sample_output_analysis.md`. It is consistent with "checks that must pass afterward" and with the completeness requirement, and the implementation should follow it because every public incomplete answer does.

### 8.2 Order

Explicit, `problem_statement.md` "Rules" and `README.md` "Output":

1. Phase order is `FINDING`, then `REMEDIATION`, then `VERIFICATION`.
2. Within a phase, follow the operation order in the allowed-operations table.
3. Then `system_id` ascending.
4. Then `resource_id` ascending.
5. `step_no` follows that array order, starting at 1.

Array order is significant. JSON object-key order and whitespace are not (`problem_statement.md` "Required Output").

`AGENTS.md` §6.5 also says to disable data flows and block unsafe restores before changing dependent records, and to process downstream copies before their source when the dependency requires it. The first sentence is already achieved by the operation table: `DISABLE_DATA_FLOW` and `BLOCK_RESTORE` sort before `DELETE_RECORD`, `REDACT_RECORD`, and `ANONYMIZE_RECORD`. The second sentence conflicts with system-id order when two deletions are involved. Public `case_16` deletes `account_service` / `account_994` before `search_service` / `search_1007`. That is system-id order, not downstream-before-source. Implement the explicit sort from the problem statement. Lock it with a regression check on the public sample.

### 8.3 Evidence on each step

Explicit:

- Findings cite a real `file_id`, `activity_id`, or `audit_id`.
- `COMPLETE` verifications cite the evidence that proves the current compliant state.
- `INCOMPLETE` remediation and future verification use an empty string, not null and not an omitted field.
- Never cite evidence captured after `audit_at`.
- Never cite organizer-only material. This checkout has none in the participant tree.

The public sample cites only `file_id` values (`evidence_NN`). It never cites `activity_id` or `audit_id`. The contract still allows both, so the engine must be able to emit them when a file does not prove the state and an activity or audit row does.

## 9. Output file

Explicit, `problem_statement.md` "Required Output", `README.md` "Output", `AGENTS.md` §6.3 and §6.7:

- Path: `output.csv` at the repository root. `dataset/output.csv` is a blank template (header only).
- Header, exact order: `case_id,deletion_status,steps_json`.
- Exactly 518 data rows, one per `case_id` in `dataset/deletion_requests.csv`.
- Sorted by `case_id`.
- `steps_json` is a JSON array. The grader parses it as JSON.
- Runnable from the terminal, reading `dataset/`, deterministic where possible.
- Do not use organizer-only files, hardcoded golden labels, or case-family shortcuts (`AGENTS.md` §6.7).

Sort ambiguity: production ids run from `case_33` through `case_550` and are not zero-padded. Lexicographic order and numeric order differ (`case_100` is before `case_33` as strings). The spec says "sorted by `case_id`" and does not say "numerically". The public sample is `case_01`–`case_32`, which sorts the same way either way, so it cannot settle this. Default assumption for implementation: lexicographic ascending, the ordinary sort of the identifier string. Validate before submission if a grader note appears.

`resource_id` "ascending" has the same string-versus-number issue (`search_1007` versus `search_899`). No public pair distinguishes them. Use lexicographic order, the same comparison as `system_id`.

## 10. Evaluation and submission

Explicit, `problem_statement.md` "Evaluation" and "Submission"; `README.md` "Evaluation"; `AGENTS.md` §6.8–§6.9.

Scoring considers deletion status, identity resolution, discovered records and risks, cited evidence, policy decisions, and the completeness and order of `steps_json`.

`evaluation_report.md` must contain:

- case-level deletion-status accuracy;
- step-level and field-level accuracy (`README.md` also names row-level accuracy);
- sequence accuracy;
- at least three additional evaluation cases created by the participant;
- failures found and improvements made.

`usage_report.md` must summarize the final full-dataset run that produced `output.csv`:

- model providers and model names;
- model-call counts;
- input and output tokens;
- total and average tokens per request;
- estimated total and per-request cost;
- per-model and overall totals when more than one model is used.

If the run calls no external model, record zero calls and explain the deterministic method. Do not invent token counts. Do not put API keys, credentials, or the dataset inside `code.zip`.

Submission items: `code.zip`, root `output.csv`, `log.txt` as the chat transcript, and the AI interview. `agent_trace_instructions.md` separately asks for an `agent-trace.zip` of harness transcripts. That file is packaging guidance for the trace upload, not a rule about deletion decisions.

## 11. Rules that are easy to over-read

- Images and PDFs are ordinary business artifacts. Extract the facts in them. They do not contain an explicit deletion verdict (`AGENTS.md` §6.6).
- Global activity and evidence contain other people. A similar email or a similar name is not a match. Public `case_28` says a search hit with a similar email belongs to someone else, and the canonical steps omit it.
- Account tombstones are redacted, not deleted, when retained records still need `user_id`.
- Security audit logs inside the retention window are retained. Their verification operation is `VERIFY_RECORD_PRESENT`, not a redaction, unless a different rule applies to that record.
- Empty `steps_json` is only for `NOT_APPLICABLE`. A complete deletion still has one or more verification steps.
