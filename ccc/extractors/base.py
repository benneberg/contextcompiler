"""Base extractor interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional

@dataclass
class ExtractedSymbol:
    """A symbol extracted from source code."""
    name: str
    kind: str  # "class", "function", "type", "route", "event"
    file: str
    line: int
    signature: str = ""
    docstring: str = ""
    metadata: Dict = field(default_factory=dict)

@dataclass
class ExtractionResult:
    """Result of code extraction."""
    symbols: List[ExtractedSymbol] = field(default_factory=list)
    imports: Dict[str, List[str]] = field(default_factory=dict)
    routes: List[Dict] = field(default_factory=list)
    types: List[Dict] = field(default_factory=list)
    external_calls: List[str] = field(default_factory=list)
    events: List[str] = field(default_factory=list)
    source_files: List[Path] = field(default_factory=list)

class BaseExtractor(ABC):
    """Base class for language-specific extractors."""
    
    def __init__(self, root: Path):
        self.root = root
    
    @abstractmethod
    def extract(self) -> ExtractionResult:
        """Extract information from source files."""
        pass
    
    @property
    @abstractmethod
    def file_patterns(self) -> List[str]:
        """File patterns this extractor handles."""
        pass
    
    @property
    @abstractmethod
    def language_name(self) -> str:
        """Name of the language."""
        pass
