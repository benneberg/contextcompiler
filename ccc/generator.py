"""Main context generator orchestrator."""
from pathlib import Path
from typing import Optional, Dict, List

from .config import load_config
from .manifest import SmartUpdater, GenerationManifest
from .security.modes import SecurityManager
from .extractors.python import PythonExtractor
from .extractors.typescript import TypeScriptExtractor
# ... import other extractors
from .generators.tree import TreeGenerator
from .generators.schemas import SchemaGenerator
# ... import other generators

class LLMContextGenerator:
    """Main orchestrator for context generation."""
    
    def __init__(
        self,
        root: Path,
        config: Optional[dict] = None,
        quick_mode: bool = False,
        force: bool = False,
    ):
        self.root = root
        self.config = config or load_config(self.root)
        self.output_dir = self.root / self.config["output_dir"]
        self.quick_mode = quick_mode
        self.updater = SmartUpdater(self.root, self.config, force=force)
        self.security = SecurityManager(self.root, self.config)
    
    def generate(self) -> None:
        """Generate all context files."""
        # ... (move generation logic)
