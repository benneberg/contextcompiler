"""File tree generator."""
from pathlib import Path
from typing import List, Tuple

from .base import BaseGenerator
from ..file_index import FileIndex
from ..utils.files import EXCLUDE_DIRS
from ..utils.formatting import get_timestamp, human_readable_size


class TreeGenerator(BaseGenerator):
    """Generate file tree visualization from a pre-built FileIndex."""

    def __init__(self, root: Path, config: dict, file_index: FileIndex):
        super().__init__(root, config)
        self.file_index = file_index

    @property
    def output_filename(self) -> str:
        return "tree.txt"

    def generate(self) -> Tuple[str, List[Path]]:
        lines = [
            f"# File Tree: {self.root.name}",
            f"# Generated: {get_timestamp()}",
            f"# Files indexed: {self.file_index.stats()['total_files']}",
            "",
        ]
        max_depth = self.config.get("max_tree_depth", 6)
        max_files = self.config.get("max_files_in_tree", 500)
        self._walk(self.root, "", lines, 0, max_depth, max_files)
        return "\n".join(lines), []

    def _walk(
        self,
        directory: Path,
        prefix: str,
        lines: list,
        depth: int,
        max_depth: int,
        max_files: int,
    ) -> None:
        if depth > max_depth:
            lines.append(f"{prefix}... (depth limit)")
            return
        if len(lines) > max_files:
            lines.append(f"{prefix}... (file limit reached)")
            return

        try:
            entries = sorted(
                directory.iterdir(),
                key=lambda e: (not e.is_dir(), e.name.lower()),
            )
        except PermissionError:
            return

        entries = [e for e in entries if e.name not in EXCLUDE_DIRS]

        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "`-- " if is_last else "|-- "
            extension = "    " if is_last else "|   "

            if entry.is_dir():
                # Use index count instead of re-walking
                count = sum(
                    1 for f in self.file_index.all_files()
                    if str(f.path).startswith(str(entry))
                )
                lines.append(f"{prefix}{connector}{entry.name}/ ({count} files)")
                self._walk(
                    entry, prefix + extension, lines, depth + 1, max_depth, max_files
                )
            else:
                try:
                    size_str = human_readable_size(entry.stat().st_size)
                    lines.append(f"{prefix}{connector}{entry.name} ({size_str})")
                except Exception:
                    lines.append(f"{prefix}{connector}{entry.name}")