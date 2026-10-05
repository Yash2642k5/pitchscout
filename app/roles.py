"""Classifies job titles into function buckets, in code, from fixed keyword rules."""

import re

# Order matters: the first function whose keywords match wins.
_RULES: list[tuple[str, list[str]]] = [
    (
        "ML and research",
        ["machine learning", "ml", "ai", "data scien", "research", "nlp", "deep learning"],
    ),
    (
        "Engineering",
        ["engineer", "developer", "devops", "sre", "backend", "frontend", "full stack"],
    ),
    (
        "Sales and marketing",
        ["sales", "account", "marketing", "growth", "business development", "customer success"],
    ),
]

_OTHER = "Other"


def _matches(keyword: str, title_lower: str) -> bool:
    if keyword == "data scien":
        return "data scien" in title_lower
    pattern = r"\b" + re.escape(keyword) + r"\b"
    return re.search(pattern, title_lower) is not None


def classify_title(title: str) -> str:
    """Returns one of: "ML and research", "Engineering", "Sales and marketing", "Other"."""
    title_lower = (title or "").lower()
    for function, keywords in _RULES:
        for keyword in keywords:
            if _matches(keyword, title_lower):
                return function
    return _OTHER


def role_mix(titles: list[str]) -> dict[str, int]:
    """Counts open roles per function, in the fixed category order."""
    counts = {"ML and research": 0, "Engineering": 0, "Sales and marketing": 0, "Other": 0}
    for title in titles:
        counts[classify_title(title)] += 1
    return counts
