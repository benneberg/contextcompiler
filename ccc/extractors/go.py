"""
Go language extractor.

Extracts from Go source using regex (no external parser required):
  - Exported function signatures (capitalised names)
  - Struct and interface type definitions
  - HTTP route registrations (net/http, gin, fiber, echo, chi patterns)
  - go.mod module name and direct dependencies

Design: Go's syntax is regular enough that regex extraction is reliable
for the public surface. We skip unexported (lowercase) functions since
those are implementation details the LLM rarely needs.
"""

import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .base import BaseExtractor, ExtractionResult, ExtractedSymbol
from ..utils.files import safe_read_text, should_skip_path


# ── Patterns ──────────────────────────────────────────────────────────────────

# Exported function: func FunctionName( or func (recv ReceiverType) MethodName(
_FN_EXPORTED = re.compile(
    r"^func\s+(?:\(\w+\s+\*?(\w+)\)\s+)?([A-Z]\w*)\s*\(([^)]*)\)\s*([^{]*)",
    re.MULTILINE,
)

# Struct definition: type FooBar struct {
_STRUCT = re.compile(r"^type\s+([A-Z]\w*)\s+struct\s*\{", re.MULTILINE)

# Interface definition: type Fooer interface {
_INTERFACE = re.compile(r"^type\s+([A-Z]\w*)\s+interface\s*\{", re.MULTILINE)

# Type alias: type MyType = OtherType  or  type MyType OtherType
_TYPE_ALIAS = re.compile(r"^type\s+([A-Z]\w*)\s+(?!=struct|interface)(\w+)", re.MULTILINE)

# HTTP route patterns for common frameworks
_ROUTES: List[Tuple[str, re.Pattern]] = [
    # Standard net/http:  http.HandleFunc("/path", handler)
    ("net/http", re.compile(
        r'http\.HandleFunc\s*\(\s*"(/[^"]*)"', re.MULTILINE
    )),
    # Gin:  r.GET("/path", handler)  or  router.POST("/path", handler)
    ("gin", re.compile(
        r'\.\s*(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s*\(\s*"(/[^"]*)"',
        re.MULTILINE | re.IGNORECASE,
    )),
    # Fiber / Echo / Chi — same pattern as Gin
    ("fiber/echo/chi", re.compile(
        r'\.\s*(Get|Post|Put|Delete|Patch|Options|Head|All)\s*\(\s*"(/[^"]*)"',
        re.MULTILINE,
    )),
    # gorilla/mux:  r.HandleFunc("/path", handler).Methods("GET")
    ("gorilla/mux", re.compile(
        r'HandleFunc\s*\(\s*"(/[^"]*)"', re.MULTILINE
    )),
]

# Imports block: single or multi-line
_IMPORT_SINGLE = re.compile(r'^import\s+"([^"]+)"', re.MULTILINE)
_IMPORT_BLOCK = re.compile(r'import\s*\(([^)]+)\)', re.DOTALL)
_IMPORT_LINE = re.compile(r'"([^"]+)"')


class GoExtractor(BaseExtractor):
    """Extract symbols, routes, types, and imports from Go source files."""

    @property
    def file_patterns(self) -> List[str]:
        return ["*.go"]

    @property
    def language_name(self) -> str:
        return "go"

    def extract(self) -> ExtractionResult:
        result = ExtractionResult()

        for go_file in self.root.rglob("*.go"):
            if should_skip_path(go_file):
                continue
            # Skip test files for symbol extraction (keep for coverage)
            if go_file.name.endswith("_test.go"):
                continue
            content = safe_read_text(go_file)
            if not content:
                continue
            result.source_files.append(go_file)
            self._extract_from_file(go_file, content, result)

        # Parse go.mod for module name and dependencies
        self._parse_go_mod(result)

        return result

    def _extract_from_file(
        self, filepath: Path, content: str, result: ExtractionResult
    ) -> None:
        rel = str(filepath.relative_to(self.root))

        # ── Symbols: exported functions and methods ──────────────────────────
        for m in _FN_EXPORTED.finditer(content):
            receiver_type = m.group(1)  # e.g. "Handler" in (h *Handler)
            fn_name = m.group(2)
            params = m.group(3).strip()
            returns = m.group(4).strip()

            if receiver_type:
                name = f"{receiver_type}.{fn_name}"
            else:
                name = fn_name

            sig = f"func {name}({params})"
            if returns:
                sig += f" {returns}"

            line = content[: m.start()].count("\n") + 1
            result.symbols.append(ExtractedSymbol(
                name=name,
                kind="method" if receiver_type else "function",
                file=rel,
                line=line,
                signature=sig,
            ))

        # ── Types: structs and interfaces ────────────────────────────────────
        for m in _STRUCT.finditer(content):
            name = m.group(1)
            line = content[: m.start()].count("\n") + 1
            result.symbols.append(ExtractedSymbol(
                name=name, kind="struct", file=rel, line=line,
            ))
            result.types.append({"name": name, "file": rel, "line": line, "kind": "struct"})

        for m in _INTERFACE.finditer(content):
            name = m.group(1)
            line = content[: m.start()].count("\n") + 1
            result.symbols.append(ExtractedSymbol(
                name=name, kind="interface", file=rel, line=line,
            ))
            result.types.append({"name": name, "file": rel, "line": line, "kind": "interface"})

        # ── Routes ────────────────────────────────────────────────────────────
        for framework, pattern in _ROUTES:
            for m in pattern.finditer(content):
                groups = m.groups()
                if len(groups) == 2:
                    method, path = groups[0].upper(), groups[1]
                else:
                    method, path = "GET", groups[0]
                line = content[: m.start()].count("\n") + 1
                result.routes.append({
                    "method": method,
                    "path": path,
                    "file": rel,
                    "line": line,
                    "framework": framework,
                })

        # ── Imports ───────────────────────────────────────────────────────────
        imports: Set[str] = set()
        for m in _IMPORT_SINGLE.finditer(content):
            imports.add(m.group(1))
        for block in _IMPORT_BLOCK.finditer(content):
            for imp in _IMPORT_LINE.finditer(block.group(1)):
                imports.add(imp.group(1))

        # Filter to external (non-stdlib) imports — stdlib has no dots in first segment
        ext_imports = [
            imp for imp in imports
            if "/" in imp and not imp.startswith("golang.org/x/")
            or "." in imp.split("/")[0]
        ]
        if ext_imports:
            result.imports[rel] = sorted(ext_imports)

    def _parse_go_mod(self, result: ExtractionResult) -> None:
        """Parse go.mod to extract module name and direct dependencies."""
        go_mod = self.root / "go.mod"
        if not go_mod.exists():
            return

        content = safe_read_text(go_mod)
        if not content:
            return

        # Module name
        m = re.search(r"^module\s+(\S+)", content, re.MULTILINE)
        if m:
            result.external_calls.append(f"go-module: {m.group(1)}")

        # Direct requires (not indirect)
        in_require = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("require ("):
                in_require = True
                continue
            if in_require and stripped == ")":
                in_require = False
                continue
            if in_require and stripped and not stripped.startswith("//"):
                if "// indirect" not in stripped:
                    parts = stripped.split()
                    if parts:
                        result.external_calls.append(f"go-dep: {parts[0]}")
            elif stripped.startswith("require ") and "// indirect" not in stripped:
                parts = stripped.replace("require ", "").split()
                if parts:
                    result.external_calls.append(f"go-dep: {parts[0]}")
