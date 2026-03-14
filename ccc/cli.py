"""Main CLI with workspace support."""
import argparse
import json
import sys
from pathlib import Path

from .generator import LLMContextGenerator
from .workspace.cli import add_workspace_commands, workspace_main
from .doctor import DiagnosticTool
from .watch import watch_mode
from . import VERSION
from .config import get_default_config, load_config, deep_merge
from .security.manager import SecurityManager
from .utils.files import safe_read_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LLM Context Generator - Generate context files for LLMs",
    )

    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--quick-update", "-q", action="store_true")
    parser.add_argument("--force", "-f", action="store_true")
    parser.add_argument("--watch", "-w", action="store_true")
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


def main():
    parser = build_parser()
    args = parser.parse_args()

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

    print("ccc package entry point is active.")
    print("Next migration step: move generator/orchestrator into ccc.generator")
    print(f"Project root: {root}")
    return 0
