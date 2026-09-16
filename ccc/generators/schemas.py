"""Schema and type definition generators."""

import ast
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

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

    # ── Shared TypeScript helpers ─────────────────────────────────────────────

    @staticmethod
    def _type_identity(rel_path: str, name: str) -> str:
        """
        Return the canonical repository identity for a TypeScript type.

        Bare type names are not globally unique. A repository can legitimately
        contain multiple types named, for example, Config or Options.
        """
        return f"{rel_path}::{name}"

    @staticmethod
    def _is_test_file(path: Path) -> bool:
        """Return True for common TypeScript/JavaScript test files."""
        name = path.name
        return (
            ".spec." in name
            or ".test." in name
            or name.endswith(".test")
            or name.endswith(".spec")
        )

    def _resolve_ts_import(
        self,
        importer: str,
        import_path: str,
        known_files: Set[str],
    ) -> Optional[str]:
        """
        Resolve a relative TypeScript import to a repository-relative file.

        This deliberately resolves only relative imports. Package aliases,
        node_modules imports, path mappings and bundler-specific aliases are
        left unresolved rather than guessed.
        """
        if not import_path.startswith("."):
            return None

        importer_path = Path(importer)
        base = (importer_path.parent / import_path).as_posix()
        base_path = Path(base)

        candidates = [
            base_path,
            Path(f"{base}.ts"),
            Path(f"{base}.tsx"),
            Path(f"{base}.js"),
            Path(f"{base}.jsx"),
            Path(f"{base}.d.ts"),
            base_path / "index.ts",
            base_path / "index.tsx",
            base_path / "index.js",
            base_path / "index.jsx",
        ]

        for candidate in candidates:
            normalized = candidate.as_posix().lstrip("./")
            if normalized in known_files:
                return normalized

        return None

    @staticmethod
    def _imported_names(import_clause: str) -> Set[str]:
        """
        Extract imported identifiers from a named-import clause.

        Examples:
            "{ Foo, Bar }"             -> {"Foo", "Bar"}
            "{ Foo as Baz }"            -> {"Foo"}
            "{ type Foo, Bar as Baz }"  -> {"Foo", "Bar"}
        """
        names: Set[str] = set()

        for part in import_clause.split(","):
            part = part.strip()

            if not part:
                continue

            # Remove TypeScript's `type` modifier.
            part = re.sub(r"^\s*type\s+", "", part)

            # `Foo as Bar` means the source/exported name is Foo.
            source_name = part.split(" as ", 1)[0].strip()

            # Ignore malformed or non-identifier fragments.
            if re.fullmatch(r"[A-Za-z_$][\w$]*", source_name):
                names.add(source_name)

        return names

    def _collect_typescript_types(
        self,
    ) -> Tuple[
        Dict[str, str],
        Dict[str, str],
        Dict[str, List[Tuple[str, str]]],
        List[Path],
    ]:
        """
        Collect TypeScript type definitions.

        Returns:
            type_defined_in:
                Canonical type identity -> defining file.
            type_kind:
                Canonical type identity -> interface/type/enum.
            file_types:
                File -> extracted (name, source) definitions.
            source_files:
                Files containing extracted definitions.
        """
        type_pattern = re.compile(
            r"^export\s+"
            r"(interface|type|enum|const\s+enum)\s+"
            r"(\w+)"
            r".*?"
            r"(?:\{[\s\S]*?\n\}|=\s*[\s\S]*?;)",
            re.MULTILINE,
        )

        type_defined_in: Dict[str, str] = {}
        type_kind: Dict[str, str] = {}
        file_types: Dict[str, List[Tuple[str, str]]] = {}
        source_files: List[Path] = []

        for fi in self.index.by_extension(".ts", ".tsx"):
            if self._is_test_file(fi.path):
                continue

            content = safe_read_text(fi.path)
            if not content:
                continue

            matched_types: List[Tuple[str, str]] = []

            for match in type_pattern.finditer(content):
                kind = match.group(1).strip()
                name = match.group(2)
                text = match.group(0).strip()

                identity = self._type_identity(fi.rel_path, name)

                type_defined_in[identity] = fi.rel_path
                type_kind[identity] = "enum" if "enum" in kind else kind
                matched_types.append((name, text))

            if matched_types:
                source_files.append(fi.path)
                file_types[fi.rel_path] = matched_types

        return (
            type_defined_in,
            type_kind,
            file_types,
            source_files,
        )

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
                    base.id
                    if isinstance(base, ast.Name)
                    else base.attr
                    if isinstance(base, ast.Attribute)
                    else ""
                    for base in node.bases
                ]

                interesting = {
                    "BaseModel",
                    "BaseSchema",
                    "TypedDict",
                    "Enum",
                    "IntEnum",
                    "StrEnum",
                }

                is_dataclass = any(
                    (
                        isinstance(d, ast.Name)
                        and d.id == "dataclass"
                    )
                    or (
                        isinstance(d, ast.Attribute)
                        and d.attr == "dataclass"
                    )
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

        (
            type_defined_in,
            _type_kind,
            file_types,
            source_files,
        ) = self._collect_typescript_types()

        # All repository source files known to the FileIndex.
        known_files = {
            fi.rel_path
            for fi in self.index.by_extension(
                ".ts",
                ".tsx",
                ".js",
                ".jsx",
            )
        }

        # Canonical identity -> importing files.
        type_used_in: Dict[str, Set[str]] = {
            identity: set()
            for identity in type_defined_in
        }

        # File-local name -> canonical identities.
        #
        # This lets us resolve:
        #   import { Foo } from "./types"
        #
        # against:
        #   src/types.ts::Foo
        #
        # rather than searching globally for every "Foo".
        types_by_file_and_name: Dict[Tuple[str, str], str] = {}

        for identity, defined_in in type_defined_in.items():
            name = identity.rsplit("::", 1)[-1]
            types_by_file_and_name[(defined_in, name)] = identity

        import_pattern = re.compile(
            r'import\s+(?:type\s+)?\{([^}]+)\}'
            r'\s+from\s+[\'"]([^\'"]+)[\'"]'
        )

        for fi in self.index.by_extension(
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
        ):
            if self._is_test_file(fi.path):
                continue

            content = safe_read_text(fi.path)
            if not content:
                continue

            for match in import_pattern.finditer(content):
                imported_names = self._imported_names(match.group(1))
                import_path = match.group(2)

                resolved_file = self._resolve_ts_import(
                    fi.rel_path,
                    import_path,
                    known_files,
                )

                if not resolved_file:
                    # Do not guess package aliases or unresolved paths.
                    continue

                for name in imported_names:
                    identity = types_by_file_and_name.get(
                        (resolved_file, name)
                    )

                    if identity is None:
                        continue

                    if fi.rel_path != resolved_file:
                        type_used_in[identity].add(fi.rel_path)

        # Emit definitions grouped by source file.
        for rel_path, type_list in sorted(file_types.items()):
            lines.append(f"\n// -- {rel_path} --")

            for name, text in type_list:
                identity = self._type_identity(rel_path, name)

                lines.append(text)

                used = sorted(type_used_in.get(identity, set()))

                if used:
                    if len(used) > 5:
                        shown = used[:5]
                        lines.append(
                            f"// used in: {', '.join(shown)} "
                            f"(+{len(used) - 5} more)"
                        )
                    else:
                        lines.append(
                            f"// used in: {', '.join(used)}"
                        )

                lines.append("")

        return "\n".join(lines), source_files

    def generate_type_graph(self) -> str:
        """
        Build type-graph.json.

        Each TypeScript type receives a canonical source-qualified identity:

            src/types.ts::VideoConfig

        This prevents duplicate type names in different files from
        overwriting one another.

        Output:
        {
          "_meta": {
            "generated": "...",
            "total_types": N
          },
          "types": {
            "src/types.ts::VideoConfig": {
              "name": "VideoConfig",
              "defined_in": "src/types.ts",
              "kind": "interface",
              "used_in": [
                "src/encoder.ts",
                "src/thumbnail.ts"
              ]
            }
          }
        }
        """
        (
            type_defined_in,
            type_kind,
            _file_types,
            _source_files,
        ) = self._collect_typescript_types()

        # All source files available for deterministic relative-import
        # resolution.
        known_files = {
            fi.rel_path
            for fi in self.index.by_extension(
                ".ts",
                ".tsx",
                ".js",
                ".jsx",
            )
        }

        # File/name -> canonical type identity.
        types_by_file_and_name: Dict[Tuple[str, str], str] = {}

        for identity, defined_in in type_defined_in.items():
            name = identity.rsplit("::", 1)[-1]
            types_by_file_and_name[(defined_in, name)] = identity

        # Canonical identity -> files importing that exact type.
        type_used_in: Dict[str, Set[str]] = {
            identity: set()
            for identity in type_defined_in
        }

        import_pattern = re.compile(
            r"""import\s+(?:type\s+)?\{([^}]+)\}
            \s+from\s+['"]([^'"]+)['"]""",
            re.MULTILINE | re.VERBOSE,
        )

        for fi in self.index.by_extension(
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
        ):
            if self._is_test_file(fi.path):
                continue

            content = safe_read_text(fi.path)
            if not content:
                continue

            for match in import_pattern.finditer(content):
                imported_names = self._imported_names(match.group(1))
                import_path = match.group(2)

                resolved_file = self._resolve_ts_import(
                    fi.rel_path,
                    import_path,
                    known_files,
                )

                if not resolved_file:
                    continue

                for name in imported_names:
                    identity = types_by_file_and_name.get(
                        (resolved_file, name)
                    )

                    if identity is None:
                        continue

                    if fi.rel_path != resolved_file:
                        type_used_in[identity].add(fi.rel_path)

        type_graph: Dict[str, dict] = {}

        # Assemble output. Every discovered type is retained, including types
        # with no cross-file relationships.
        for identity in sorted(type_defined_in):
            defined_in = type_defined_in[identity]
            name = identity.rsplit("::", 1)[-1]

            type_graph[identity] = {
                "name": name,
                "defined_in": defined_in,
                "kind": type_kind.get(identity, "type"),
                "used_in": sorted(type_used_in.get(identity, set())),
            }

        output = {
            "_meta": {
                "generated": get_timestamp(),
                "total_types": len(type_graph),
                "note": (
                    "TypeScript type cross-reference. "
                    "used_in lists files that explicitly import each type "
                    "through a resolvable relative import."
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
            r"(?:#\[derive\(.*?\)\]\s*)?"
            r"pub\s+(?:struct|enum|trait)\s+\w+"
            r"[\s\S]*?\n\}",
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

                for match in matches:
                    lines.append(match.strip())
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
            r"type\s+\w+\s+"
            r"(?:struct|interface)\s*\{[\s\S]*?\n\}",
            re.MULTILINE,
        )

        for fi in self.index.by_extension(".go"):
            if fi.path.name.endswith("_test.go"):
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

    # ── C# ────────────────────────────────────────────────────────────────────

    def _extract_csharp(self) -> Tuple[str, List[Path]]:
        lines = [
            "// Auto-extracted C# type definitions",
            f"// Generated: {get_timestamp()}",
            "",
        ]
        source_files: List[Path] = []

        pattern = re.compile(
            r"public\s+"
            r"(?:sealed\s+|abstract\s+|partial\s+|static\s+)*"
            r"(?:class|record|enum|interface|struct)\s+\w+"
            r"[\s\S]*?\n\}",
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

                for match in matches:
                    lines.append(match.strip())
                    lines.append("")

        return "\n".join(lines), source_files
