"""File operation utilities."""
from pathlib import Path
from typing import Optional

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    # ... (move from main file)
}

def is_binary_file(path: Path) -> bool:
    """Check if file is binary."""
    # ... (move from main file)

def safe_read_text(path: Path) -> Optional[str]:
    """Safely read text file with UTF-8 encoding."""
    # ... (move from main file)

def safe_write_text(path: Path, content: str) -> bool:
    """Safely write text file with UTF-8 encoding."""
    # ... (move from main file)

def should_skip_path(path: Path) -> bool:
    """Check if path should be skipped."""
    # ... (move from main file)
