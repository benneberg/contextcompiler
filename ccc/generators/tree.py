"""File tree generator."""
from pathlib import Path
from typing import Tuple, List

from .base import BaseGenerator
from ..utils.formatting import human_readable_size

class TreeGenerator(BaseGenerator):
    """Generate file tree visualization."""
    
    @property
    def output_filename(self) -> str:
        return "tree.txt"
    
    def generate(self) -> Tuple[str, List[Path]]:
        """Generate file tree."""
        # ... (move TreeGenerator logic)
