from pathlib import Path
import hashlib


def hash_file_quick(path: Path) -> str:
    """Generate a quick hash of a file."""
    try:
        size = path.stat().st_size
        if size > 100000:
            with open(path, "rb") as f:
                start = f.read(10000)
                f.seek(-10000, 2)
                end = f.read(10000)
                data = start + end
        else:
            data = path.read_bytes()
        return hashlib.md5(data).hexdigest()[:12]
    except Exception:
        return ""


def compute_string_hash(content: str) -> str:
    """Hash string content."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]
