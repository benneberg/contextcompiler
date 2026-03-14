"""API route and public function signature generators."""
import ast
import re
from pathlib import Path
from typing import List, Tuple

from .base import BaseGenerator
from ..file_index import FileIndex
from ..utils.files import safe_read_text
from ..utils.formatting import get_timestamp


class APIGenerator(BaseGenerator):
    """Extract API routes and public function signatures."""

    def __init__(self, root: Path, config: dict, file_index: FileIndex, framework: str = ""):
        super().__init__(root, config)
        self.index = file_index
        self.framework = framework

    @property
    def output_filename(self) -> str:
        return "routes.txt"

    def generate(self) -> Tuple[str, List[Path]]:
        return self.generate_routes()

    def generate_routes(self) -> Tuple[str, List[Path]]:
        lines = [
            "# API Routes",
            f"# Generated: {get_timestamp()}",
            "",
        ]
        source_files: List[Path] = []

        py_lines, py_files = self._extract_python_routes()
        lines.extend(py_lines)
        source_files.extend(py_files)

        js_lines, js_files = self._extract_js_routes()
        lines.extend(js_lines)
        source_files.extend(js_files)

        if len(lines) <= 3:
            return "", []

        return "\n".join(lines), source_files

    def generate_public_api(self) -> Tuple[str, List[Path]]:
        lines = [
            "# Public API (function signatures)",
            f"# Generated: {get_timestamp()}",
            "",
        ]
        source_files: List[Path] = []

        py_lines, py_files = self._extract_python_signatures()
        lines.extend(py_lines)
        source_files.extend(py_files)

        ts_lines, ts_files = self._extract_ts_signatures()
        lines.extend(ts_lines)
        source_files.extend(ts_files)

        return "\n".join(lines), source_files

    # ── Python routes ─────────────────────────────────────────────────────────

    def _extract_python_routes(self) -> Tuple[List[str], List[Path]]:
        lines: List[str] = []
        source_files: List[Path] = []
        route_pattern = re.compile(
            r"@(?:app|router|api)\.(get|post|put|patch|delete|head|options|websocket)"
            r'\s*\(\s*["\']([^"\']*)["\']'
        )
        for fi in self.index.by_extension(".py"):
            content = safe_read_text(fi.path)
            if not content:
                continue
            matches = route_pattern.findall(content)
            if matches:
                source_files.append(fi.path)
                lines.append(f"\n## {fi.rel_path}")
                for method, path in matches:
                    lines.append(f"  {method.upper():8s} {path}")
        return lines, source_files

    # ── JS/TS routes ──────────────────────────────────────────────────────────

    def _extract_js_routes(self) -> Tuple[List[str], List[Path]]:
        lines: List[str] = []
        source_files: List[Path] = []
        route_pattern = re.compile(
            r"(?:app|router|server)\.(get|post|put|patch|delete)"
            r'\s*\(\s*["\'/]([^"\']*)["\']'
        )
        for fi in self.index.by_extension(".js", ".ts", ".jsx", ".tsx"):
            content = safe_read_text(fi.path)
            if not content:
                continue
            matches = route_pattern.findall(content)
            if matches:
                source_files.append(fi.path)
                lines.append(f"\n## {fi.rel_path}")
                for method, path in matches:
                    lines.append(f"  {method.upper():8s} {path}")
        return lines, source_files

    # ── Python signatures ─────────────────────────────────────────────────────

    def _extract_python_signatures(self) -> Tuple[List[str], List[Path]]:
        lines: List[str] = []
        source_files: List[Path] = []
        for fi in self.index.by_extension(".py"):
            content = safe_read_text(fi.path)
            if not content:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            sigs = []
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("_"):
                        sigs.append(self._format_python_sig(node, ""))
                elif isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if not item.name.startswith("_") or item.name == "__init__":
                                sigs.append(self._format_python_sig(item, node.name))
            if sigs:
                source_files.append(fi.path)
                lines.append(f"\n## {fi.rel_path}")
                lines.extend(sigs)
        return lines, source_files

    def _format_python_sig(self, node: ast.AST, class_name: str) -> str:
        prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
        name = f"{class_name}.{node.name}" if class_name else node.name
        args = []
        for arg in node.args.args:
            if arg.arg == "self":
                continue
            annotation = ""
            if arg.annotation:
                try:
                    annotation = f": {ast.unparse(arg.annotation)}"
                except Exception:
                    pass
            args.append(f"{arg.arg}{annotation}")
        returns = ""
        if node.returns:
            try:
                returns = f" -> {ast.unparse(node.returns)}"
            except Exception:
                pass
        return f"  {prefix}def {name}({', '.join(args)}){returns}"

    # ── TypeScript signatures ─────────────────────────────────────────────────

    def _extract_ts_signatures(self) -> Tuple[List[str], List[Path]]:
        lines: List[str] = []
        source_files: List[Path] = []
        pattern = re.compile(
            r"^export\s+(?:async\s+)?function\s+(\w+)\s*"
            r"\(([^)]*)\)\s*(?::\s*([^\{]*))?",
            re.MULTILINE,
        )
        for fi in self.index.by_extension(".ts", ".tsx"):
            content = safe_read_text(fi.path)
            if not content:
                continue
            matches = pattern.findall(content)
            if matches:
                source_files.append(fi.path)
                lines.append(f"\n## {fi.rel_path}")
                for name, params, return_type in matches:
                    ret = f": {return_type.strip()}" if return_type and return_type.strip() else ""
                    lines.append(f"  function {name}({params}){ret}")
        return lines, source_files