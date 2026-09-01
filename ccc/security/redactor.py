"""
Secret redaction for CCC output.

Extracted from SecurityManager so it can be used independently — e.g. in
streaming generators that don't need the full audit-log machinery.

Usage::

    from ccc.security.redactor import redact

    clean = redact(raw_content)               # uses default patterns
    clean = redact(raw_content, extra=[...])  # append extra (pattern, repl) pairs
"""

from __future__ import annotations

import re
from typing import List, Tuple

# ── Default redaction patterns ─────────────────────────────────────────────────
#
# Each entry is (regex_pattern, replacement).
# Patterns are applied in order; earlier patterns shadow later ones where they
# overlap (e.g. "Bearer" catches JWT before the generic TOKEN= rule fires on it).
#
# All patterns are compiled with re.IGNORECASE at call-time.

_DEFAULT_PATTERNS: List[Tuple[str, str]] = [
    # HTTP authorisation headers
    (r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", "Bearer ****"),
    (r"Basic\s+[A-Za-z0-9+/]+=*", "Basic ****"),

    # PEM private-key blocks (multi-line)
    (
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
        "-----BEGIN PRIVATE KEY----- **** -----END PRIVATE KEY-----",
    ),

    # DSN / connection strings  scheme://user:pass@host
    (
        r"((?:postgresql|mysql|mongodb|amqp|redis|sqlite)://[^:]+:)[^@\s\"']+(@)",
        r"\1****\2",
    ),

    # AWS access-key IDs  AKIA…
    (r"\bAKIA[0-9A-Z]{16}\b", "AKIA****"),

    # Assignment-style secrets in env/config files
    (r"(API[_-]?KEY\s*=\s*)[\"']?[^\"'\s]+[\"']?", r"\1****"),
    (r"(PASSWORD\s*=\s*)[\"']?[^\"'\s]+[\"']?", r"\1****"),
    (r"(SECRET\s*=\s*)[\"']?[^\"'\s]+[\"']?", r"\1****"),
    (r"(TOKEN\s*=\s*)[\"']?[^\"'\s]+[\"']?", r"\1****"),

    # JSON / YAML inline secrets  "password": "value"
    (r'("(?:password|api_key|secret|token|auth)"\s*:\s*")[^"]+(")', r"\1****\2"),
    (r"('(?:password|api_key|secret|token|auth)'\s*:\s*')[^']+(')", r"\1****\2"),
]


def redact(content: str, extra: List[Tuple[str, str]] | None = None) -> str:
    """Apply secret-redaction patterns to *content* and return the cleaned string.

    Parameters
    ----------
    content:
        Raw text that may contain secrets (file content, CLI output, etc.).
    extra:
        Optional list of additional ``(pattern, replacement)`` pairs appended
        after the defaults.  Use this for project-specific secrets that the
        default ruleset doesn't cover.

    Returns
    -------
    str
        Content with secrets replaced by ``****``.
    """
    patterns = list(_DEFAULT_PATTERNS)
    if extra:
        patterns.extend(extra)

    result = content
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def redact_dict(data: dict, extra: List[Tuple[str, str]] | None = None) -> dict:
    """Recursively redact string values inside a dictionary (e.g. parsed JSON/YAML).

    Only string leaf-values are modified; keys are never altered.
    """
    out: dict = {}
    for k, v in data.items():
        if isinstance(v, str):
            out[k] = redact(v, extra)
        elif isinstance(v, dict):
            out[k] = redact_dict(v, extra)
        elif isinstance(v, list):
            out[k] = [
                redact(item, extra) if isinstance(item, str) else item for item in v
            ]
        else:
            out[k] = v
    return out
