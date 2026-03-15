import argparse
import json
import sys
from pathlib import Path

from . import VERSION
from .config import get_default_config, load_config, deep_merge
from .security.manager import SecurityManager
from .utils.files import safe_read_text
from .workspace import WorkspaceManifest, WorkspaceQuery, ConflictDetector
from .doctor import DiagnosticTool
from .watch import watch_mode
from .generator import LLMContextGenerator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LLM Context Generator - Generate context files for LLMs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python llm-context-setup.py workspace list
  python llm-context-setup.py workspace query --tags core
  python llm-context-setup.py workspace query --service auth-service --what all
  python llm-context-setup.py workspace validate
  python llm-context-setup.py workspace generate
  python llm-context-setup.py workspace conflicts
""",
    )

    subparsers = parser.add_subparsers(dest="command")

    workspace_parser = subparsers.add_parser(
        "workspace",
        help="Multi-repository workspace commands",
    )
    workspace_parser.add_argument("--workspace", "-w", help="Path to ccc-workspace.yml file")
    workspace_subparsers = workspace_parser.add_subparsers(dest="workspace_command")

    workspace_subparsers.add_parser("list", help="List all services in workspace")

    query_parser = workspace_subparsers.add_parser("query", help="Query services")
    query_parser.add_argument("--tags", "-t", nargs="+", help="Filter by tags")
    query_parser.add_argument("--service", "-s", help="Query specific service")
    query_parser.add_argument(
        "--what",
        choices=["info", "depends-on", "dependents", "external", "all"],
        default="all",
        help="What information to show",
    )
    query_parser.add_argument(
        "--generate",
        "-g",
        action="store_true",
        help="Generate workspace context for matched services",
    )

    workspace_subparsers.add_parser("validate", help="Validate workspace configuration")

    gen_parser = workspace_subparsers.add_parser("generate", help="Generate workspace context")
    gen_parser.add_argument("--tags", "-t", nargs="+", help="Filter services by tags")

    conflicts_parser = workspace_subparsers.add_parser(
        "conflicts",
        help="Detect cross-repo conflicts and inconsistencies",
    )
    conflicts_parser.add_argument("--tags", "-t", nargs="+", help="Filter services by tags")
    conflicts_parser.add_argument("--output", "-o", help="Output directory for report")

    doctor_ws_parser = workspace_subparsers.add_parser(
        "doctor",
        help="Check workspace health (alias for conflicts)",
    )
    doctor_ws_parser.add_argument("--tags", "-t", nargs="+", help="Filter services by tags")
    doctor_ws_parser.add_argument("--output", "-o", help="Output directory for report")

    # pkml subcommand
    pkml_parser = subparsers.add_parser(
        "pkml",
        help="Bootstrap a pkml.json from generated .llm-context/ files",
    )
    pkml_parser.add_argument(
        "path", nargs="?", default=".",
        help="Path to project root (default: current directory)",
    )
    pkml_parser.add_argument(
        "--output", "-o",
        help="Output directory (default: product-knowledge/)",
    )
    pkml_parser.add_argument(
        "--open", action="store_true",
        help="Open PKML editor in browser after generating",
    )

    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--quick-update", "-q", action="store_true")
    parser.add_argument("--force", "-f", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--with-summaries", action="store_true")
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--security-status", action="store_true")
    parser.add_argument("--output", "-o")
    parser.add_argument("--config", "-c")
    parser.add_argument("--version", "-v", action="version", version=f"ccc {VERSION}")
    return parser


def load_runtime_config(args, root: Path) -> dict:
    if args.config:
        config_path = Path(args.config)
        if config_path.suffix in (".yml", ".yaml"):
            try:
                import yaml
                content = safe_read_text(config_path)
                config = get_default_config()
                if content:
                    user_config = yaml.safe_load(content)
                    if user_config:
                        deep_merge(config, user_config)
                return config
            except ImportError:
                print("  YAML config requires: pip install pyyaml")
                sys.exit(1)
        else:
            content = safe_read_text(config_path)
            config = get_default_config()
            if content:
                user_config = json.loads(content)
                deep_merge(config, user_config)
            return config

    return load_config(root)


def handle_workspace_command(args) -> int:
    workspace_file = Path(args.workspace) if getattr(args, "workspace", None) else None

    if not workspace_file:
        for filename in ["ccc-workspace.yml", "ccc-workspace.yaml", "ccc-workspace.json"]:
            if Path(filename).exists():
                workspace_file = Path(filename)
                break

    if not workspace_file or not workspace_file.exists():
        print("\n  Error: No workspace file found.")
        return 1

    try:
        manifest = WorkspaceManifest.load(workspace_file)
    except ImportError as e:
        print(f"\n  Error: {e}")
        return 1
    except Exception as e:
        print(f"\n  Error loading workspace: {e}")
        return 1

    query = WorkspaceQuery(manifest)
    workspace_cmd = getattr(args, "workspace_command", None)

    if workspace_cmd == "list":
        query.list_services()
        return 0

    if workspace_cmd == "query":
        tags = getattr(args, "tags", None)
        service = getattr(args, "service", None)
        what = getattr(args, "what", "all")
        generate = getattr(args, "generate", False)

        if tags:
            query.query_tags(tags, generate_context=generate)
            return 0
        if service:
            query.query_service(service, what=what)
            return 0

        print("\n  Error: Specify --tags or --service")
        return 1

    if workspace_cmd == "validate":
        query.validate_workspace()
        return 0

    if workspace_cmd == "generate":
        tags = getattr(args, "tags", None)
        services = manifest.query_by_tags(tags) if tags else list(manifest.services.values())
        query.generate_workspace_context(services)
        return 0

    if workspace_cmd in ("conflicts", "doctor"):
        tags = getattr(args, "tags", None)
        output = getattr(args, "output", None)
        services = manifest.query_by_tags(tags) if tags else list(manifest.services.values())

        detector = ConflictDetector(manifest)
        conflicts = detector.analyze(services)
        detector.print_summary()

        output_dir = Path(output) if output else manifest.root / "workspace-context"
        detector.generate_report(output_dir)
        print(f"  Report saved to: {output_dir / 'conflicts-report.md'}")

        errors = [c for c in conflicts if c.severity == "error"]
        return 1 if errors else 0

    print("\n  Error: Unknown workspace command")
    return 1


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "workspace":
        return handle_workspace_command(args)

    if args.command == "pkml":
        return handle_pkml_command(args)

    root = Path(args.path).resolve()
    config = load_runtime_config(args, root)

    if args.output:
        config["output_dir"] = args.output

    if args.with_summaries:
        config["generate"]["module_summaries"] = True
        if config.get("security", {}).get("mode") == "offline":
            config["security"]["mode"] = "public-ai"

    if args.security_status:
        security = SecurityManager(root, config)
        security.print_status()
        return 0

    if args.doctor:
        tool = DiagnosticTool(root)
        tool.run()
        return 0

    if args.watch:
        watch_mode(root, config, LLMContextGenerator)
        return 0

    generator = LLMContextGenerator(
        root=root,
        config=config,
        quick_mode=args.quick_update,
        force=args.force,
    )
    generator.generate()
    return 0


def handle_pkml_command(args) -> int:
    """Handle the `ccc pkml` subcommand."""
    from .generators.pkml import bootstrap_pkml

    root = Path(getattr(args, "path", ".")).resolve()
    output = Path(args.output).resolve() if getattr(args, "output", None) else None
    open_editor = getattr(args, "open", False)

    print("")
    print("=" * 60)
    print("  CCC -> PKML Bootstrapper")
    print(f"  Project: {root}")
    print("=" * 60)
    print("")

    try:
        out_path = bootstrap_pkml(root, output_dir=output, open_editor=open_editor)
        print(f"\n  pkml.json written to: {out_path}")
        return 0
    except FileNotFoundError as exc:
        print(f"\n  Error: {exc}")
        return 1
    except Exception as exc:
        print(f"\n  Error generating pkml.json: {exc}")
        return 1
