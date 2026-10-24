"""Decide whether request text authorizes deletion.

The decision is lexical and deterministic. Workflow classifications are not
an input. Case ids are not an input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

# Stems that authorize deletion when they are not inside a negation window.
_DELETION_PATTERNS = (
    r"\bdelet\w*",
    r"\berasure\b",
    r"\beras\w*",
    r"\bremov\w*\s+(?:my|the|any|that|records|this)",
    r"\bclose\s+(?:my|this|the)\s+account\b",
    r"\bsupprim\w*",
    r"\bsuppression\b",
    r"\belimin\w*",
    r"\bborr\w*",
    r"\bolvid\w*",
    r"\bexcluir\b",
    r"\bexclus\w*",
    r"\bapagar\b",
    r"削除",
    r"삭제",
    r"\bprofile is gone\b",
    r"\bcannot identify me\b",
    r"\balready been removed\b",
    r"\blösch\w*",
    r"\blosc\w*",
)

_NEGATION = re.compile(
    r"(?:do not|don't|dont|never|must not|ne pas|n'effacez pas|no debe|non\s+)\W{0,40}$",
    re.IGNORECASE,
)

_PRESERVE = (
    "keep the account",
    "keep my account",
    "leave the account",
    "leave my profile",
    "leave my account",
    "still use it",
    "continue using the service",
    "do not close",
    "don't close",
    "do not delete",
    "don't delete",
    "dont delete",
    "must not be deleted",
    "must not delete",
    "without deleting",
)

_NON_DELETION_TASKS = (
    "portable format",
    "download my",
    "copy of my",
    "copy of the information",
    "copy of last",
    "invoice",
    "invoices",
    "resetting the login",
    "reset the login",
    "reset my password",
    "password reset",
    "can't access my profile",
    "cannot access my profile",
    "change the email",
    "change my email",
    "replace it with the new one",
    "out of date",
    "correct my",
    "correct the",
    "update my",
    "update the",
    "change my phone",
    "change my address",
    "change my name",
    "export my",
    "export the",
    "opt out",
    "opt-out",
    "unsubscribe",
    "marketing list",
    "service messages",
)


class RequestIntent(str, Enum):
    DELETION = "deletion"
    NON_DELETION = "non_deletion"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class Classification:
    intent: RequestIntent
    deletion_terms: tuple[str, ...]
    negated_terms: tuple[str, ...]
    preservation_terms: tuple[str, ...]


def _find_terms(text: str) -> tuple[list[tuple[int, int, str]], list[tuple[int, int, str]]]:
    deletion: list[tuple[int, int, str]] = []
    negated: list[tuple[int, int, str]] = []
    for pattern in _DELETION_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            window = text[max(0, match.start() - 40) : match.start()]
            if _NEGATION.search(window):
                negated.append((match.start(), match.end(), match.group(0)))
            else:
                deletion.append((match.start(), match.end(), match.group(0)))
    return deletion, negated


def _inside_phrase(start: int, end: int, text: str, phrases: tuple[str, ...]) -> bool:
    for phrase in phrases:
        cursor = 0
        while True:
            found = text.find(phrase, cursor)
            if found < 0:
                break
            if found <= start and end <= found + len(phrase):
                return True
            cursor = found + 1
    return False


def classify_request(request_text: str) -> Classification:
    text = request_text.casefold()
    deletion, negated = _find_terms(text)
    preservation = tuple(phrase for phrase in _PRESERVE if phrase in text)
    tasks = tuple(phrase for phrase in _NON_DELETION_TASKS if phrase in text)
    authorizing = tuple(
        item for item in deletion if not _inside_phrase(item[0], item[1], text, preservation)
    )
    if authorizing:
        return Classification(
            RequestIntent.DELETION,
            tuple(item[2] for item in authorizing),
            tuple(item[2] for item in negated),
            preservation,
        )
    if negated or preservation or tasks:
        return Classification(
            RequestIntent.NON_DELETION,
            (),
            tuple(item[2] for item in negated),
            preservation + tasks,
        )
    return Classification(RequestIntent.AMBIGUOUS, (), tuple(item[2] for item in negated), ())
