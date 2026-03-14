"""Main CLI with workspace support."""
import argparse
from pathlib import Path

from .generator import LLMContextGenerator
from .workspace.cli import add_workspace_commands, workspace_main
from .doctor import DiagnosticTool
from .watch import watch_mode
from . import VERSION

def main():
    parser = argparse.ArgumentParser(
        description="Generate LLM context files",
    )
    
    # Add subcommands
    subparsers = parser.add_subparsers(dest="command")
    
    # Single-repo commands (default)
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--quick-update", "-q", action="store_true")
    # ... (move argument parsing)

    # Workspace commands
    add_workspace_commands(subparsers)
    
    args = parser.parse_args()
    
    if args.command == "workspace":
        return workspace_main(args)   
    
    if args.doctor:
        tool = DiagnosticTool(Path(args.path))
        tool.run()
        return
    
    # ... (rest of CLI logic)
