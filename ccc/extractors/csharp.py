"""C# language extractor.

Extracts useful public API information from C# source without requiring
an external C# parser:

- Public classes, interfaces, records, and enums
- Public methods
- ASP.NET Core attribute routes
- ASP.NET Core Minimal API routes
- External using namespaces
- .csproj assembly name and PackageReference dependencies

This is intentionally regex-based so the core package has no C# parser
dependency.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Set

from .base import BaseExtractor, ExtractionResult, ExtractedSymbol
from ..utils.files import safe_read_text, should_skip_path


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# public class Foo
_PUBLIC_CLASS = re.compile(
    r"\bpublic\s+(?:sealed\s+|abstract\s+|partial\s+)*class\s+(\w+)",
    re.MULTILINE,
)

# public interface IFoo
_PUBLIC_INTERFACE = re.compile(
    r"\bpublic\s+(?:partial\s+)?interface\s+(\w+)",
    re.MULTILINE,
)

# public record Foo / public record class Foo / public record struct Foo
_PUBLIC_RECORD = re.compile(
    r"\bpublic\s+record(?:\s+(?:class|struct))?\s+(\w+)",
    re.MULTILINE,
)

# public enum Foo
_PUBLIC_ENUM = re.compile(
    r"\bpublic\s+enum\s+(\w+)",
    re.MULTILINE,
)

# public async Task<Foo> GetSomething(...)
# public IActionResult GetSomething(...)
# public void Foo(...)
#
# We deliberately require "public" so private/internal/protected methods
# aren't extracted.
_PUBLIC_METHOD = re.compile(
    r"""
    \bpublic
    \s+
    (?:
        static\s+
    |   async\s+
    |   virtual\s+
    |   override\s+
    |   sealed\s+
    |   abstract\s+
    |   partial\s+
    )*
    (?:
        [\w<>\[\],.?]+\s+
    )+
    (\w+)
    \s*
    \(
        ([^)]*)
    \)
    """,
    re.MULTILINE | re.VERBOSE,
)

# using Foo.Bar;
_USING = re.compile(
    r"^\s*using\s+(?!static\s+)([\w.]+)\s*;",
    re.MULTILINE,
)

# [HttpGet]
# [HttpGet("{id}")]
# [HttpPost]
# [HttpDelete("{id}")]
_ATTRIBUTE_ROUTE = re.compile(
    r"""
    \[\s*
    Http
    (Get|Post|Put|Delete|Patch|Head|Options)
    (?:\s*\(\s*"([^"]*)"\s*\))?
    \s*\]
    """,
    re.MULTILINE | re.IGNORECASE | re.VERBOSE,
)

# app.MapGet("/path", ...)
# app.MapPost("/path", ...)
_MINIMAL_API_ROUTE = re.compile(
    r"""
    \.\s*
    Map
    (Get|Post|Put|Delete|Patch|Head|Options)
    \s*
    \(
        \s*"([^"]+)"
    """,
    re.MULTILINE | re.IGNORECASE | re.VERBOSE,
)

# [Route("api/[controller]")]
_CONTROLLER_ROUTE = re.compile(
    r'\[\s*Route\s*\(\s*"([^"]+)"\s*\)\s*\]',
    re.MULTILINE | re.IGNORECASE,
)


class CSharpExtractor(BaseExtractor):
    """Extract symbols, routes, imports, and project metadata from C#."""

    @property
    def file_patterns(self) -> List[str]:
        return ["*.cs"]

    @property
    def language_name(self) -> str:
        return "csharp"

    def extract(self) -> ExtractionResult:
        result = ExtractionResult()

        for cs_file in self.root.rglob("*.cs"):
            if should_skip_path(cs_file):
                continue

            if self._is_generated_file(cs_file):
                continue

            content = safe_read_text(cs_file)
            if not content:
                continue

            result.source_files.append(cs_file)
            self._extract_from_file(cs_file, content, result)

        self._parse_csproj(result)

        return result

    # -----------------------------------------------------------------------
    # Generated files
    # -----------------------------------------------------------------------

    def _is_generated_file(self, filepath: Path) -> bool:
        """Return True for common generated C# source files."""
        name = filepath.name.lower()

        return (
            name.endswith(".designer.cs")
            or name.endswith(".generated.cs")
            or name.endswith(".g.cs")
            or name.endswith(".g.i.cs")
        )

    # -----------------------------------------------------------------------
    # Source extraction
    # -----------------------------------------------------------------------

    def _extract_from_file(
        self,
        filepath: Path,
        content: str,
        result: ExtractionResult,
    ) -> None:
        rel = str(filepath.relative_to(self.root))

        self._extract_types(filepath, rel, content, result)
        self._extract_methods(rel, content, result)
        self._extract_attribute_routes(rel, content, result)
        self._extract_minimal_api_routes(rel, content, result)
        self._extract_usings(rel, content, result)

    def _extract_types(
        self,
        filepath: Path,
        rel: str,
        content: str,
        result: ExtractionResult,
    ) -> None:
        patterns = [
            (_PUBLIC_CLASS, "class"),
            (_PUBLIC_INTERFACE, "interface"),
            (_PUBLIC_RECORD, "record"),
            (_PUBLIC_ENUM, "enum"),
        ]

        for pattern, kind in patterns:
            for match in pattern.finditer(content):
                name = match.group(1)
                line = content[: match.start()].count("\n") + 1

                result.symbols.append(
                    ExtractedSymbol(
                        name=name,
                        kind=kind,
                        file=rel,
                        line=line,
                    )
                )

                # The tests expect classes and interfaces in result.types.
                if kind in {"class", "interface"}:
                    result.types.append(
                        {
                            "name": name,
                            "file": rel,
                            "line": line,
                            "kind": kind,
                        }
                    )

    def _extract_methods(
        self,
        rel: str,
        content: str,
        result: ExtractionResult,
    ) -> None:
        for match in _PUBLIC_METHOD.finditer(content):
            name = match.group(1)
            params = (match.group(2) or "").strip()
            line = content[: match.start()].count("\n") + 1

            # Avoid treating constructors as methods.
            # A constructor has the same name as its containing class.
            if self._looks_like_constructor(content, match, name):
                continue

            signature = f"public {name}({params})"

            result.symbols.append(
                ExtractedSymbol(
                    name=name,
                    kind="method",
                    file=rel,
                    line=line,
                    signature=signature,
                )
            )

    def _looks_like_constructor(
        self,
        content: str,
        match: re.Match[str],
        name: str,
    ) -> bool:
        """Best-effort constructor detection.

        Constructors don't have a return type. Our method regex generally
        avoids them, but this extra check keeps extraction conservative.
        """
        before = content[: match.start()]

        # Find the most recent class declaration.
        classes = list(_PUBLIC_CLASS.finditer(before))
        if not classes:
            return False

        current_class = classes[-1].group(1)
        return current_class == name

    # -----------------------------------------------------------------------
    # ASP.NET Core attribute routes
    # -----------------------------------------------------------------------

    def _extract_attribute_routes(
        self,
        rel: str,
        content: str,
        result: ExtractionResult,
    ) -> None:
        controller_match = _CONTROLLER_ROUTE.search(content)
        controller_prefix = ""

        if controller_match:
            controller_prefix = controller_match.group(1).strip("/")

        for match in _ATTRIBUTE_ROUTE.finditer(content):
            method = match.group(1).upper()
            path = match.group(2) or ""

            # Attribute routes without a path are still valid routes.
            if path:
                if controller_prefix:
                    path = (
                        "/" + controller_prefix.strip("/") +
                        "/" + path.strip("/")
                    )
                else:
                    path = "/" + path.strip("/")
            elif controller_prefix:
                path = "/" + controller_prefix.strip("/")

            line = content[: match.start()].count("\n") + 1

            result.routes.append(
                {
                    "method": method,
                    "path": path,
                    "file": rel,
                    "line": line,
                    "framework": "aspnet-core",
                }
            )

    # -----------------------------------------------------------------------
    # ASP.NET Core Minimal APIs
    # -----------------------------------------------------------------------

    def _extract_minimal_api_routes(
        self,
        rel: str,
        content: str,
        result: ExtractionResult,
    ) -> None:
        for match in _MINIMAL_API_ROUTE.finditer(content):
            method = match.group(1).upper()
            path = match.group(2)

            line = content[: match.start()].count("\n") + 1

            result.routes.append(
                {
                    "method": method,
                    "path": path,
                    "file": rel,
                    "line": line,
                    "framework": "minimal-api",
                }
            )

    # -----------------------------------------------------------------------
    # using statements
    # -----------------------------------------------------------------------

    def _extract_usings(
        self,
        rel: str,
        content: str,
        result: ExtractionResult,
    ) -> None:
        imports: Set[str] = set()

        for match in _USING.finditer(content):
            namespace = match.group(1)

            # Framework namespaces are intentionally omitted.
            if namespace.startswith("System"):
                continue

            if namespace.startswith("Microsoft"):
                continue

            imports.add(namespace)

        if imports:
            result.imports[rel] = sorted(imports)

    # -----------------------------------------------------------------------
    # .csproj
    # -----------------------------------------------------------------------

    def _parse_csproj(self, result: ExtractionResult) -> None:
        """Extract assembly name and PackageReference dependencies."""

        csproj_files = list(self.root.glob("*.csproj"))

        for csproj in csproj_files:
            content = safe_read_text(csproj)
            if not content:
                continue

            try:
                root = ET.fromstring(content)
                self._parse_csproj_xml(root, result)
            except ET.ParseError:
                self._parse_csproj_regex(content, result)

            # Normally there is one .csproj per project.
            break

    def _parse_csproj_xml(
        self,
        root: ET.Element,
        result: ExtractionResult,
    ) -> None:
        for element in root.iter():
            tag = element.tag.split("}")[-1]

            if tag == "AssemblyName" and element.text:
                result.external_calls.append(
                    f"csharp-assembly: {element.text.strip()}"
                )

            elif tag == "PackageReference":
                include = element.attrib.get("Include")
                if include:
                    result.external_calls.append(
                        f"csharp-dep: {include}"
                    )

    def _parse_csproj_regex(
        self,
        content: str,
        result: ExtractionResult,
    ) -> None:
        assembly = re.search(
            r"<AssemblyName>\s*([^<]+?)\s*</AssemblyName>",
            content,
            re.IGNORECASE,
        )

        if assembly:
            result.external_calls.append(
                f"csharp-assembly: {assembly.group(1).strip()}"
            )

        for match in re.finditer(
            r'<PackageReference\b[^>]*\bInclude\s*=\s*"([^"]+)"',
            content,
            re.IGNORECASE,
        ):
            result.external_calls.append(
                f"csharp-dep: {match.group(1)}"
            )
