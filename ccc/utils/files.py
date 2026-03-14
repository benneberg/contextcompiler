from pathlib import Path
from typing import Optional
import fnmatch

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp",
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".obj",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".pyc", ".pyo", ".class", ".o", ".a", ".lib",
    ".sqlite", ".db", ".sqlite3",
    ".DS_Store",
}

EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".env",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".next",
    ".nuxt",
    "target",
    ".terraform",
    "vendor",
    "coverage",
    ".coverage",
    "htmlcov",
    ".idea",
    ".vscode",
    "eggs",
    ".eggs",
    ".cache",
    ".parcel-cache",
    ".turbo",
}

SENSITIVE_PATTERNS = [
    "**/.env",
    "**/.env.*",
    "**/secrets/**",
    "**/certs/**",
    "**/keys/**",
    "**/credentials/**",
    "**/*_key",
    "**/*_secret",
    "**/*.pem",
    "**/*.key",
]


def is_binary_file(path: Path) -> bool:
    """Check if a file is binary."""
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
        return b"\0" in chunk
    except Exception:
        return True


def safe_read_text(path: Path) -> Optional[str]:
    """Safely read a text file with UTF-8 encoding."""
    if is_binary_file(path):
        return None
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


def safe_write_text(path: Path, content: str) -> bool:
    """Safely write text to a file with UTF-8 encoding."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False


def should_skip_path(path: Path) -> bool:
    """Check if path should be skipped based on exclusion rules."""
    path_parts = set(path.parts)
    if path_parts & EXCLUDE_DIRS:
        return True

    path_str = str(path)
    for pattern in SENSITIVE_PATTERNS:
        if fnmatch.fnmatch(path_str, pattern):
            return True
    return False
