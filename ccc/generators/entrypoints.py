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

        # Detect test suites recursively rather than only at repository root.

+        # This covers common JS/TS conventions such as:

+        #   src/foo.test.ts

+        #   src/foo.spec.tsx

+        #   packages/foo/__tests__/

+        # as well as traditional tests/, test/, and spec/ directories.

+        test_dirs = {"tests", "test", "__tests__", "spec"}

+        test_file_suffixes = (

+            ".test.ts", ".test.tsx", ".test.js", ".test.jsx",

+            ".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx",

+            "_test.py", "_test.go",

+        )

+

+        found_test_suites = set()

+        for fi in self.index.all_files():

+            if should_skip_path(fi.path):

+                continue

+

+            parts = Path(fi.rel_path).parts

+            if any(part in test_dirs for part in parts[:-1]):

+                found_test_suites.add(

+                    next(part for part in parts if part in test_dirs)

+                )

+

+            if fi.path.name.endswith(test_file_suffixes):

+                found_test_suites.add(str(Path(fi.rel_path).parent))

+

+        entry_points["test_suites"] = sorted(

+            suite for suite in found_test_suites if suite and suite != "."

+        )

 

         return json.dumps(entry_points, indent=2), source_files
