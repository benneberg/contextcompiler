"""Schema and type definition generators."""
import ast
import re
from pathlib import Path
from typing import Dict, List, Tuple

from .base import BaseGenerator
from ..file_index import FileIndex
from ..utils.files import safe_read_text
from ..utils.formatting import get_timestamp


class SchemaGenerator(BaseGenerator):
    """Generate schema/type extraction files for all detected languages."""

    def __init__(self, root: Path, config: dict, file_index: FileIndex):
        super().__init__(root, config)
        self.index = file_index

    @property
    def output_filename(self) -> str:
        return "schemas-extracted.py"

    def generate(self) -> Tuple[str, List[Path]]:
        results = self.generate_all()
        if "schemas-extracted.py" in results:
            return results["schemas-extracted.py"]
        for content, sources in results.values():
            return content, sources
        return "", []

    def generate_all(self) -> Dict[str, Tuple[str, List[Path]]]:
        """Generate schema files for every language present in the index."""
        results = {}

        langs = self.index.detect_languages()

        if "python" in langs:
            content, sources = self._extract_python()
            if content.strip():
                results["schemas-extracted.py"] = (content, sources)

        if "typescript" in langs:
            content, sources = self._extract_typescript()
            if content.strip():
                results["types-extracted.ts"] = (content, sources)

        if "rust" in langs:
            content, sources = self._extract_rust()
            if content.strip():
                results["rust-types.rs"] = (content, sources)

        if "go" in langs:
            content, sources = self._extract_go()
            if content.strip():
                results["go-types.go"] = (content, sources)

        if "csharp" in langs:
            content, sources = self._extract_csharp()
            if content.strip():
                results["csharp-types.cs"] = (content, sources)

        return results

    # ── Python ────────────────────────────────────────────────────────────────

    def _extract_python(self) -> Tuple[str, List[Path]]:
        lines = [
            "# Auto-extracted Python type definitions",
            f"# Generated: {get_timestamp()}",
            "",
        ]
        source_files: List[Path] = []

        for fi in self.index.by_extension(".py"):
            content = safe_read_text(fi.path)
            if not content:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue

            classes_in_file = []
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue

                base_names = [
                    base.id if isinstance(base, ast.Name)
                    else base.attr if isinstance(base, ast.Attribute)
                    else ""
                    for base in node.bases
                ]

                interesting = {
                    "BaseModel", "BaseSchema", "TypedDict",
                    "Enum", "IntEnum", "StrEnum",
                }
                is_dataclass = any(
                    (isinstance(d, ast.Name) and d.id == "dataclass") or
                    (isinstance(d, ast.Attribute) and d.attr == "dataclass")
                    for d in node.decorator_list
                )

                if set(base_names) & interesting or is_dataclass:
                    start = node.lineno - 1
                    end = getattr(node, "end_lineno", start + 1)
                    src_lines = content.split("\n")[start:end]
                    classes_in_file.append("\n".join(src_lines))

            if classes_in_file:
                source_files.append(fi.path)
                lines.append(f"\n# -- {fi.rel_path} --")
                lines.extend(classes_in_file)
                lines.append("")

        return "\n".join(lines), source_files

    # ── TypeScript ────────────────────────────────────────────────────────────

    def _extract_typescript(self) -> Tuple[str, List[Path]]:
        lines = [
            "// Auto-extracted TypeScript type definitions",
            f"// Generated: {get_timestamp()}",
            "",
        ]
        source_files: List[Path] = []

        pattern = re.compile(
            r"^export\s+(?:interface|type|enum|const\s+enum)\s+.*?"
            r"(?:\{[\s\S]*?\n\}|=\s*[\s\S]*?;)",
            re.MULTILINE,
        )

        for fi in self.index.by_extension(".ts", ".tsx"):
            if ".spec.ts" in fi.path.name or ".test.ts" in fi.path.name:
                continue
            content = safe_read_text(fi.path)
            if not content:
                continue
            matches = pattern.findall(content)
            if matches:
                source_files.append(fi.path)
                lines.append(f"\n// -- {fi.rel_path} --")
                for match in matches:
                    lines.append(match.strip())
                    lines.append("")

        return "\n".join(lines), source_files

    # ── Rust ──────────────────────────────────────────────────────────────────

    def _extract_rust(self) -> Tuple[str, List[Path]]:
        lines = [
            "// Auto-extracted Rust type definitions",
            f"// Generated: {get_timestamp()}",
            "",
        ]
        source_files: List[Path] = []
        pattern = re.compile(
            r"(?:#\[derive\(.*?\)\]\s*)?pub\s+(?:struct|enum|trait)\s+\w+[\s\S]*?\n\}",
            re.MULTILINE,
        )
        for fi in self.index.by_extension(".rs"):
            content = safe_read_text(fi.path)
            if not content:
                continue
            matches = pattern.findall(content)
            if matches:
                source_files.append(fi.path)
                lines.append(f"\n// -- {fi.rel_path} --")
                for m in matches:
                    lines.append(m.strip())
                    lines.append("")
        return "\n".join(lines), source_files

    # ── Go ────────────────────────────────────────────────────────────────────

    def _extract_go(self) -> Tuple[str, List[Path]]:
        lines = [
            "// Auto-extracted Go type definitions",
            f"// Generated: {get_timestamp()}",
            "",
        ]
        source_files: List[Path] = []
        pattern = re.compile(
            r"type\s+\w+\s+(?:struct|interface)\s*\{[\s\S]*?\n\}",
            re.MULTILINE,
        )
        for fi in self.index.by_extension(".go"):
            if "_test.go" in fi.path.name:
                continue
            content = safe_read_text(fi.path)
            if not content:
                continue
            matches = pattern.findall(content)
            if matches:
                source_files.append(fi.path)
                lines.append(f"\n// -- {fi.rel_path} --")
                for m in matches:
                    lines.append(m.strip())
                    lines.append("")
        return "\n".join(lines), source_files

    # ── C# ────────────────────────────────────────────────────────────────────

    def _extract_csharp(self) -> Tuple[str, List[Path]]:
        lines = [
            "// Auto-extracted C# type definitions",
            f"// Generated: {get_timestamp()}",
            "",
        ]
        source_files: List[Path] = []
        pattern = re.compile(
            r"public\s+(?:sealed\s+|abstract\s+|partial\s+|static\s+)*"
            r"(?:class|record|enum|interface|struct)\s+\w+[\s\S]*?\n\}",
            re.MULTILINE,
        )
        for fi in self.index.by_extension(".cs"):
            content = safe_read_text(fi.path)
            if not content:
                continue
            matches = pattern.findall(content)
            if matches:
                source_files.append(fi.path)
                lines.append(f"\n// -- {fi.rel_path} --")
                for m in matches:
                    lines.append(m.strip())
                    lines.append("")
        return "\n".join(lines), source_files