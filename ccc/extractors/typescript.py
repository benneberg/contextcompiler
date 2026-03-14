"""TypeScript/JavaScript code extractor."""
import re
from pathlib import Path
from typing import List

from .base import BaseExtractor, ExtractionResult, ExtractedSymbol
from ..utils.files import safe_read_text, should_skip_path


class TypeScriptExtractor(BaseExtractor):
    """Extract symbols, routes, and types from TypeScript/JavaScript source."""

    @property
    def file_patterns(self) -> List[str]:
        return ["*.ts", "*.tsx", "*.js", "*.jsx"]

    @property
    def language_name(self) -> str:
        return "typescript"

    def extract(self) -> ExtractionResult:
        result = ExtractionResult()

        for pattern in self.file_patterns:
            for ts_file in self.root.rglob(pattern):
                if should_skip_path(ts_file):
                    continue
                if ".spec." in ts_file.name or ".test." in ts_file.name:
                    continue
                content = safe_read_text(ts_file)
                if not content:
                    continue
                result.source_files.append(ts_file)
                self._extract_from_source(ts_file, content, result)

        return result

    def _extract_from_source(
        self, filepath: Path, content: str, result: ExtractionResult
    ) -> None:
        rel_path = str(filepath.relative_to(self.root))

        # Exported functions
        fn_pattern = re.compile(
            r"^export\s+(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)\s*(?::\s*([^\{]*))?",
            re.MULTILINE,
        )
        for match in fn_pattern.finditer(content):
            name, params, return_type = match.groups()
            ret = f": {return_type.strip()}" if return_type and return_type.strip() else ""
            result.symbols.append(ExtractedSymbol(
                name=name, kind="function", file=rel_path,
                line=content[:match.start()].count("\n") + 1,
                signature=f"function {name}({params}){ret}",
            ))

        # Interfaces and types
        for kind, pattern_str in [
            ("interface", r"(?:export\s+)?interface\s+(\w+)"),
            ("type", r"(?:export\s+)?type\s+(\w+)\s*="),
            ("enum", r"(?:export\s+)?enum\s+(\w+)"),
        ]:
            for match in re.finditer(pattern_str, content):
                result.symbols.append(ExtractedSymbol(
                    name=match.group(1), kind=kind, file=rel_path,
                    line=content[:match.start()].count("\n") + 1,
                ))
                if kind in ("interface", "type", "enum"):
                    result.types.append({"name": match.group(1), "file": rel_path, "kind": kind})

        # Routes (Express/fastify style)
        route_pattern = re.compile(
            r"(?:app|router|server)\.(get|post|put|patch|delete)\s*\(\s*['\"/]([^'\"]*)['\"]",
        )
        for match in route_pattern.finditer(content):
            method, path = match.groups()
            result.routes.append({"method": method.upper(), "path": path, "file": rel_path})

        # Relative imports
        import_pattern = re.compile(r"""(?:import|require)\s*\(?['"](\.+[^'"]+)['"]\)?""")
        result.imports[rel_path] = import_pattern.findall(content)

        # External HTTP calls
        http_pattern = re.compile(
            r"""(?:fetch|axios\.\w+|got\.\w+)\s*\(\s*[`'"](https?://[^`'"]+)"""
        )
        for match in http_pattern.finditer(content):
            result.external_calls.append(match.group(1))