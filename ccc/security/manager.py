import json
import re
from pathlib import Path

from ..utils.formatting import get_timestamp

# Audit log rotation: keep last N lines when file exceeds this size
_AUDIT_MAX_BYTES = 5 * 1024 * 1024   # 5 MB
_AUDIT_KEEP_LINES = 10_000


class SecurityManager:
    """Manage security settings and audit logging."""

    def __init__(self, root: Path, config: dict):
        self.root = root
        self.config = config
        security_config = config.get("security", {})
        self.mode = security_config.get("mode", "offline")
        self.audit_enabled = security_config.get("audit_log", True)
        self.redact_secrets = security_config.get("redact_secrets", True)

    def is_ai_enabled(self) -> bool:
        """Check if AI features are enabled."""
        return self.mode in ["private-ai", "public-ai"]

    def log_audit(self, action: str, details: dict) -> None:
        """
        Append one JSON-lines entry to audit.log.

        Uses append mode (O_APPEND) — never reads the whole file.
        Rotates when the file exceeds _AUDIT_MAX_BYTES.
        """
        if not self.audit_enabled:
            return

        audit_file = self.root / ".llm-context" / "audit.log"
        entry = {
            "timestamp": get_timestamp(),
            "action": action,
            "mode": self.mode,
        }
        entry.update(details)

        try:
            audit_file.parent.mkdir(parents=True, exist_ok=True)

            # Rotate if over size limit
            if audit_file.exists() and audit_file.stat().st_size > _AUDIT_MAX_BYTES:
                self._rotate_audit(audit_file)

            # True append — no read required
            with audit_file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")

        except Exception:
            pass  # audit must never crash the main flow

    def _rotate_audit(self, audit_file: Path) -> None:
        """Keep the last _AUDIT_KEEP_LINES lines, discard the rest."""
        try:
            lines = audit_file.read_text(encoding="utf-8", errors="replace").splitlines()
            trimmed = "\n".join(lines[-_AUDIT_KEEP_LINES:]) + "\n"
            audit_file.write_text(trimmed, encoding="utf-8")
        except Exception:
            pass

    def redact_content(self, content: str) -> str:
        """Redact sensitive patterns from content."""
        if not self.redact_secrets:
            return content

        patterns = [
            # Assignment-style: KEY = "value" or KEY=value
            (r"(API[_-]?KEY\s*=\s*)[\"']?[^\"'\s]+[\"']?", r"\1****"),
            (r"(PASSWORD\s*=\s*)[\"']?[^\"'\s]+[\"']?", r"\1****"),
            (r"(SECRET\s*=\s*)[\"']?[^\"'\s]+[\"']?", r"\1****"),
            (r"(TOKEN\s*=\s*)[\"']?[^\"'\s]+[\"']?", r"\1****"),
            # HTTP auth headers
            (r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", "Bearer ****"),
            (r"Basic\s+[A-Za-z0-9+/]+=*", "Basic ****"),
            # PEM private key blocks
            (r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
             "-----BEGIN PRIVATE KEY----- **** -----END PRIVATE KEY-----"),
            # Connection / DSN strings  postgresql://user:pass@host
            (r"((?:postgresql|mysql|mongodb|amqp|redis|sqlite)://[^:]+:)[^@\s\"']+(@)",
             r"\1****\2"),
            # AWS access key IDs  AKIA...
            (r"\bAKIA[0-9A-Z]{16}\b", "AKIA****"),
            # JSON / YAML embedded secrets  "password": "value"
            (r'("(?:password|api_key|secret|token|auth)"\s*:\s*")[^"]+(")',
             r"\1****\2"),
            (r"('(?:password|api_key|secret|token|auth)'\s*:\s*')[^']+(')",
             r"\1****\2"),
        ]

        result = content
        for pattern, replacement in patterns:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        return result

    def print_status(self) -> None:
        """Print security status."""
        print("")
        print("=" * 60)
        print("  Security Status")
        print("=" * 60)
        print(f"  Mode: {self.mode.upper()}")

        if self.mode == "offline":
            print("  External APIs: DISABLED")
            print("  AI Features: DISABLED")
        elif self.mode == "private-ai":
            print("  External APIs: ALLOWED (Private infrastructure)")
            print("  AI Features: ENABLED")
        else:
            print("  External APIs: ALLOWED (Public services)")
            print("  AI Features: ENABLED")
            print("  WARNING: Code may be sent to external AI services")

        redact_status = "ENABLED" if self.redact_secrets else "DISABLED"
        audit_status = "ENABLED" if self.audit_enabled else "DISABLED"
        print(f"  Secret Redaction: {redact_status}")
        print(f"  Audit Logging: {audit_status}")
        print("=" * 60)
        print("")
