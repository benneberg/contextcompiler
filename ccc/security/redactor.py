"""Secret pattern detection and redaction."""
import re

class SecretRedactor:
    """Redact sensitive patterns from content."""
    
    PATTERNS = [
        (r"(API[_-]?KEY\s*=\s*)[\"']?[^\"'\s]+[\"']?", r"\1****"),
        # ... (move patterns from SecurityManager)
    ]
    
    def redact(self, content: str) -> str:
        """Redact secrets from content."""
        # ... (move from SecurityManager)
