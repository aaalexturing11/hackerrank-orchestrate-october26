# AI judge preparation

The running program is a deterministic deletion auditor. It does not send each request to a language model.

## Architecture

`python code/main.py` loads `dataset/`, parses every evidence file, and calls `DeletionAuditor` once per request. The same class scores the 32 public samples. Output is `output.csv` at the repository root with columns `case_id,deletion_status,steps_json`.

The pipeline is:

1. Classify the request text as deletion or not.
2. Resolve the email to one user, including historical emails, phones, and email hashes.
3. Collect resource ids tied to that user by identifiers, by a literal `Target resource:` activity, or by historical lineage.
4. Reconstruct resource state from observations whose package and inner time are both at or before `audit_at`.
5. Apply `dataset/deletion_rules.csv`.
6. Emit findings, remediation, and verification in the contract order.

A non-deletion request is `NOT_APPLICABLE` with `[]`. An unresolved or ambiguous identity is `INCOMPLETE` with no invented resources.

## Why deterministic reasoning

The contract is a policy over evidence, timestamps, and identifiers. The same inputs must produce the same steps. A model call would add cost, non-determinism, and a path that could memorize the 32 public answers. The sample file is not read until after prediction, and only by the scorer.

## Identity lineage

Current identity comes from `user_identities.csv`. Historical emails, phones, and hashes come from `user_audit_log.csv` at or before `audit_at`. Names are never join keys.

A resource is linked when an observation carries one of those identifiers. If the observation's inner time is at or before the audit, the link is kept even when the file was packaged later. If any observation of that resource carries a different subject's identifiers, the resource stays unassigned. `account_5684` is the public example: a 9 September snapshot names user 26, and the admissible state is the 15 September 404 in `evidence_92`.

## Audit-time state

`observed_at` is when the row says the fact happened. `captured_at` is when the file was packaged. State used for a finding, or for a verification on a `COMPLETE` case, must pass both clocks. Reported workflow success is stored as a claim and does not set presence.

If a resource has no eligible observation, an earlier event inside a later package may still describe state. That path runs only when the case is already incomplete, and the resulting verification has an empty evidence id. It cannot create a finding and it cannot mark the case complete.

## Multimodal evidence

JSON, logs, SQL snapshots, PDFs, and plain text are parsed into one observation shape. The eleven screenshots were read once during development. Their visible fields live in `code/ingestion/image_facts.py`. The runtime does not call a vision API and does not guess relationships that were not on the screen.

## Policy and remediation

Fifteen rules map categories to DELETE, REDACT, ANONYMIZE, or RETAIN. Direct identifiers are name, email, phone, and email hash. A tombstone may keep `user_id`. A security log or legal hold outside its retention period produces no step. An enabled flow is disabled before dependent edits. A backup that can be restored is retained and blocked, not deleted. Shared support messages are redacted. Sole-subject attachments are deleted.

Within a phase, steps follow the allowed-operation table, then system id, then resource id. Step numbers are assigned after that sort.

## Why a later file cannot overwrite earlier state

A package after `audit_at` is not a citation and is not the winning state when an eligible observation already exists. The rejected alternative, using only the inner timestamp, replaced the exposed `support_5281` and `support_6477` rows and dropped admissible account citations. Exact-row accuracy fell to 12/32. The retained rule keeps the earlier eligible row.

## Why some public verifications stay out

Several analytics rows and account lookups in `evidence_92` have null subject fields in every admissible source. Several account ids appear only in deletion-worker text that names no person. `account_004`, `audit_record_6645`, and `audit_record_5569` do not appear in the participant evidence at all. `account_4857` appears as an activity, not inside the cited snapshot. `account_3866` is named in a snapshot dated two days after the audit, so that name is not an audit-time fact. Choosing a neighbor, a time window, or the sample answer would assign those rows without evidence.

## Evaluation

Public scoring compares predictions with `dataset/sample_output.csv` after inference. Current result: status 32/32, exact rows 17/32, positional fields 889/1158, precision 172/172, recall 172/193, extra operations 0. Synthetic tests cover late packages, competing owners, replica conflicts, unnamed worker rows, and the fifteen rule actions. The 518-request file was generated twice with the same SHA-256 hash. Hidden production accuracy is not claimed.

## What changed from the first version

The first auditor parsed evidence and stopped before policy decisions. Later versions added category rules, image facts, explicit system names, target-resource anchors, and same-trace identifier propagation. The last accuracy change split lineage from state and allowed a historical event to fill a resource that had no eligible observation. That moved exact rows from 15/32 to 17/32 without adding an unsupported operation. This final pass confirmed the remaining 21 operations are not uniquely identified, wrote the evaluation and usage reports, and packaged `code.zip`.

## Limitations and future work

The auditor will miss a resource whose only subject key is null, and it will miss a resource that exists only in a file packaged after the audit when the case is otherwise complete, because that verification would have no admissible citation. A future evidence format that carries a workflow id on both the request and the worker event could link the seven unnamed accounts without using time proximity. Until that field exists, leaving them out is the conservative result.
