"""Schema extraction generator."""
from pathlib import Path
from typing import Tuple, List, Dict

from .base import BaseGenerator
from ..extractors.base import ExtractionResult
from ..utils.formatting import get_timestamp

class SchemaGenerator(BaseGenerator):
    """Generate schema extractions for all languages."""
    
    def __init__(self, root: Path, config: dict, extraction_results: Dict[str, ExtractionResult]):
        super().__init__(root, config)
        self.results = extraction_results
    
    def generate(self) -> Dict[str, Tuple[str, List[Path]]]:
        """Generate schema files for each language."""
        outputs = {}
        
        for lang, result in self.results.items():
            if not result.types:
                continue
            
            filename = self._get_filename(lang)
            content = self._format_types(lang, result)
            outputs[filename] = (content, result.source_files)
        
        return outputs
    
    def _get_filename(self, lang: str) -> str:
        """Get output filename for language."""
        mapping = {
            "python": "schemas-extracted.py",
            "typescript": "types-extracted.ts",
            "rust": "rust-types.rs",
            "go": "go-types.go",
            "csharp": "csharp-types.cs",
        }
        return mapping.get(lang, f"{lang}-types.txt")
    
    def _format_types(self, lang: str, result: ExtractionResult) -> str:
        """Format types for output."""
        # ... (move formatting logic)
