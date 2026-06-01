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
            "// Types annotated with 'used in:' show cross-file import relationships.",
            "",
        ]
        source_files: List[Path] = []

        # Phase 1: extract all type definitions per file
        type_pattern = re.compile(
            r"^export\s+(?:interface|type|enum|const\s+enum)\s+(\w+)"
            r".*?(?:\{[\s\S]*?\n\}|=\s*[\s\S]*?;)",
            re.MULTILINE,
        )
        type_defined_in: Dict[str, str] = {}
        file_types: Dict[str, List[Tuple[str, str]]] = {}

        for fi in self.index.by_extension(".ts", ".tsx"):
            if ".spec.ts" in fi.path.name or ".test.ts" in fi.path.name:
                continue
            content = safe_read_text(fi.path)
            if not content:
                continue
            matched_types = []
            for m in type_pattern.finditer(content):
                name = m.group(1)
                text = m.group(0).strip()
                type_defined_in[name] = fi.rel_path
                matched_types.append((name, text))
            if matched_types:
                source_files.append(fi.path)
                file_types[fi.rel_path] = matched_types

        # Phase 2: build import graph
        type_used_in: Dict[str, set] = {k: set() for k in type_defined_in}
        import_pattern = re.compile(
            r'import\s+\{([^}]+)\}\s+from\s+[\'"]([^\'"]+)[\'"]' 
        )
        type_name_re = re.compile(r"\b([A-Z]\w+)\b")

        for fi in self.index.by_extension(".ts", ".tsx", ".js", ".jsx"):
            if ".spec." in fi.path.name or ".test." in fi.path.name:
                continue
            content = safe_read_text(fi.path)
            if not content:
                continue
            for m in import_pattern.finditer(content):
                for name_m in type_name_re.finditer(m.group(1)):
                    name = name_m.group(1)
                    if name in type_used_in and fi.rel_path != type_defined_in.get(name):
                        type_used_in[name].add(fi.rel_path)

        # Phase 3: emit annotated output
        for rel_path, type_list in sorted(file_types.items()):
            lines.append(f"\n// -- {rel_path} --")
            for name, text in type_list:
                lines.append(text)
                used = sorted(type_used_in.get(name, set()))
                if used:
                    if len(used) > 5:
                        shown = used[:5]
                        lines.append(f"// used in: {', '.join(shown)} (+{len(used)-5} more)")
                    else:
                        lines.append(f"// used in: {', '.join(used)}")
                lines.append("")

        return "\n".join(lines), source_files

    def generate_type_graph(self) -> str:
        """
        Build type-graph.json — for each TypeScript type, record where it's
        defined and which files import it.

        Output:
        {
          "_meta": { "generated": "...", "total_types": N },
          "types": {
            "VideoConfig": {
              "defined_in": "src/types.ts",
              "kind": "interface",
              "used_in": ["src/encoder.ts", "src/thumbnail.ts"]
            }
          }
        }
        """
        import json
        type_graph: Dict[str, dict] = {}

        # Collect definitions
        type_def_pattern = re.compile(
            r"^export\s+(interface|type|enum|const\s+enum)\s+(\w+)",
            re.MULTILINE,
        )
        type_defined_in: Dict[str, str] = {}
        type_kind: Dict[str, str] = {}

        for fi in self.index.by_extension(".ts", ".tsx"):
            if ".spec." in fi.path.name or ".test." in fi.path.name:
                continue
            content = safe_read_text(fi.path)
            if not content:
                continue
            for m in type_def_pattern.finditer(content):
                kind = m.group(1).strip()
                name = m.group(2)
                type_defined_in[name] = fi.rel_path
                type_kind[name] = "enum" if "enum" in kind else kind

        # Build used_in map
        type_used_in: Dict[str, List[str]] = {k: [] for k in type_defined_in}
        import_pattern = re.compile(
            r"""import\s+\{([^}]+)\}\s+from\s+['"]([^'"]+)['"]"""
        )
        type_name_re = re.compile(r"\b([A-Z]\w+)\b")

        for fi in self.index.by_extension(".ts", ".tsx", ".js", ".jsx"):
            if ".spec." in fi.path.name or ".test." in fi.path.name:
                continue
            content = safe_read_text(fi.path)
            if not content:
                continue
            for m in import_pattern.finditer(content):
                for name_m in type_name_re.finditer(m.group(1)):
                    name = name_m.group(1)
                    if name in type_used_in and fi.rel_path not in type_used_in[name]:
                        if fi.rel_path != type_defined_in.get(name):
                            type_used_in[name].append(fi.rel_path)

        # Assemble output — only types with cross-file relationships
        for name, defined_in in sorted(type_defined_in.items()):
            used = sorted(type_used_in.get(name, []))
            type_graph[name] = {
                "defined_in": defined_in,
                "kind": type_kind.get(name, "type"),
                "used_in": used,
            }

        output = {
            "_meta": {
                "generated": get_timestamp(),
                "total_types": len(type_graph),
                "note": (
                    "TypeScript type cross-reference. "
                    "used_in lists files that explicitly import each type."
                ),
            },
            "types": type_graph,
        }
        return json.dumps(output, indent=2)

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