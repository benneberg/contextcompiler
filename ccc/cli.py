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
        "--generate", "-g", action="store_true",
        help="Generate workspace context for matched services",
    )
    query_parser.add_argument(
        "--intent", "-i", metavar="TASK",
        help="Natural language task description — resolve relevant services and optionally generate task context",
    )
    query_parser.add_argument(
        "--depth", type=int, choices=[1, 2], default=1,
        help="Dependency expansion depth: 1=direct, 2=transitive (default: 1)",
    )

    workspace_subparsers.add_parser("validate", help="Validate workspace configuration")

    gen_parser = workspace_subparsers.add_parser("generate", help="Generate workspace context")
    gen_parser.add_argument("--tags", "-t", nargs="+", help="Filter services by tags")
    gen_parser.add_argument("--skip-discover", action="store_true",
                            help="Skip automatic undeclared dependency detection after generate")
    gen_parser.add_argument("--commit-index", action="store_true",
                            help="Stage workspace-context/service-index.json for git commit after generation")

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

    # workspace init
    init_parser = workspace_subparsers.add_parser(
        "init",
        help="Scan directories and generate a ccc-workspace.yml draft",
    )
    init_parser.add_argument(
        "scan_path", nargs="?", default=".",
        help="Directory to scan for service repos (default: current directory)",
    )
    init_parser.add_argument("--name", "-n", help="Workspace name (default: directory name)")
    init_parser.add_argument("--output", "-o", help="Where to write ccc-workspace.yml")
    init_parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing file")

    # workspace serve
    serve_parser = workspace_subparsers.add_parser(
        "serve",
        help="Launch browser UI for workspace exploration",
    )
    serve_parser.add_argument("--port", "-p", type=int, default=7842, help="Port to serve on (default: 7842)")
    serve_parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
    serve_parser.add_argument("--no-rebuild", action="store_true", help="Skip rebuilding service-index.json")
    serve_parser.add_argument("--bind", default="127.0.0.1", metavar="ADDR",
                              help="Address to bind to (default: 127.0.0.1). Use 0.0.0.0 to expose on network.")
    serve_parser.add_argument("--token", default=None, metavar="TOKEN",
                              help="Require ?token=TOKEN in URL to access the UI")
    serve_parser.add_argument("--auto-refresh", type=int, default=0, metavar="SECONDS",
                              help="Auto-refresh UI every N seconds (0 = disabled). Useful when running ccc workspace generate in another terminal.")
    serve_parser.add_argument("--live-reload", action="store_true",
                              help="Enable WebSocket live reload — UI updates instantly when workspace generate runs (requires websockets + watchdog)")

    # workspace discover
    discover_parser = workspace_subparsers.add_parser(
        "discover",
        help="Find undeclared cross-repo relationships from artifact analysis",
    )
    discover_parser.add_argument("--tags", "-t", nargs="+", help="Filter services by tags")
    discover_parser.add_argument(
        "--min-confidence", type=float, default=0.5, metavar="FLOAT",
        help="Minimum confidence threshold 0.0-1.0 (default: 0.5)",
    )
    discover_parser.add_argument("--output", "-o", help="Output directory for reports")

    # query subcommand
    query_cmd = subparsers.add_parser(
        "query",
        help="Query .llm-context/ artifacts at runtime",
    )
    query_cmd.add_argument("term", help="Symbol name, route keyword, or free text")
    query_cmd.add_argument(
        "--type", choices=["symbol", "route", "impact", "api", "context", "all"],
        default="all", help="Query type (default: all)",
    )
    query_cmd.add_argument(
        "--format", choices=["human", "json", "compact", "markdown"],
        default="human", help="Output format (default: human)",
    )
    query_cmd.add_argument(
        "--context-dir", default=".llm-context",
        help="Path to .llm-context/ directory (default: .llm-context)",
    )
    query_cmd.add_argument(
        "--limit", type=int, default=10,
        help="Max results per section (default: 10)",
    )

    # align subcommand
    align_cmd = subparsers.add_parser(
        "align",
        help="Detect drift between code (CCC) and product docs (PKML)",
    )
    align_cmd.add_argument(
        "--pkml", help="Path to pkml.json (default: auto-detect)",
    )
    align_cmd.add_argument(
        "--context-dir", default=".llm-context",
        help="Path to .llm-context/ directory (default: .llm-context)",
    )
    align_cmd.add_argument(
        "--format", choices=["human", "json"],
        default="human", help="Output format (default: human)",
    )

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

    setup_parser = subparsers.add_parser(
        "setup",
        help="Interactive onboarding wizard — detects single repo vs. workspace and sets everything up",
    )
    setup_parser.add_argument(
        "path", nargs="?", default=".",
        help="Root directory to set up (default: current directory)",
    )

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Show exactly what CCC extracted from a specific file",
    )
    inspect_parser.add_argument(
        "file",
        help="Path to the file to inspect",
    )
    inspect_parser.add_argument(
        "--root", "-r", default=None,
        help="Repo root directory (auto-detected if not specified)",
    )

    feedback_parser = subparsers.add_parser(
        "feedback",
        help="Record post-session AI feedback to improve context quality over time",
    )
    feedback_parser.add_argument(
        "--analyze", action="store_true",
        help="Summarise patterns across all recorded feedback sessions",
    )
    feedback_parser.add_argument(
        "--service", default=None, metavar="NAME",
        help="Pre-fill the service name",
    )
    feedback_parser.add_argument(
        "--root", default=None, metavar="PATH",
        help="Repo root (auto-detected if not specified)",
    )

    context_for_parser = subparsers.add_parser(
        "context-for",
        help="Assemble token-budget-aware context for a task — outputs #file: blocks ready to paste into Copilot/Claude",
    )
    context_for_parser.add_argument(
        "task",
        help="Natural language task description (e.g. 'add webm support to thumbnail pipeline')",
    )
    context_for_parser.add_argument(
        "--budget", type=int, default=8000, metavar="TOKENS",
        help="Target token budget for the assembled context (default: 8000)",
    )
    context_for_parser.add_argument(
        "--depth", type=int, choices=[1, 2], default=1,
        help="Dependency expansion depth: 1=direct, 2=transitive (default: 1)",
    )
    context_for_parser.add_argument(
        "--generate", action="store_true",
        help="Also write task context files to workspace-context/task-{slug}/",
    )
    context_for_parser.add_argument(
        "--workspace", default=None, metavar="PATH",
        help="Path to workspace root with ccc-workspace.yml (auto-detected if not specified)",
    )

    parser.add_argument(
        "path", nargs="?", default=".",
        help="Path to the repository root to analyse (default: current directory)",
    )
    parser.add_argument(
        "--quick-update", "-q", action="store_true",
        help="Skip unchanged files using content hashes — faster incremental runs",
    )
    parser.add_argument(
        "--force", "-f", action="store_true",
        help="Regenerate all artifacts even if they appear up-to-date",
    )
    parser.add_argument(
        "--watch", action="store_true",
        help="Watch for file changes and regenerate context automatically",
    )
    parser.add_argument(
        "--with-summaries", action="store_true",
        help="Include AI-generated per-file summaries (requires an AI provider key)",
    )
    parser.add_argument(
        "--doctor", action="store_true",
        help="Run diagnostic checks and report issues without generating context",
    )
    parser.add_argument(
        "--security-status", action="store_true",
        help="Print the current security mode and redaction settings, then exit",
    )
    parser.add_argument(
        "--output", "-o",
        metavar="DIR",
        help="Override the output directory for generated artifacts (default: .llm-context/)",
    )
    parser.add_argument(
        "--config", "-c",
        metavar="FILE",
        help="Path to a ccc config file (default: .llm-context/config.yml in the repo root)",
    )
    parser.add_argument("--version", "-v", action="version", version=f"ccc {VERSION}")
    parser.add_argument("--quiet", action="store_true", help="Suppress all output except warnings and errors")
    parser.add_argument("--verbose", action="store_true", help="Enable debug-level output")
    parser.add_argument("--log-file", metavar="PATH", help="Write log output to file")
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


def _handle_context_for(args) -> int:
    """
    Handler for `ccc context-for "task description"`.

    Finds a workspace (via ccc-workspace.yml), scores services by relevance
    to the task, assembles a token-budget-aware context package, and prints
    a ready-to-paste #file: block for Copilot/Claude.
    """
    from pathlib import Path as _Path
    from .task_context import resolve_intent, generate_task_context

    task  = args.task
    budget = getattr(args, "budget", 8000)
    depth  = getattr(args, "depth", 1)
    generate = getattr(args, "generate", False)
    ws_arg = getattr(args, "workspace", None)

    # Auto-detect workspace root
    if ws_arg:
        ws_root = _Path(ws_arg).resolve()
    else:
        ws_root = _Path.cwd()
        for p in [_Path.cwd()] + list(_Path.cwd().parents):
            for name in ("ccc-workspace.yml", "ccc-workspace.yaml", "ccc-workspace.json"):
                if (p / name).exists():
                    ws_root = p
                    break
            else:
                continue
            break

    # Load manifest
    ws_file = None
    for name in ("ccc-workspace.yml", "ccc-workspace.yaml", "ccc-workspace.json"):
        candidate = ws_root / name
        if candidate.exists():
            ws_file = candidate
            break

    if not ws_file:
        print(f"\n  Error: no ccc-workspace.yml found (searched from {_Path.cwd()})")
        print(f"  Run `ccc workspace init` first, or use --workspace PATH\n")
        return 1

    from .workspace.manifest import WorkspaceManifest
    manifest = WorkspaceManifest.load(ws_file)

    print(f"\n{'=' * 60}")
    print(f"  ccc context-for: {task!r}")
    print(f"  Workspace: {manifest.name} ({len(manifest.services)} services)")
    print(f"  Budget: ~{budget:,} tokens  |  Depth: {depth}")
    print(f"{'=' * 60}\n")

    results = resolve_intent(manifest, task, depth=depth)
    if not results:
        print("  No services matched. Try different keywords or add tags to ccc-workspace.yml.\n")
        return 1

    primary   = [r for r in results if r["score"] >= 20]
    secondary = [r for r in results if r["score"] < 20]

    # Load context-manifest.json to get token estimates
    token_estimates: dict = {}
    index_path = ws_root / "workspace-context" / "service-index.json"
    if index_path.exists():
        import json as _json
        try:
            idx_data = _json.loads(index_path.read_text())
            for svc_name, svc_data in idx_data.get("services", {}).items():
                path = svc_data.get("path", "")
                cm_path = ws_root / path / ".llm-context" / "context-manifest.json"
                if cm_path.exists():
                    cm = _json.loads(cm_path.read_text())
                    token_estimates[svc_name] = cm.get("total_estimated_tokens", 0)
        except Exception:
            pass

    print("  Matched services:\n")
    total_tokens = 0
    file_block_lines = []
    over_budget = False

    for r in results:
        svc = r["svc"]
        name = r["name"]
        path = svc.get("path", name)
        has_ctx = svc.get("has_context", False)
        est = token_estimates.get(name, 0)
        tier = "primary" if r["score"] >= 20 else "secondary"
        tier_color = "●" if tier == "primary" else "○"

        reasons_str = ", ".join(r["reasons"][:3])
        token_str = f"~{est:,} tokens" if est else "no context"

        print(f"  {tier_color} {name:<28s}  score={r['score']:3d}  {token_str}")
        print(f"    {reasons_str}")

        if has_ctx:
            new_total = total_tokens + est
            if new_total <= budget or total_tokens == 0:
                file_block_lines.append(f"#file:{path}/.llm-context/LLM.md")
                total_tokens = new_total
            else:
                if not over_budget:
                    print(f"\n  [!] Budget ~{budget:,} tokens reached — remaining services excluded from file block")
                    over_budget = True
        else:
            print(f"    [!] No context — run `ccc` in {path} first")
        print()

    # Print the copyable block
    if file_block_lines:
        print(f"{'─' * 60}")
        print(f"  Copy for Copilot / Claude  (~{total_tokens:,} tokens)\n")
        for line in file_block_lines:
            print(f"  {line}")
        print()
        print(f"  Task: {task}")
        print(f"{'─' * 60}\n")
    else:
        print("  No services with generated context found.")
        print("  Run `ccc` inside each service directory first.\n")

    # Optionally generate task context files
    if generate:
        print("  Generating task context package...")
        task_dir = generate_task_context(manifest, task, depth=depth)
        print(f"  Written: {task_dir}")
        for f in sorted(task_dir.iterdir()):
            size = f.stat().st_size
            print(f"    {f.name:<30s}  {size:,} bytes")
        print()

    return 0


def handle_workspace_command(args) -> int:
    workspace_cmd = getattr(args, "workspace_command", None)

    # init does not require an existing workspace file
    if workspace_cmd == "init":
        from .workspace.init import init_workspace
        scan_path = Path(getattr(args, "scan_path", ".")).resolve()
        output = getattr(args, "output", None)
        name = getattr(args, "name", None)
        force = getattr(args, "force", False)
        try:
            init_workspace(
                scan_path,
                output_path=Path(output).resolve() if output else scan_path,
                workspace_name=name,
                force=force,
            )
            return 0
        except FileExistsError as e:
            print(f"\n  Error: {e}")
            return 1
        except FileNotFoundError as e:
            print(f"\n  Error: {e}")
            return 1

    # all other commands require an existing workspace file
    workspace_file = Path(args.workspace) if getattr(args, "workspace", None) else None

    if not workspace_file:
        for filename in ["ccc-workspace.yml", "ccc-workspace.yaml", "ccc-workspace.json"]:
            if Path(filename).exists():
                workspace_file = Path(filename)
                break

    if not workspace_file or not workspace_file.exists():
        print("\n  Error: No workspace file found.")
        print("  Run `ccc workspace init` to create one.")
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

    if workspace_cmd == "list":
        query.list_services()
        return 0

    if workspace_cmd == "query":
        tags = getattr(args, "tags", None)
        service = getattr(args, "service", None)
        what = getattr(args, "what", "all")
        generate = getattr(args, "generate", False)
        intent = getattr(args, "intent", None)
        depth = getattr(args, "depth", 1)

        # Intent-based query: natural language → ranked services
        if intent:
            from .task_context import resolve_intent, generate_task_context
            print(f"\n  Resolving intent: {intent!r}  (depth {depth})\n")
            results = resolve_intent(manifest, intent, depth=depth)
            if not results:
                print("  No services matched. Try different keywords or add tags to ccc-workspace.yml.\n")
                return 1
            primary   = [r for r in results if r["score"] >= 20]
            secondary = [r for r in results if r["score"] < 20]
            print(f"  {'Service':<30s}  {'Score':>5}  Reasons")
            print(f"  {'-'*30}  {'-'*5}  -------")
            for r in primary:
                print(f"  {r['name']:<30s}  {r['score']:>5}  {', '.join(r['reasons'][:3])}")
            if secondary:
                print(f"\n  Secondary / transitive:")
                for r in secondary:
                    print(f"  {r['name']:<30s}  {r['score']:>5}  {', '.join(r['reasons'][:2])}")
            if generate:
                print(f"\n  Generating task context package...")
                task_dir = generate_task_context(manifest, intent, depth=depth)
                print(f"  Written to: {task_dir}")
                print(f"\n  Files:")
                for f in sorted(task_dir.iterdir()):
                    print(f"    {f.name}")
                print()
            return 0

        if tags:
            query.query_tags(tags, generate_context=generate)
            return 0
        if service:
            query.query_service(service, what=what)
            return 0

        print("\n  Error: Specify --tags, --service, or --intent")
        return 1

    if workspace_cmd == "validate":
        query.validate_workspace()
        return 0

    if workspace_cmd == "generate":
        tags = getattr(args, "tags", None)
        skip_discover = getattr(args, "skip_discover", False)
        commit_index = getattr(args, "commit_index", False)
        services = manifest.query_by_tags(tags) if tags else list(manifest.services.values())
        query.generate_workspace_context(services)

        if commit_index:
            index_path = manifest.root / "workspace-context" / "service-index.json"
            if index_path.exists():
                import subprocess as _sp
                result = _sp.run(
                    ["git", "add", str(index_path)],
                    cwd=str(manifest.root),
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    print(f"  [ok] Staged for commit: workspace-context/service-index.json")
                    print(f"       Teammates can now run `ccc workspace serve` without cloning all repos.")
                else:
                    print(f"  [!] git add failed: {result.stderr.strip()}")
            else:
                print(f"  [!] service-index.json not found — cannot stage")

        if not skip_discover:
            from .workspace.discover import run_discovery
            output_dir = manifest.root / "workspace-context"
            print(f"\n  Running discovery scan...")
            try:
                relationships, json_path, md_path = run_discovery(
                    manifest, services=services,
                    output_dir=output_dir, min_confidence=0.5,
                )
                undeclared = [r for r in relationships if not r.declared]
                if undeclared:
                    print(f"  [!] {len(undeclared)} undeclared relationship(s) found.")
                    print(f"      Review: {md_path.name}")
                    print(f"      Run `ccc workspace discover` for full details.")
                else:
                    print(f"  [ok] Discovery: all relationships declared in manifest.")
            except Exception as e:
                print(f"  [!] Discovery scan failed: {e}")

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

    if workspace_cmd == "discover":
        from .workspace.discover import run_discovery
        tags = getattr(args, "tags", None)
        min_conf = getattr(args, "min_confidence", 0.5)
        output = getattr(args, "output", None)
        services = manifest.query_by_tags(tags) if tags else list(manifest.services.values())
        output_dir = Path(output) if output else manifest.root / "workspace-context"

        print(f"\n{'=' * 60}")
        print(f"  CCC — Workspace Discovery")
        print(f"  Workspace: {manifest.name}")
        print(f"  Services:  {len(services)}")
        print(f"  Min confidence: {min_conf:.0%}")
        print(f"{'=' * 60}")

        relationships, json_path, md_path = run_discovery(
            manifest, services=services,
            output_dir=output_dir, min_confidence=min_conf,
        )

        undeclared = [r for r in relationships if not r.declared]
        print(f"\n  Results:")
        print(f"    Total relationships found: {len(relationships)}")
        print(f"    Undeclared (not in manifest): {len(undeclared)}")
        print(f"")
        print(f"  Reports written to:")
        print(f"    {json_path}")
        print(f"    {md_path}")
        print(f"")
        if undeclared:
            print(f"  ⚠  {len(undeclared)} undeclared relationship(s) found.")
            print(f"     Review {md_path.name} and add confirmed deps to ccc-workspace.yml")
        else:
            print(f"  ✓  All discovered relationships are declared in manifest.")
        print(f"")
        return 1 if undeclared else 0

    if workspace_cmd == "serve":
        from .workspace.serve import serve_workspace
        port = getattr(args, "port", 7842)
        no_open = getattr(args, "no_open", False)
        no_rebuild = getattr(args, "no_rebuild", False)
        bind = getattr(args, "bind", "127.0.0.1")
        token = getattr(args, "token", None)
        auto_refresh = getattr(args, "auto_refresh", 0)
        live_reload = getattr(args, "live_reload", False)
        try:
            serve_workspace(manifest, port=port, open_browser=not no_open,
                            rebuild_index=not no_rebuild, bind=bind, token=token,
                            auto_refresh=auto_refresh, live_reload=live_reload)
            return 0
        except Exception as e:
            print(f"\n  Error: {e}")
            return 1

    print("\n  Error: Unknown workspace command")
    return 1


def main():
    parser = build_parser()
    args = parser.parse_args()

    from .utils.logging import configure_logging
    configure_logging(
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
        log_file=getattr(args, "log_file", None),
    )

    if args.command == "workspace":
        return handle_workspace_command(args)

    if args.command == "setup":
        from .setup_wizard import run_setup
        path = getattr(args, "path", ".")
        return run_setup(path)

    if args.command == "inspect":
        from .inspect_cmd import run_inspect
        from pathlib import Path as _Path
        root_arg = getattr(args, "root", None)
        root = _Path(root_arg).resolve() if root_arg else None
        return run_inspect(args.file, root=root)

    if args.command == "feedback":
        from .feedback import run_feedback
        from pathlib import Path as _Path
        root_arg = getattr(args, "root", None)
        root = _Path(root_arg).resolve() if root_arg else None
        return run_feedback(
            root=root,
            service=getattr(args, "service", None),
            analyze=getattr(args, "analyze", False),
        )

    if args.command == "context-for":
        return _handle_context_for(args)

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

    if args.command == "query":
        from .query import CCCQueryEngine
        context_dir = getattr(args, "context_dir", ".llm-context")
        term = args.term
        qtype = getattr(args, "type", "all")
        fmt = getattr(args, "format", "human")
        limit = getattr(args, "limit", 10)

        try:
            engine = CCCQueryEngine(context_dir)
        except FileNotFoundError as e:
            print(f"\n  Error: {e}")
            return 1

        if qtype == "symbol":
            results = engine.search_symbols(term)
            if fmt == "json":
                import json
                print(json.dumps([{"name": s.name, "file": s.file,
                    "line": s.line, "kind": s.kind} for s in results[:limit]], indent=2))
            else:
                if results:
                    for s in results[:limit]:
                        print(f"  {s.kind:10s} {s.name:40s} {s.file}:{s.line}")
                else:
                    print(f"  No symbols found matching '{term}'")

        elif qtype == "route":
            results = engine.find_routes(term)
            if fmt == "json":
                import json
                print(json.dumps([{"method": r.method, "path": r.path,
                    "file": r.file} for r in results[:limit]], indent=2))
            else:
                if results:
                    for r in results[:limit]:
                        file_hint = f"  ({r.file})" if r.file else ""
                        print(f"  {r.method:8s} {r.path}{file_hint}")
                else:
                    print(f"  No routes found matching '{term}'")

        elif qtype == "impact":
            impact = engine.find_impact(term)
            if fmt == "json":
                import json
                print(json.dumps(impact, indent=2))
            else:
                print(f"\n  Impact analysis: {term}")
                print(f"  Total affected: {impact['total_affected']}")
                if impact["direct_dependents"]:
                    print(f"\n  Direct dependents:")
                    for d in impact["direct_dependents"]:
                        loc = f"  ({d['file']})" if d.get("file") else ""
                        print(f"    → {d['module']}{loc}")
                if impact["transitive_dependents"]:
                    print(f"\n  Transitive dependents:")
                    for d in impact["transitive_dependents"][:10]:
                        print(f"    ⟶ {d['module']}")
                if not impact["graph_available"]:
                    print(f"\n  Tip: pip install networkx for deeper graph analysis")

        elif qtype == "context":
            fmt_map = {"human": "markdown", "markdown": "markdown",
                       "json": "json", "compact": "compact"}
            output = engine.build_llm_context(
                term, format=fmt_map.get(fmt, "markdown"), max_symbols=limit,
            )
            print(output)

        else:  # all
            result = engine.query(term, limit=limit)
            if fmt == "json":
                import json
                print(engine.build_llm_context(term, format="json"))
            else:
                stats = engine.stats()
                print(f"\n  Query: '{term}'  "
                      f"({stats['symbols']} symbols, {stats['routes']} routes indexed)")
                print(f"  {result.total_hits} hit(s)\n")
                if result.symbols:
                    print(f"  Symbols:")
                    for s in result.symbols[:limit]:
                        print(f"    {s.kind:10s} {s.name:35s} {s.file}:{s.line}")
                if result.routes:
                    print(f"  Routes:")
                    for r in result.routes[:limit]:
                        print(f"    {r.method:8s} {r.path}")
                if result.public_api:
                    print(f"  Functions:")
                    for sig in result.public_api[:limit]:
                        print(f"    {sig}")
                if result.is_empty():
                    print(f"  No results. Try: ccc query --type symbol {term}")
        return 0

    if args.command == "align":
        from .alignment import run_alignment
        context_dir = Path(getattr(args, "context_dir", ".llm-context"))
        pkml_path = Path(args.pkml) if getattr(args, "pkml", None) else None
        fmt = getattr(args, "format", "human")

        if not context_dir.exists():
            print(f"\n  Error: {context_dir} not found. Run `ccc` first.")
            return 1

        report, output = run_alignment(context_dir, pkml_path, fmt)
        print(output)
        return 1 if report.errors else 0

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
