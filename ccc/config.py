import json
from pathlib import Path

from .utils.files import safe_read_text

MANIFEST_VERSION = "4"


def get_default_config():
    """Return default configuration dictionary."""
    return {
        "version": MANIFEST_VERSION,
        "output_dir": ".llm-context",
        "security": {
            "mode": "offline",
            "redact_secrets": True,
            "audit_log": True,
        },
        "max_file_size_kb": 100,
        "max_tree_depth": 6,
        "max_files_in_tree": 500,
        "generate": {
            "tree": True,
            "schemas": True,
            "public_api": True,
            "routes": True,
            "dependencies": True,
            "dependency_graph_mermaid": True,
            "db_schema": True,
            "api_contract": True,
            "env_shape": True,
            "recent_activity": True,
            "claude_md_scaffold": True,
            "architecture_md_scaffold": True,
            "module_summaries": False,
            "symbol_index": True,
            "entry_points": True,
            "external_dependencies": True,
        },
        "llm_summaries": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-20250514",
            "max_modules": 30,
            "min_file_size_bytes": 300,
        },
        "update_strategies": {
            "tree.txt": "always",
            "recent-commits.txt": "always",
            "recent-changes.txt": "always",
            "schemas-extracted.py": "if-changed",
            "types-extracted.ts": "if-changed",
            "rust-types.rs": "if-changed",
            "go-types.go": "if-changed",
            "csharp-types.cs": "if-changed",
            "public-api.txt": "if-changed",
            "routes.txt": "if-changed",
            "dependency-graph.txt": "if-changed",
            "dependency-graph.md": "if-changed",
            "db-schema.txt": "if-changed",
            "api-contract.md": "if-changed",
            "symbol-index.json": "if-changed",
            "entry-points.json": "if-changed",
            "external-dependencies.json": "if-changed",
            "modules/*.md": "if-changed",
            "../CLAUDE.md": "if-missing",
            "../ARCHITECTURE.md": "if-missing",
        },
    }


def deep_merge(base: dict, override: dict) -> None:
    """Deep merge override into base dictionary."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = value


def load_config(root: Path) -> dict:
    """Load configuration from file or return defaults."""
    config = get_default_config()

    yaml_config = root / "llm-context.yml"
    if yaml_config.exists():
        try:
            import yaml
            content = safe_read_text(yaml_config)
            if content:
                user_config = yaml.safe_load(content)
                if user_config:
                    deep_merge(config, user_config)
                print(f"  Loaded config from {yaml_config}")
        except ImportError:
            pass
        except Exception as e:
            print(f"  Warning: Could not parse {yaml_config}: {e}")
        return config

    json_config = root / "llm-context.json"
    if json_config.exists():
        try:
            content = safe_read_text(json_config)
            if content:
                user_config = json.loads(content)
                deep_merge(config, user_config)
                print(f"  Loaded config from {json_config}")
        except Exception as e:
            print(f"  Warning: Could not parse {json_config}: {e}")

    return config
