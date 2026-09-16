"""Entry point detector — finds main files, servers, CLIs, and test suites."""

import json
from pathlib import Path
from typing import List, Set, Tuple

from .base import BaseGenerator
from ..file_index import FileIndex

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
        "main.py",
        "app.py",
        "__main__.py",
        "manage.py",
        "main.ts",
        "index.ts",
        "server.ts",
        "app.ts",
        "main.js",
        "index.js",
        "server.js",
        "app.js",
        "main.go",
        "main.rs",
    }
    server_names = {
        "server.py",
        "wsgi.py",
        "asgi.py",
    }
    cli_names = {
        "cli.py",
        "cli.ts",
        "cmd.py",
    }
    for fi in self.index.all_files():
        name = fi.path.name
        rel = fi.rel_path
        if name in main_names:
            if rel not in entry_points["main_files"]:
                entry_points["main_files"].append(rel)
                source_files.append(fi.path)
        elif name in server_names:
            if rel not in entry_points["server_files"]:
                entry_points["server_files"].append(rel)
                source_files.append(fi.path)
        elif name in cli_names:
            if rel not in entry_points["cli_files"]:
                entry_points["cli_files"].append(rel)
                source_files.append(fi.path)
    # Detect test suites recursively.
    #
    # This covers common JS/TS conventions such as:
    #
    #   src/foo.test.ts
    #   src/foo.spec.tsx
    #   packages/foo/__tests__/
    #
    # as well as traditional:
    #
    #   tests/
    #   test/
    #   spec/
    #
    # The FileIndex has already applied the repository's source-boundary
    # rules, so we do not independently scan skipped directories here.
    test_dirs = {
        "tests",
        "test",
        "__tests__",
        "spec",
    }
    test_file_suffixes = (
        ".test.ts",
        ".test.tsx",
        ".test.js",
        ".test.jsx",
        ".spec.ts",
        ".spec.tsx",
        ".spec.js",
        ".spec.jsx",
        "_test.py",
        "_test.go",
    )
    found_test_suites: Set[str] = set()
    for fi in self.index.all_files():
        parts = Path(fi.rel_path).parts
        # A file inside a conventional test directory belongs to that
        # directory's suite. Preserve the complete path so nested suites
        # remain distinguishable.
        for index, part in enumerate(parts[:-1]):
            if part in test_dirs:
                suite_path = Path(*parts[: index + 1]).as_posix()
                found_test_suites.add(suite_path)
        # Detect colocated test files such as:
        #
        #   src/foo.test.ts
        #   packages/parser/src/parser.spec.ts
        #
        # The parent directory is the suite location.
        if fi.path.name.endswith(test_file_suffixes):
            parent = Path(fi.rel_path).parent.as_posix()
            if parent != ".":
                found_test_suites.add(parent)
    entry_points["test_suites"] = sorted(found_test_suites)
    return json.dumps(entry_points, indent=2), source_files
