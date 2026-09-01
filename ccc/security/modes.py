"""
Security mode definitions for CCC.

CCC supports three security tiers that control whether — and where — code
context is allowed to leave the local machine.

Modes
-----
``offline``
    No external network calls.  AI features are disabled.  Secret redaction
    is always on.  Suitable for air-gapped environments and proprietary
    codebases that must not leave the machine.

``private-ai``
    AI features are enabled but traffic is routed through infrastructure that
    the operator controls (self-hosted LLM, private VPC endpoint, etc.).
    Secret redaction is on by default but can be relaxed in config.

``public-ai``
    AI features are enabled and code context may be sent to public third-party
    AI services (Anthropic, OpenAI, …).  Users must explicitly opt in to this
    mode.  A warning is printed at startup.

Usage::

    from ccc.security.modes import SecurityMode, validate_mode, describe_mode

    mode = validate_mode(config.get("security", {}).get("mode", "offline"))
    print(describe_mode(mode))
"""

from __future__ import annotations

from enum import Enum
from typing import Dict


class SecurityMode(str, Enum):
    """Enumeration of CCC security tiers."""

    OFFLINE = "offline"
    PRIVATE_AI = "private-ai"
    PUBLIC_AI = "public-ai"


# Human-readable descriptions shown in --security-status output and docs.
_DESCRIPTIONS: Dict[SecurityMode, str] = {
    SecurityMode.OFFLINE: (
        "Offline — no external network calls; AI features disabled; "
        "suitable for air-gapped or proprietary codebases."
    ),
    SecurityMode.PRIVATE_AI: (
        "Private-AI — AI features enabled via operator-controlled infrastructure "
        "(self-hosted LLM, private VPC endpoint, etc.); secret redaction on by default."
    ),
    SecurityMode.PUBLIC_AI: (
        "Public-AI — AI features enabled; code context may be sent to public "
        "third-party services (Anthropic, OpenAI, …); explicit opt-in required."
    ),
}

# Capabilities unlocked per mode (used by SecurityManager.is_ai_enabled etc.)
_CAPABILITIES: Dict[SecurityMode, Dict[str, bool]] = {
    SecurityMode.OFFLINE: {
        "ai_enabled": False,
        "external_apis": False,
        "redact_secrets": True,
    },
    SecurityMode.PRIVATE_AI: {
        "ai_enabled": True,
        "external_apis": True,
        "redact_secrets": True,
    },
    SecurityMode.PUBLIC_AI: {
        "ai_enabled": True,
        "external_apis": True,
        "redact_secrets": True,  # still on — public mode is more exposure, not less safety
    },
}


def validate_mode(value: str) -> SecurityMode:
    """Parse and validate a mode string from config.

    Parameters
    ----------
    value:
        Raw string from the config file (e.g. ``"offline"``, ``"private-ai"``).

    Returns
    -------
    SecurityMode
        The corresponding enum member.

    Raises
    ------
    ValueError
        If *value* does not map to a known mode.  The error message lists valid
        options so the user can fix their config immediately.
    """
    try:
        return SecurityMode(value.lower().strip())
    except ValueError:
        valid = ", ".join(f'"{m.value}"' for m in SecurityMode)
        raise ValueError(
            f"Unknown security mode {value!r}. Valid options: {valid}. "
            "Set it under [security] mode in your ccc config file."
        ) from None


def describe_mode(mode: SecurityMode) -> str:
    """Return a one-line human description of *mode*."""
    return _DESCRIPTIONS[mode]


def capabilities(mode: SecurityMode) -> Dict[str, bool]:
    """Return a dict of boolean capability flags for *mode*.

    Keys: ``ai_enabled``, ``external_apis``, ``redact_secrets``.
    """
    return dict(_CAPABILITIES[mode])


def is_ai_enabled(mode: SecurityMode) -> bool:
    """Return True if AI features are permitted in *mode*."""
    return _CAPABILITIES[mode]["ai_enabled"]
