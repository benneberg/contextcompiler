"""
Call graph generator.

Produces .llm-context/call-graph.json — a 2-level function dependency map
showing what each function calls and what calls it.

This complements symbol-index.json: the index tells you WHERE a function is,
the call graph tells you HOW it connects to the rest of the codebase.

Output schema:
{
  "_meta": { "generated": "...", "total_functions": N, "depth": 2 },
  "graph": {
    "process_thumbnail": {
      "file": "thumbnail/processor.py",
      "line": 42,
      "calls": ["encode_frame", "resize_image", "ffmpeg_wrapper"],
      "called_by": ["handle_upload", "batch_process"]
    },
    ...
  }
}

Design decisions:
  - Python: AST-based (accurate — resolves direct function calls in body)
  - TypeScript: regex-based (pragmatic — covers the 80% case without a TS parser)
  - Depth limited to 2 levels (callers + callees) — keeps artifact size manageable
  - Only tracks cross-function calls, not method chain calls on external objects
  - Private functions (leading _) included if called by public ones
"""

import ast
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .base import BaseGenerator
from ..file_index import FileIndex
from ..utils.files import safe_read_text, should_skip_path
from ..utils.formatting import get_timestamp
from ..extractors.go import GoExtractor
from ..extractors.rust import RustExtractor
from ..extractors.csharp import CSharpExtractor


class CallGraphGenerator(BaseGenerator):
    """Generate a 2-level function call graph for the codebase."""

    def __init__(self, root: Path, config: dict, file_index: FileIndex):
        super().__init__(root, config)
        self.index = file_index

    @property
    def output_filename(self) -> str:
        return "call-graph.json"

    def generate(self) -> Tuple[str, List[Path]]:
        # calls[caller] = set of callee names
        calls: Dict[str, Set[str]] = defaultdict(set)
        # meta[name] = {file, line}
        meta: Dict[str, dict] = {}
        source_files: List[Path] = []

        langs = self.index.detect_languages()

        if "python" in langs:
            py_calls, py_meta, py_files = self._extract_python()
            for caller, callees in py_calls.items():
                calls[caller].update(callees)
            meta.update(py_meta)
            source_files.extend(py_files)

        if "typescript" in langs or "javascript" in langs:
            ts_calls, ts_meta, ts_files = self._extract_typescript()
            for caller, callees in ts_calls.items():
                calls[caller].update(callees)
            meta.update(ts_meta)
            source_files.extend(ts_files)

        if "go" in langs:
            go_meta, go_files = self._extract_go_meta()
            meta.update(go_meta)
            source_files.extend(go_files)

        if "rust" in langs:
            rs_meta, rs_files = self._extract_rust_meta()
            meta.update(rs_meta)
            source_files.extend(rs_files)

        if "csharp" in langs:
            cs_meta, cs_files = self._extract_csharp_meta()
            meta.update(cs_meta)
            source_files.extend(cs_files)

        # Build called_by (reverse map)
        called_by: Dict[str, Set[str]] = defaultdict(set)
        for caller, callees in calls.items():
            for callee in callees:
                if callee in meta:  # only track internal calls
                    called_by[callee].add(caller)

        # Assemble output — only include functions that have at least one edge
        graph: Dict[str, dict] = {}
        all_names = set(meta.keys())

        for name in sorted(all_names):
            fn_calls = sorted(c for c in calls.get(name, set()) if c in all_names)
            fn_called_by = sorted(called_by.get(name, set()))

            if not fn_calls and not fn_called_by:
                continue  # isolated — not useful in the graph

            entry = {
                "file": meta[name]["file"],
                "line": meta[name]["line"],
            }
            if fn_calls:
                entry["calls"] = fn_calls
            if fn_called_by:
                entry["called_by"] = fn_called_by

            graph[name] = entry

        output = {
            "_meta": {
                "generated": get_timestamp(),
                "total_functions": len(meta),
                "connected_functions": len(graph),
                "depth": 2,
                "note": (
                    "Shows which functions call which others (2-level depth). "
                    "Only includes functions with at least one internal connection. "
                    "Use with symbol-index.json to trace call paths."
                ),
            },
            "graph": graph,
        }

        return json.dumps(output, indent=2), source_files

    # ── Python ────────────────────────────────────────────────────────────────

    def _extract_python(
        self,
    ) -> Tuple[Dict[str, Set[str]], Dict[str, dict], List[Path]]:
        """
        AST-based extraction for Python.
        Walks each function body and collects Name and Attribute call nodes.
        """
        calls: Dict[str, Set[str]] = defaultdict(set)
        meta: Dict[str, dict] = {}
        source_files: List[Path] = []

        for fi in self.index.by_extension(".py"):
            if should_skip_path(fi.path):
                continue
            content = safe_read_text(fi.path)
            if not content:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue

            source_files.append(fi.path)
            rel = fi.rel_path

            # First pass: collect all function/method names defined in this file
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Use ClassName.method for methods, plain name for top-level
                    qual_name = self._qualify(node, tree, rel)
                    meta[qual_name] = {"file": rel, "line": node.lineno}

            # Second pass: for each function, collect its call targets
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qual_name = self._qualify(node, tree, rel)
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            callee = self._resolve_call_name(child)
                            if callee and callee != qual_name:
                                calls[qual_name].add(callee)

        return calls, meta, source_files

    def _qualify(
        self, func_node: ast.AST, tree: ast.AST, rel_path: str
    ) -> str:
        """Return ClassName.method_name for methods, just method_name for top-level."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if item is func_node:
                        return f"{node.name}.{func_node.name}"
        return func_node.name

    def _resolve_call_name(self, call: ast.Call) -> str:
        """Extract the function name from a Call node."""
        try:
            if isinstance(call.func, ast.Name):
                return call.func.id
            if isinstance(call.func, ast.Attribute):
                # obj.method() — return just the method name
                return call.func.attr
        except Exception:
            pass
        return ""

    # ── TypeScript / JavaScript ───────────────────────────────────────────────

    def _extract_typescript(
        self,
    ) -> Tuple[Dict[str, Set[str]], Dict[str, dict], List[Path]]:
        """
        Regex-based extraction for TypeScript/JavaScript.
        Accurate enough for the 80% case without a full TS parser.
        """
        calls: Dict[str, Set[str]] = defaultdict(set)
        meta: Dict[str, dict] = {}
        source_files: List[Path] = []

        # Patterns to identify function definitions
        fn_def_patterns = [
            # export async function foo(
            re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(", re.MULTILINE),
            # export const foo = async (  or  const foo = (
            re.compile(r"^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\(", re.MULTILINE),
            # foo = async () =>   (arrow method in class)
            re.compile(r"^\s+(?:async\s+)?(\w+)\s*(?:=\s*(?:async\s*)?\(|(?:\([^)]*\))\s*(?::\s*\w+)?\s*\{)", re.MULTILINE),
        ]

        # Pattern to find function calls: word followed by (
        call_pattern = re.compile(r"\b(\w+)\s*\(")

        # Noise words that look like calls but aren't user functions
        BUILTINS = {
            "if", "for", "while", "switch", "catch", "function", "class",
            "return", "typeof", "instanceof", "new", "await", "import",
            "require", "console", "Promise", "Array", "Object", "String",
            "Number", "Boolean", "Math", "JSON", "Date", "Error", "Map",
            "Set", "parseInt", "parseFloat", "setTimeout", "setInterval",
            "clearTimeout", "clearInterval", "fetch", "describe", "it",
            "test", "expect", "beforeEach", "afterEach",
        }

        extensions = [".ts", ".tsx", ".js", ".jsx"]
        for ext in extensions:
            for fi in self.index.by_extension(ext):
                if should_skip_path(fi.path):
                    continue
                if ".spec." in fi.path.name or ".test." in fi.path.name:
                    continue
                content = safe_read_text(fi.path)
                if not content:
                    continue

                source_files.append(fi.path)
                rel = fi.rel_path
                lines = content.splitlines()

                # Find all function definitions
                defined_here: List[Tuple[str, int]] = []
                for pattern in fn_def_patterns:
                    for m in pattern.finditer(content):
                        name = m.group(1)
                        line = content[: m.start()].count("\n") + 1
                        if name and name[0].islower() or name[0].isupper():
                            meta[name] = {"file": rel, "line": line}
                            defined_here.append((name, m.start()))

                # For each function, find its body and extract calls
                # Simple approach: find the function, scan until brace depth returns to 0
                for fn_name, fn_start in defined_here:
                    body = self._extract_ts_body(content, fn_start)
                    for m in call_pattern.finditer(body):
                        callee = m.group(1)
                        if callee not in BUILTINS and callee != fn_name and len(callee) > 1:
                            calls[fn_name].add(callee)

        return calls, meta, source_files

    def _extract_ts_body(self, content: str, fn_start: int) -> str:
        """
        Extract the body of a TS/JS function starting at fn_start.
        Tracks brace depth to find the end of the function.
        Returns at most 200 lines worth of content.
        """
        # Find the opening brace
        brace_start = content.find("{", fn_start)
        if brace_start < 0:
            return ""

        depth = 0
        limit = min(len(content), brace_start + 8000)  # max ~200 lines
        for i in range(brace_start, limit):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    return content[brace_start:i]
        return content[brace_start:limit]

    # ── Go (meta only) ────────────────────────────────────────────────────────

    def _extract_go_meta(self) -> Tuple[Dict[str, dict], List[Path]]:
        """
        Populate function metadata from Go source via GoExtractor.
        Call edges within Go are not traced (would need full parser),
        but Go functions appear in called_by when Python/TS code calls them
        by name — useful in polyglot workspaces.
        """
        extractor = GoExtractor(self.root)
        result = extractor.extract()
        meta: Dict[str, dict] = {}
        for sym in result.symbols:
            if sym.kind in ("function", "method"):
                meta[sym.name] = {"file": sym.file, "line": sym.line}
        return meta, result.source_files

    # ── Rust (meta only) ──────────────────────────────────────────────────────

    def _extract_rust_meta(self) -> Tuple[Dict[str, dict], List[Path]]:
        """
        Populate function metadata from Rust source via RustExtractor.
        Same rationale as Go — edges not traced, meta populated for
        cross-language called_by lookups.
        """
        extractor = RustExtractor(self.root)
        result = extractor.extract()
        meta: Dict[str, dict] = {}
        for sym in result.symbols:
            if sym.kind == "function":
                meta[sym.name] = {"file": sym.file, "line": sym.line}
        return meta, result.source_files

    # ── C# (meta only) ────────────────────────────────────────────────────────

    def _extract_csharp_meta(self) -> Tuple[Dict[str, dict], List[Path]]:
        """Populate function metadata from C# source via CSharpExtractor."""
        extractor = CSharpExtractor(self.root)
        result = extractor.extract()
        meta: Dict[str, dict] = {}
        for sym in result.symbols:
            if sym.kind == "method":
                meta[sym.name] = {"file": sym.file, "line": sym.line}
        return meta, result.source_files
