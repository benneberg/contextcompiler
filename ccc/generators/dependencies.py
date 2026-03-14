"""Dependency graph generators."""
import re
from pathlib import Path
from typing import Dict, List, Tuple

from .base import BaseGenerator
from ..file_index import FileIndex
from ..utils.files import safe_read_text
from ..utils.formatting import get_timestamp


class DependencyGenerator(BaseGenerator):
    """Analyze internal import relationships and generate dependency graphs."""

    def __init__(self, root: Path, config: dict, file_index: FileIndex):
        super().__init__(root, config)
        self.index = file_index

    @property
    def output_filename(self) -> str:
        return "dependency-graph.txt"

    def generate(self) -> Tuple[str, List[Path]]:
        lines = [
            "# Internal Dependency Graph",
            f"# Generated: {get_timestamp()}",
            "",
        ]
        source_files: List[Path] = []

        langs = self.index.detect_languages()

        if "python" in langs:
            py_lines, py_files = self._analyze_python()
            lines.extend(py_lines)
            source_files.extend(py_files)

        if "typescript" in langs or "javascript" in langs:
            js_lines, js_files = self._analyze_js()
            lines.extend(js_lines)
            source_files.extend(js_files)

        return "\n".join(lines), source_files

    def generate_mermaid(self, dependency_text: str) -> str:
        """Convert dependency text to a Mermaid diagram."""
        lines = ["# Dependency Graph Visualization", "", "```mermaid", "graph LR"]
        current_file = None
        edges = []
        for line in dependency_text.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("##"):
                continue
            if stripped.startswith("->"):
                dep = stripped[2:].strip()
                if current_file and dep:
                    edges.append((current_file, dep))
            else:
                current_file = stripped

        def sanitize(name: str) -> str:
            return re.sub(r"[/.\-]", "_", name)

        seen: set = set()
        for source, target in edges:
            edge = f"{sanitize(source)} --> {sanitize(target)}"
            if edge not in seen:
                lines.append(f"  {edge}")
                seen.add(edge)

        lines.append("```")
        return "\n".join(lines)

    # ── Python ────────────────────────────────────────────────────────────────

    def _analyze_python(self) -> Tuple[List[str], List[Path]]:
        lines = ["## Python Imports", ""]
        source_files: List[Path] = []
        import_pattern = re.compile(
            r"^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
            re.MULTILINE,
        )
        # Detect likely package root
        candidates = ["src", "app", "lib", self.root.name]
        package_root = next(
            (d for d in candidates if (self.root / d).is_dir()), ""
        )

        graph: Dict[str, List[str]] = {}
        for fi in self.index.by_extension(".py"):
            content = safe_read_text(fi.path)
            if not content:
                continue
            source_files.append(fi.path)
            imports = []
            for match in import_pattern.finditer(content):
                module = match.group(1) or match.group(2)
                if package_root and module.startswith(package_root):
                    imports.append(module)
                elif module.startswith("."):
                    imports.append(module)
            if imports:
                graph[fi.rel_path] = imports

        for file_path, imports in sorted(graph.items()):
            lines.append(file_path)
            for imp in imports:
                lines.append(f"  -> {imp}")
            lines.append("")

        return lines, source_files

    # ── JavaScript / TypeScript ───────────────────────────────────────────────

    def _analyze_js(self) -> Tuple[List[str], List[Path]]:
        lines = ["## JavaScript/TypeScript Imports", ""]
        source_files: List[Path] = []
        import_pattern = re.compile(
            r"""(?:import|require)\s*\(?['"](\.+[^'"]+)['"]\)?""",
            re.MULTILINE,
        )
        graph: Dict[str, List[str]] = {}
        for fi in self.index.by_extension(".js", ".ts", ".jsx", ".tsx"):
            content = safe_read_text(fi.path)
            if not content:
                continue
            source_files.append(fi.path)
            imports = import_pattern.findall(content)
            if imports:
                graph[fi.rel_path] = imports

        for file_path, imports in sorted(graph.items()):
            lines.append(file_path)
            for imp in imports:
                lines.append(f"  -> {imp}")
            lines.append("")

        return lines, source_files
