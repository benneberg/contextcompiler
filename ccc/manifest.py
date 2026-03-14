import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional, List

from .models import FileManifestEntry
from .utils.files import safe_read_text, safe_write_text
from .utils.hashing import hash_file_quick, compute_string_hash
from .utils.formatting import get_timestamp


class GenerationManifest:
    """Tracks what was generated and when."""

    def __init__(self, version: str, generated_at: str, project_fingerprint: str, files: dict):
        self.version = version
        self.generated_at = generated_at
        self.project_fingerprint = project_fingerprint
        self.files = files

    @classmethod
    def load(cls, root: Path) -> Optional["GenerationManifest"]:
        """Load manifest from disk."""
        manifest_file = root / ".llm-context" / "manifest.json"
        if not manifest_file.exists():
            return None

        try:
            content = safe_read_text(manifest_file)
            if not content:
                return None
            data = json.loads(content)
            if data.get("version") != "4":
                print("  Manifest version mismatch, will regenerate")
                return None
            return cls(
                version=data["version"],
                generated_at=data["generated_at"],
                project_fingerprint=data["project_fingerprint"],
                files=data["files"],
            )
        except Exception as e:
            print(f"  Warning: Could not load manifest: {e}")
            return None

    def save(self, root: Path) -> None:
        """Save manifest to disk."""
        manifest_file = root / ".llm-context" / "manifest.json"
        data = {
            "version": self.version,
            "generated_at": self.generated_at,
            "project_fingerprint": self.project_fingerprint,
            "files": self.files,
        }
        safe_write_text(manifest_file, json.dumps(data, indent=2))

    def get_entry(self, filename: str) -> Optional[FileManifestEntry]:
        """Get manifest entry for a file."""
        entry_dict = self.files.get(filename)
        if not entry_dict:
            return None
        return FileManifestEntry(**entry_dict)

    def set_entry(self, filename: str, entry: FileManifestEntry) -> None:
        """Set manifest entry for a file."""
        self.files[filename] = asdict(entry)


class SmartUpdater:
    """Manages incremental updates based on file changes."""

    def __init__(self, root: Path, config: dict, force: bool = False):
        self.root = root
        self.config = config
        self.force = force
        self.old_manifest = None if force else GenerationManifest.load(root)
        self.new_manifest = GenerationManifest(
            version="4",
            generated_at=get_timestamp(),
            project_fingerprint=self._compute_fingerprint(),
            files={},
        )
        self.stats = {"regenerated": 0, "skipped": 0, "new": 0}

    def _compute_fingerprint(self) -> str:
        """Compute project fingerprint from key files."""
        key_files = [
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
            "go.mod",
            "requirements.txt",
            "poetry.lock",
            "package-lock.json",
            ".env.example",
            "docker-compose.yml",
        ]

        parts = []
        for filename in key_files:
            path = self.root / filename
            if path.exists():
                file_hash = hash_file_quick(path)
                parts.append(f"{filename}:{file_hash}")

        import hashlib
        combined = "|".join(sorted(parts))
        return hashlib.md5(combined.encode()).hexdigest()[:16]

    def _get_strategy(self, filepath: str) -> str:
        """Get update strategy for a file."""
        import fnmatch

        strategies = self.config.get("update_strategies", {})
        if filepath in strategies:
            return strategies[filepath]

        for pattern, strategy in strategies.items():
            if "*" in pattern:
                if fnmatch.fnmatch(filepath, pattern):
                    return strategy
            elif filepath.endswith(pattern):
                return strategy

        return "always"

    def should_regenerate(self, filepath: str, source_files: Optional[List[Path]] = None):
        """Determine if a file needs regeneration."""
        if self.force:
            return True, "force mode"

        strategy = self._get_strategy(filepath)

        if strategy == "always":
            return True, "always regenerate"

        if strategy == "never":
            return False, "never regenerate"

        if strategy == "if-missing":
            check_path = self.root / filepath
            if not check_path.exists():
                return True, "file missing"
            return False, "file exists"

        if strategy == "if-changed":
            if not self.old_manifest:
                return True, "first run"

            old_entry = self.old_manifest.get_entry(filepath)
            if not old_entry:
                return True, "new file"

            if source_files:
                old_hashes = old_entry.source_hashes
                new_hashes = [hash_file_quick(f) for f in source_files]
                if new_hashes != old_hashes:
                    return True, "source files changed"

            old_fp = self.old_manifest.project_fingerprint
            new_fp = self.new_manifest.project_fingerprint
            if old_fp != new_fp:
                return True, "project dependencies changed"

            return False, "up to date"

        return True, "default"

    def mark_generated(
        self,
        filepath: str,
        content: str,
        source_files: Optional[List[Path]] = None,
        is_new: bool = False,
    ) -> None:
        """Record that a file was generated."""
        strategy = self._get_strategy(filepath)
        src_files = source_files or []
        entry = FileManifestEntry(
            hash=compute_string_hash(content),
            size=len(content),
            generated_at=get_timestamp(),
            source_files=[str(f.relative_to(self.root)) for f in src_files],
            source_hashes=[hash_file_quick(f) for f in src_files],
            strategy=strategy,
        )
        self.new_manifest.set_entry(filepath, entry)
        if is_new:
            self.stats["new"] += 1
        else:
            self.stats["regenerated"] += 1

    def mark_skipped(self, filepath: str) -> None:
        """Record that a file was skipped."""
        if self.old_manifest:
            old_entry = self.old_manifest.get_entry(filepath)
            if old_entry:
                self.new_manifest.set_entry(filepath, old_entry)
        self.stats["skipped"] += 1

    def print_summary(self) -> None:
        """Print update statistics."""
        total = sum(self.stats.values())
        print("")
        print("-" * 60)
        print("  Update Summary:")
        print(f"  - Regenerated: {self.stats['regenerated']}")
        print(f"  - Skipped (up to date): {self.stats['skipped']}")
        print(f"  - New files: {self.stats['new']}")
        print(f"  - Total: {total}")
        print("-" * 60)
        print("")
