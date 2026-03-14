"""Python code extractor."""
from pathlib import Path
from typing import Tuple, List
import ast
import re

from .base import BaseExtractor, ExtractionResult, ExtractedSymbol
from ..utils.files import safe_read_text, should_skip_path

class PythonExtractor(BaseExtractor):
    """Extract information from Python code."""
    
    @property
    def file_patterns(self) -> List[str]:
        return ["*.py"]
    
    @property
    def language_name(self) -> str:
        return "python"
    
    def extract(self) -> ExtractionResult:
        """Extract Python symbols, routes, types."""
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
        result: ExtractionResult
    ) -> None:
        """Extract symbols from AST."""
        rel_path = str(filepath.relative_to(self.root))
        
        for node in ast.walk(tree):
            # Extract classes
            if isinstance(node, ast.ClassDef):
                symbol = ExtractedSymbol(
                    name=node.name,
                    kind="class",
                    file=rel_path,
                    line=node.lineno,
                )
                result.symbols.append(symbol)
                
                # Check if it's a schema/model
                if self._is_schema_class(node):
                    result.types.append({
                        "name": node.name,
                        "file": rel_path,
                        "line": node.lineno,
                    })
            
            # Extract functions
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
            
            # Extract routes (FastAPI, Flask, etc.)
            # ... (extract route detection logic)
        
        # Extract imports
        result.imports[rel_path] = self._extract_imports(content)
        
        # Extract external API calls
        result.external_calls.extend(self._extract_external_calls(content))
    
    def _is_schema_class(self, node: ast.ClassDef) -> bool:
        """Check if class is a schema/model."""
        base_names = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_names.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_names.append(base.attr)
        
        schema_bases = {"BaseModel", "BaseSchema", "TypedDict", "Enum"}
        return bool(set(base_names) & schema_bases)
    
    def _format_signature(self, node) -> str:
        """Format function signature."""
        # ... (extract signature formatting logic)
    
    def _extract_imports(self, content: str) -> List[str]:
        """Extract import statements."""
        # ... (extract import detection logic)
    
    def _extract_external_calls(self, content: str) -> List[str]:
        """Extract external API calls."""
        patterns = [
            r"requests\.(get|post|put|delete)\(['\"]([^'\"]+)",
            r"httpx\.(get|post|put|delete)\(['\"]([^'\"]+)",
        ]
        calls = []
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                calls.append(match.group(2))
        return calls
