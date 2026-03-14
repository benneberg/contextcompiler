"""
Symbol index generator.

Produces a machine-readable JSON map of every significant symbol
(class, function, type, route) to its file and line number.

Example output:
{
  "UserService.create_user": {"file": "services/user.py", "line": 42, "kind": "function"},
  "AuthMiddleware":          {"file": "middleware/auth.py", "line": 10, "kind": "class"},
  "POST /api/users":         {"file": "routes/users.py",   "line": 88, "kind": "route"}
}
"""
import ast
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

from .base import BaseGenerator
from ..file_index import FileIndex
from ..utils.files import safe_read_text
from ..utils.formatting import get_timestamp


class SymbolIndexGenerator(BaseGenerator):
    """Generate a semantic symbol index for fast LLM navigation."""

    def __init__(self, root: Path, config: dict, file_index: FileIndex):
        super().__init__(root, config)
        self.index = file_index

    @property
    def output_filename(self) -> str:
        return "symbol-index.json"

    def generate(self) -> Tuple[str, List[Path]]:
        symbols: Dict[str, dict] = {}
        source_files: List[Path] = []
        langs = self.index.detect_languages()

        if "python" in langs:
            py_syms, py_files = self._index_python()
            symbols.update(py_syms)
            source_files.extend(py_files)

        if "typescript" in langs or "javascript" in langs:
            ts_syms, ts_files = self._index_typescript()
            symbols.update(ts_syms)
            source_files.extend(ts_files)

        output = {
            "_meta": {
                "generated": get_timestamp(),
                "total_symbols": len(symbols),
            },
            "symbols": symbols,
        }

        return json.dumps(output, indent=2), source_files

    # ── Python ────────────────────────────────────────────────────────────────

    def _index_python(self) -> Tuple[Dict[str, dict], List[Path]]:
        symbols: Dict[str, dict] = {}
        source_files: List[Path] = []

        route_pattern = re.compile(
            r"@(?:app|router|api)\.(get|post|put|patch|delete|websocket)"
            r'\s*\(\s*["\']([^"\']*)["\']'
        )

        for fi in self.index.by_extension(".py"):
            content = safe_read_text(fi.path)
            if not content:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue

            source_files.append(fi.path)

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    symbols[node.name] = {
                        "file": fi.rel_path,
                        "line": node.lineno,
                        "kind": "class",
                    }
                    # Index public methods as ClassName.method_name
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if not item.name.startswith("_") or item.name == "__init__":
                                key = f"{node.name}.{item.name}"
                                symbols[key] = {
                                    "file": fi.rel_path,
                                    "line": item.lineno,
                                    "kind": "method",
                                }

                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("_"):
                        symbols[node.name] = {
                            "file": fi.rel_path,
                            "line": node.lineno,
                            "kind": "function",
                        }

            # Index routes separately
            for method, path in route_pattern.findall(content):
                key = f"{method.upper()} {path}"
                line = content[: content.find(path)].count("\n") + 1
                symbols[key] = {
                    "file": fi.rel_path,
                    "line": line,
                    "kind": "route",
                }

        return symbols, source_files

    # ── TypeScript ────────────────────────────────────────────────────────────

    def _index_typescript(self) -> Tuple[Dict[str, dict], List[Path]]:
        symbols: Dict[str, dict] = {}
        source_files: List[Path] = []

        patterns = [
            ("class",     re.compile(r"(?:export\s+)?class\s+(\w+)")),
            ("interface", re.compile(r"(?:export\s+)?interface\s+(\w+)")),
            ("type",      re.compile(r"(?:export\s+)?type\s+(\w+)\s*=")),
            ("enum",      re.compile(r"(?:export\s+)?enum\s+(\w+)")),
            ("function",  re.compile(r"export\s+(?:async\s+)?function\s+(\w+)")),
        ]

        route_pattern = re.compile(
            r"(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*[\"'/]([^\"']*)[\"']"
        )

        for fi in self.index.by_extension(".ts", ".tsx"):
            if ".spec." in fi.path.name or ".test." in fi.path.name:
                continue
            content = safe_read_text(fi.path)
            if not content:
                continue

            source_files.append(fi.path)
            lines_list = content.split("\n")

            for kind, pattern in patterns:
                for match in pattern.finditer(content):
                    name = match.group(1)
                    line = content[: match.start()].count("\n") + 1
                    symbols[name] = {"file": fi.rel_path, "line": line, "kind": kind}

            for method, path in route_pattern.findall(content):
                key = f"{method.upper()} {path}"
                line = content[: content.find(path)].count("\n") + 1
                symbols[key] = {"file": fi.rel_path, "line": line, "kind": "route"}

        return symbols, source_files