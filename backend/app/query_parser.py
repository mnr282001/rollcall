from __future__ import annotations

import re

# Ordered from most to least specific. Each must capture a single "name" group.
_PATTERNS = [
    re.compile(r"\bwhat\s+is\s+(?P<name>\w+)\s+working\s+on\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+has\s+(?P<name>\w+)\s+been\s+working\s+on\b", re.IGNORECASE),
    re.compile(r"\bactivity\s+for\s+(?P<name>\w+)\b", re.IGNORECASE),
    re.compile(r"\bfor\s+(?P<name>\w+)\s*$", re.IGNORECASE),
]

# Fallback: the last capitalized word that isn't a sentence-leading question word.
_LEADING_QUESTION_WORDS = {"what", "show", "who", "how"}
_CAPITALIZED_WORD = re.compile(r"\b([A-Z][a-z]+)\b")


def parse_name(question: str) -> str | None:
    """Extracts the person's name from a free-form question, or None if none is found."""
    for pattern in _PATTERNS:
        match = pattern.search(question)
        if match:
            return match.group("name")

    candidates = [
        word for word in _CAPITALIZED_WORD.findall(question) if word.lower() not in _LEADING_QUESTION_WORDS
    ]
    return candidates[-1] if candidates else None
