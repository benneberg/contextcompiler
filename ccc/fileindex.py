"""
FileIndex — single repository scan shared across all generators.

Builds once, reused by every generator to avoid repeated os.walk() calls.
For large repos (100k+ files) this is the single biggest performance win.
"""
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set

from .utils.files import EXCLUDE_DIRS, BINARY_EXTENSIONS, SENSITIVE_PATTERNS
import fnmatch


@dataclass
class FileInfo:
    """Metadata for a single file in the index."""
    path: Path
    rel_path: str          # relative to repo root, forward slashes
    ext: str               # lowercase extension including dot, e.g. ".py"
    size: int              # bytes
    mtime: float           # unix timestamp


class FileIndex:
    """
    Single-scan file index for a repository.

    Build once at the start of generation, then pass to every generator
    so they can filter by extension/pattern without re-walking the disk.
    """

    def __init__(self, root: Path, exclude_dirs: Optional[Set[str]] = None):
        self.root = root
        self.exclude_dirs = exclude_dirs or EXCLUDE_DIRS
        self.files: List[FileInfo] = []
        self._by_ext: Dict[str, List[FileInfo]] = {}
        self._built = False

    def build(self) -> "FileIndex":
        """Walk the repository once and populate the index."""
        self.files = []
        self._by_ext = {}

        for dirpath, dirnames, filenames in os.walk(self.root):
            # Prune excluded directories in-place so os.walk won't recurse into them
            dirnames[:] = [
                d for d in dirnames
                if d not in self.exclude_dirs
                and not d.startswith(".")
                or d in {".github", ".llm-context"}  # keep these
            ]
            # Re-apply: simpler and correct
            dirnames[:] = [d for d in dirnames if d not in self.exclude_dirs]

            for name in filenames:
                p = Path(dirpath) / name

                # Skip binary files by extension fast-path
                ext = p.suffix.lower()
                if ext in BINARY_EXTENSIONS:
                    continue

                # Skip sensitive paths
                rel = str(p.relative_to(self.root))
                if self._is_sensitive(rel):
                    continue

                try:
                    stat = p.stat()
                except OSError:
                    continue

                info = FileInfo(
                    path=p,
                    rel_path=rel.replace("\\", "/"),
                    ext=ext,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                )
                self.files.append(info)

                if ext not in self._by_ext:
                    self._by_ext[ext] = []
                self._by_ext[ext].append(info)

        self._built = True
        return self

    def by_extension(self, *exts: str) -> List[FileInfo]:
        """Return all files with any of the given extensions (e.g. '.py', '.ts')."""
        result = []
        for ext in exts:
            result.extend(self._by_ext.get(ext.lower(), []))
        return result

    def by_language(self, language: str) -> List[FileInfo]:
        """Return files for a named language."""
        lang_exts = {
            "python":     (".py",),
            "typescript": (".ts", ".tsx"),
            "javascript": (".js", ".jsx"),
            "rust":       (".rs",),
            "go":         (".go",),
            "csharp":     (".cs",),
            "java":       (".java",),
            "ruby":       (".rb",),
        }
        exts = lang_exts.get(language, ())
        return self.by_extension(*exts)

    def all_files(self) -> List[FileInfo]:
        """Return every indexed file."""
        return self.files

    def detect_languages(self, min_files: int = 2) -> List[str]:
        """Detect languages present in the repo by extension count."""
        ext_to_lang = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".tsx": "typescript", ".jsx": "javascript", ".rs": "rust",
            ".go": "go", ".java": "java", ".cs": "csharp",
            ".rb": "ruby", ".php": "php", ".swift": "swift", ".kt": "kotlin",
        }
        counts: Dict[str, int] = {}
        for ext, files in self._by_ext.items():
            lang = ext_to_lang.get(ext)
            if lang:
                counts[lang] = counts.get(lang, 0) + len(files)

        return [
            lang for lang, count
            in sorted(counts.items(), key=lambda x: -x[1])
            if count >= min_files
        ][:5]

    def stats(self) -> Dict[str, int]:
        """Return summary statistics."""
        return {
            "total_files": len(self.files),
            "total_size_bytes": sum(f.size for f in self.files),
            "extensions": len(self._by_ext),
        }

    def _is_sensitive(self, rel_path: str) -> bool:
        for pattern in SENSITIVE_PATTERNS:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
        return False


class HashCache:
    """
    Persistent mtime-gated file hash cache.

    Avoids rehashing files whose mtime hasn't changed since the last run.
    Stored at .llm-context/.ccc-hashcache.json.

    Structure:
        { "rel/path/to/file": { "mtime": 1234567.89, "hash": "abc123" } }
    """

    CACHE_FILE = ".ccc-hashcache.json"

    def __init__(self, root: Path):
        self.root = root
        self._cache: Dict[str, Dict] = {}
        self._dirty = False
        self._load()

    def _cache_path(self) -> Path:
        return self.root / ".llm-context" / self.CACHE_FILE

    def _load(self) -> None:
        path = self._cache_path()
        if not path.exists():
            return
        try:
            self._cache = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            self._cache = {}

    def save(self) -> None:
        """Persist cache to disk if it was modified."""
        if not self._dirty:
            return
        path = self._cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(json.dumps(self._cache, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get_hash(self, file_info: FileInfo) -> str:
        """
        Return the hash for a file, using the cache if the mtime is unchanged.
        Falls back to computing the hash and storing the result.
        """
        key = file_info.rel_path
        cached = self._cache.get(key)

        if cached and abs(cached.get("mtime", 0) - file_info.mtime) < 0.01:
            return cached["hash"]

        # Cache miss — compute hash
        file_hash = self._compute_hash(file_info.path)
        self._cache[key] = {"mtime": file_info.mtime, "hash": file_hash}
        self._dirty = True
        return file_hash

    def _compute_hash(self, path: Path) -> str:
        try:
            size = path.stat().st_size
            with open(path, "rb") as f:
                if size > 100_000:
                    start = f.read(10_000)
                    f.seek(-10_000, 2)
                    end = f.read(10_000)
                    data = start + end
                else:
                    data = f.read()
            return hashlib.md5(data).hexdigest()[:12]
        except Exception:
            return ""