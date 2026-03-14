"""Base generator interface."""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Tuple, List

class BaseGenerator(ABC):
    """Base class for output generators."""
    
    def __init__(self, root: Path, config: dict):
        self.root = root
        self.config = config
    
    @abstractmethod
    def generate(self) -> Tuple[str, List[Path]]:
        """
        Generate output content.
        
        Returns:
            (content: str, source_files: List[Path])
        """
        pass
    
    @property
    @abstractmethod
    def output_filename(self) -> str:
        """Name of the output file."""
        pass
