import json
import re
from pathlib import Path

from ..utils.files import safe_read_text, safe_write_text
from ..utils.formatting import get_timestamp


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
        """Log an audit event."""
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
            existing = ""
            if audit_file.exists():
                existing = safe_read_text(audit_file) or ""
            new_entry = json.dumps(entry) + "\n"
            safe_write_text(audit_file, existing + new_entry)
        except Exception:
            pass

    def redact_content(self, content: str) -> str:
        """Redact sensitive patterns from content."""
        if not self.redact_secrets:
            return content

        patterns = [
            (r"(API[_-]?KEY\s*=\s*)[\"']?[^\"'\s]+[\"']?", r"\1****"),
            (r"(PASSWORD\s*=\s*)[\"']?[^\"'\s]+[\"']?", r"\1****"),
            (r"(SECRET\s*=\s*)[\"']?[^\"'\s]+[\"']?", r"\1****"),
            (r"(TOKEN\s*=\s*)[\"']?[^\"'\s]+[\"']?", r"\1****"),
            (r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", "Bearer ****"),
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
