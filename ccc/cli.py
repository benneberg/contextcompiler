"""Command-line interface."""
import argparse
from pathlib import Path

from .generator import LLMContextGenerator
from .doctor import DiagnosticTool
from .watch import watch_mode
from . import VERSION

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate LLM context files for a codebase",
    )
    # ... (move argument parsing)
    
    args = parser.parse_args()
    
    if args.doctor:
        tool = DiagnosticTool(Path(args.path))
        tool.run()
        return
    
    # ... (rest of CLI logic)
