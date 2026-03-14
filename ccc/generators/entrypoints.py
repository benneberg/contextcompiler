"""Entry point detector — finds main files, servers, CLIs, test suites."""
import json
from pathlib import Path
from typing import List, Tuple

from .base import BaseGenerator
from ..file_index import FileIndex
from ..utils.files import should_skip_path


class EntryPointGenerator(BaseGenerator):
    """Detect application entry points from the file index."""

    def __init__(self, root: Path, config: dict, file_index: FileIndex):
        super().__init__(root, config)
        self.index = file_index

    @property
    def output_filename(self) -> str:
        return "entry-points.json"

    def generate(self) -> Tuple[str, List[Path]]:
        entry_points = {
            "main_files": [],
            "server_files": [],
            "cli_files": [],
            "test_suites": [],
        }
        source_files: List[Path] = []

        main_names = {
            "main.py", "app.py", "__main__.py", "manage.py",
            "main.ts", "index.ts", "server.ts", "app.ts",
            "main.js", "index.js", "server.js", "app.js",
            "main.go", "main.rs",
        }
        server_names = {"server.py", "wsgi.py", "asgi.py"}
        cli_names    = {"cli.py", "cli.ts", "cmd.py"}

        for fi in self.index.all_files():
            name = fi.path.name
            if name in main_names:
                rel = fi.rel_path
                if rel not in entry_points["main_files"]:
                    entry_points["main_files"].append(rel)
                    source_files.append(fi.path)
            elif name in server_names:
                rel = fi.rel_path
                if rel not in entry_points["server_files"]:
                    entry_points["server_files"].append(rel)
            elif name in cli_names:
                rel = fi.rel_path
                if rel not in entry_points["cli_files"]:
                    entry_points["cli_files"].append(rel)

        for test_dir in ["tests", "test", "__tests__", "spec"]:
            if (self.root / test_dir).is_dir():
                entry_points["test_suites"].append(test_dir)

        return json.dumps(entry_points, indent=2), source_files
