"""Python code extractor."""
import ast
import re
from pathlib import Path
from typing import List

from .base import BaseExtractor, ExtractionResult, ExtractedSymbol
from ..utils.files import safe_read_text, should_skip_path


class PythonExtractor(BaseExtractor):
    """Extract symbols, routes, types, and imports from Python source."""

    @property
    def file_patterns(self) -> List[str]:
        return ["*.py"]

    @property
    def language_name(self) -> str:
        return "python"

    def extract(self) -> ExtractionResult:
        result = ExtractionResult()

        for py_file in self.root.rglob("*.py"):
            if should_skip_path(py_file):
                continue
            content = safe_read_text(py_file)
            if not content:
                continue
            try:
                tree = ast.parse(content)
                result.source_files.append(py_file)
                self._extract_from_ast(tree, py_file, content, result)
            except SyntaxError:
                continue

        return result

    def _extract_from_ast(
        self,
        tree: ast.AST,
        filepath: Path,
        content: str,
        result: ExtractionResult,
    ) -> None:
        rel_path = str(filepath.relative_to(self.root))

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                symbol = ExtractedSymbol(
                    name=node.name,
                    kind="class",
                    file=rel_path,
                    line=node.lineno,
                )
                result.symbols.append(symbol)

                if self._is_schema_class(node):
                    result.types.append({
                        "name": node.name,
                        "file": rel_path,
                        "line": node.lineno,
                    })

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    symbol = ExtractedSymbol(
                        name=node.name,
                        kind="function",
                        file=rel_path,
                        line=node.lineno,
                        signature=self._format_signature(node),
                    )
                    result.symbols.append(symbol)

        result.imports[rel_path] = self._extract_imports(content)
        result.external_calls.extend(self._extract_external_calls(content))

    def _is_schema_class(self, node: ast.ClassDef) -> bool:
        base_names = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_names.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_names.append(base.attr)
        schema_bases = {"BaseModel", "BaseSchema", "TypedDict", "Enum", "IntEnum", "StrEnum"}
        return bool(set(base_names) & schema_bases)

    def _format_signature(self, node: ast.AST) -> str:
        """Format a function/method as a readable signature string."""
        prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
        args = []
        for arg in node.args.args:
            if arg.arg == "self":
                continue
            if arg.annotation:
                try:
                    annotation = f": {ast.unparse(arg.annotation)}"
                except Exception:
                    annotation = ""
            else:
                annotation = ""
            args.append(f"{arg.arg}{annotation}")

        returns = ""
        if node.returns:
            try:
                returns = f" -> {ast.unparse(node.returns)}"
            except Exception:
                pass

        return f"{prefix}def {node.name}({', '.join(args)}){returns}"

    def _extract_imports(self, content: str) -> List[str]:
        """Extract import module names from source."""
        pattern = re.compile(
            r"^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
            re.MULTILINE,
        )
        imports = []
        for match in pattern.finditer(content):
            module = match.group(1) or match.group(2)
            if module:
                imports.append(module)
        return imports

    def _extract_external_calls(self, content: str) -> List[str]:
        """Extract HTTP API calls made from this file."""
        patterns = [
            r"requests\.(get|post|put|delete|patch)\(['\"]([^'\"]+)",
            r"httpx\.(get|post|put|delete|patch)\(['\"]([^'\"]+)",
            r"aiohttp.*?\.(get|post|put|delete)\(['\"]([^'\"]+)",
        ]
        calls = []
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                calls.append(match.group(2))
        return calls