"""Workspace-specific CLI commands."""
import argparse
from pathlib import Path

from .manifest import WorkspaceManifest
from .query import WorkspaceQuery

def workspace_main(args):
    """Handle workspace subcommands."""
    workspace_file = Path(args.workspace or "ccc-workspace.yml")
    
    if not workspace_file.exists():
        print(f"Error: Workspace file not found: {workspace_file}")
        print("\nCreate one with:")
        print("  ccc workspace init")
        return 1
    
    manifest = WorkspaceManifest.load(workspace_file)
    
    if args.workspace_command == "query":
        query = WorkspaceQuery(manifest)
        if args.tags:
            query.query_tags(args.tags)
        else:
            print("Error: --tags required for query")
            return 1
    
    elif args.workspace_command == "list":
        print(f"\nWorkspace: {manifest.name}\n")
        for name, service in manifest.services.items():
            tags_str = ", ".join(service.tags)
            print(f"  {name:20s} [{service.type:12s}] — tags: {tags_str}")
    
    return 0

def add_workspace_commands(subparsers):
    """Add workspace subcommands to CLI."""
    workspace = subparsers.add_parser("workspace", help="Multi-repo workspace commands")
    workspace.add_argument("--workspace", "-w", help="Path to ccc-workspace.yml")
    
    workspace_subparsers = workspace.add_subparsers(dest="workspace_command")
    
    # ccc workspace query
    query = workspace_subparsers.add_parser("query", help="Query services by tags")
    query.add_argument("--tags", nargs="+", help="Tags to search for")
    
    # ccc workspace list
    workspace_subparsers.add_parser("list", help="List all services")
    
    # ccc workspace generate
    generate = workspace_subparsers.add_parser("generate", help="Generate cross-repo context")
