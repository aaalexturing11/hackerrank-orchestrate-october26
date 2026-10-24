# Usage report

This report covers the final full-dataset run that wrote repository-root `output.csv`.

The runtime does not call an external language model or a vision model. Screenshot fields are read from `code/ingestion/image_facts.py`. Identity, policy, and step planning are ordinary Python.

## Final dataset run

Command: `python code/main.py`

The command was executed twice. Both outputs hashed to the same SHA-256 value. Counts below are for one run; the second run matched.

| Item | Value |
| --- | --- |
| Provider | none |
| Model name | none |
| Model calls | 0 |
| Input tokens | 0 |
| Output tokens | 0 |
| Total tokens | 0 |
| Average tokens per request | 0 |
| Estimated total cost | 0 |
| Average estimated cost per request | 0 |
| Requests | 518 |

Per-model totals are the same as the overall totals, because no model was called.

| Provider | Model | Calls | Input tokens | Output tokens | Estimated cost |
| --- | --- | --- | --- | --- | --- |
| none | none | 0 | 0 | 0 | 0 |
| Overall |  | 0 | 0 | 0 | 0 |

## Development assistance

Cursor, with the model Grok 4.7, was used to write and review this solution. Those editor sessions are not part of `python code/main.py`. This program does not record their tokens, and this report does not invent a token or cost figure for them.
