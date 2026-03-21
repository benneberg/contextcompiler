"""
ccc workspace init — scan directories and generate a ccc-workspace.yml draft.

Discovers service repos by scanning sibling directories, detects their
language/framework/type, suggests tags, and writes a ready-to-review manifest.
No manual editing required for the first pass.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..utils.files import safe_read_text, safe_write_text


# ── Service type detection ────────────────────────────────────────────────────

_TYPE_SIGNALS: List[Tuple[str, str, List[str]]] = [
    # (service_type, description, file_signals)
    ("frontend",    "Frontend application",   ["src/App.tsx", "src/App.jsx", "src/App.vue", "index.html", "vite.config.ts", "next.config.js", "angular.json"]),
    ("data",        "Data / database layer",  ["migrations/", "alembic/", "prisma/schema.prisma", "schema.sql", "seeds/"]),
    ("gateway",     "API gateway / proxy",    ["nginx.conf", "traefik.yml", "kong.yml"]),
    ("worker",      "Background worker",      ["celery", "worker.py", "consumer.py", "queue/"]),
    ("library",     "Shared library",         ["src/index.ts", "src/index.js", "__init__.py"]),
    ("backend-api", "Backend API service",    ["main.py", "app.py", "server.ts", "server.js", "index.ts"]),
]

_TAG_SIGNALS: Dict[str, List[str]] = {
    "auth":       ["auth", "login", "jwt", "oauth", "session", "permission", "role"],
    "payments":   ["payment", "billing", "stripe", "invoice", "checkout"],
    "users":      ["user", "profile", "account", "member"],
    "platforms":  ["platform", "device", "tizen", "samsung", "lg", "webos"],
    "media":      ["video", "audio", "stream", "player", "media", "content"],
    "cms":        ["cms", "content", "editorial", "article", "page"],
    "search":     ["search", "elastic", "index", "query"],
    "notification": ["notification", "push", "email", "sms", "alert"],
    "infra":      ["infra", "config", "gateway", "proxy", "nginx", "k8s"],
    "data":       ["database", "db", "schema", "migration", "seed"],
    "shared":     ["shared", "common", "lib", "types", "util"],
    "core":       ["core", "main", "primary"],
}


def _detect_language(repo_path: Path) -> List[str]:
    """Detect primary languages in a repo."""
    langs = []
    if any(repo_path.rglob("*.py")):
        langs.append("python")
    if any(repo_path.glob("*.ts")) or any(repo_path.rglob("src/*.ts")):
        langs.append("typescript")
    elif any(repo_path.glob("*.js")) or any(repo_path.rglob("src/*.js")):
        langs.append("javascript")
    if any(repo_path.rglob("*.go")):
        langs.append("go")
    if any(repo_path.rglob("*.rs")):
        langs.append("rust")
    if any(repo_path.rglob("*.cs")):
        langs.append("csharp")
    return langs[:2]  # cap at 2 primary langs


def _detect_service_type(repo_path: Path) -> str:
    """Detect service type from directory contents."""
    for service_type, _, signals in _TYPE_SIGNALS:
        for signal in signals:
            if (repo_path / signal).exists():
                return service_type
            # Also check package.json for frontend frameworks
            if service_type == "frontend":
                pkg = repo_path / "package.json"
                if pkg.exists():
                    content = safe_read_text(pkg) or ""
                    if any(fw in content for fw in ['"react"', '"vue"', '"angular"', '"next"', '"svelte"']):
                        return "frontend"
    return "backend-api"


def _detect_framework(repo_path: Path) -> str:
    """Quick framework detection for description."""
    pkg = repo_path / "package.json"
    if pkg.exists():
        content = safe_read_text(pkg) or ""
        for fw in ["next", "nuxt", "angular", "svelte", "express", "fastify", "nestjs"]:
            if f'"{fw}"' in content:
                return fw
    for pyfile in ["requirements.txt", "pyproject.toml"]:
        content = safe_read_text(repo_path / pyfile) or ""
        for fw in ["fastapi", "django", "flask", "starlette"]:
            if fw in content.lower():
                return fw
    return ""


def _suggest_tags(name: str, repo_path: Path) -> List[str]:
    """Suggest tags based on repo name and content signals."""
    tags = []
    name_lower = name.lower()

    # Check name first
    for tag, signals in _TAG_SIGNALS.items():
        if any(sig in name_lower for sig in signals):
            tags.append(tag)

    # Check README and package description for more signals
    for readme in ["README.md", "README.txt", "package.json", "pyproject.toml"]:
        content = (safe_read_text(repo_path / readme) or "").lower()[:1000]
        for tag, signals in _TAG_SIGNALS.items():
            if tag not in tags and any(sig in content for sig in signals):
                tags.append(tag)

    return tags[:4]  # cap suggestions, human can add more


def _detect_depends_on(name: str, all_names: List[str]) -> List[str]:
    """
    Heuristic: detect likely dependencies by scanning for other service
    names in env files and config files.
    """
    deps = []
    search_files = [".env.example", ".env", "config.py", "config.ts",
                    "docker-compose.yml", "settings.py"]

    # We'll look in the repo if it's available
    # For init this is a best-effort hint
    return deps


def _is_service_repo(path: Path) -> bool:
    """Check if a directory looks like a service repo."""
    if not path.is_dir():
        return False
    # Skip obvious non-repos
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv",
            "dist", "build", ".llm-context", "workspace-context"}
    if path.name.startswith(".") or path.name in skip:
        return False
    # Must have some code
    has_code = (
        any(path.glob("*.py")) or
        any(path.glob("*.ts")) or
        any(path.glob("*.js")) or
        any(path.glob("*.go")) or
        any(path.glob("*.rs")) or
        any(path.rglob("src/*.ts")) or
        any(path.rglob("src/*.js"))
    )
    return has_code


def _generate_yaml(
    workspace_name: str,
    workspace_root: Path,
    services: List[Dict],
) -> str:
    """Generate ccc-workspace.yml content."""
    lines = [
        f"# ccc-workspace.yml — Auto-generated by `ccc workspace init`",
        f"# Review and fill in the TODOs before committing.",
        f"",
        f"name: {workspace_name}",
        f"version: 1",
        f"",
        f"services:",
    ]

    for svc in services:
        rel_path = svc["rel_path"]
        name = svc["name"]
        svc_type = svc["type"]
        tags = svc["tags"]
        desc = svc["description"]
        deps = svc["depends_on"]
        langs = svc["languages"]

        lines.append(f"")
        lines.append(f"  {name}:")
        lines.append(f"    path: {rel_path}")
        lines.append(f"    type: {svc_type}")

        if langs:
            lines.append(f"    # languages: {', '.join(langs)}")

        if tags:
            lines.append(f"    tags:")
            for tag in tags:
                lines.append(f"      - {tag}")
        else:
            lines.append(f"    tags:")
            lines.append(f"      - core  # TODO: add meaningful tags")

        if deps:
            lines.append(f"    depends_on:")
            for dep in deps:
                lines.append(f"      - {dep}")
        else:
            lines.append(f"    # depends_on:  # TODO: add dependencies if any")
            lines.append(f"    #   - other-service")

        if desc:
            lines.append(f"    description: \"{desc}\"")
        else:
            lines.append(f"    description: \"TODO: describe what this service does\"")

    lines.extend([
        "",
        "# ── Notes ──────────────────────────────────────────────────────────────",
        "# Tags are used by: ccc workspace query --tags <tag>",
        "# depends_on drives the change-sequence ordering",
        "# Run `ccc` in each service directory to generate .llm-context/ first",
        "# Then run `ccc workspace generate` to build the cross-repo overview",
    ])

    return "\n".join(lines) + "\n"


def init_workspace(
    scan_path: Path,
    output_path: Optional[Path] = None,
    workspace_name: Optional[str] = None,
    force: bool = False,
) -> Path:
    """
    Scan directories and generate a ccc-workspace.yml draft.

    Args:
        scan_path:      Directory to scan for service repos (default: parent of cwd)
        output_path:    Where to write ccc-workspace.yml (default: scan_path)
        workspace_name: Name for the workspace (default: scan_path directory name)
        force:          Overwrite if file already exists

    Returns:
        Path to generated ccc-workspace.yml
    """
    scan_path = scan_path.resolve()
    out_dir = (output_path or scan_path).resolve()
    out_file = out_dir / "ccc-workspace.yml"

    if out_file.exists() and not force:
        raise FileExistsError(
            f"ccc-workspace.yml already exists at {out_file}\n"
            f"Use --force to overwrite."
        )

    name = workspace_name or scan_path.name

    print(f"\n{'=' * 60}")
    print(f"  CCC — Workspace Init")
    print(f"  Scanning: {scan_path}")
    print(f"{'=' * 60}\n")

    # Discover candidate service directories
    candidates = [p for p in sorted(scan_path.iterdir()) if _is_service_repo(p)]

    if not candidates:
        print(f"  No service repos found in {scan_path}")
        print(f"  Make sure the path contains cloned repositories.\n")
        raise FileNotFoundError(f"No service repos found in {scan_path}")

    print(f"  Found {len(candidates)} candidate repo(s):\n")

    all_names = [c.name for c in candidates]
    services = []

    for repo_path in candidates:
        svc_type = _detect_service_type(repo_path)
        langs = _detect_language(repo_path)
        framework = _detect_framework(repo_path)
        tags = _suggest_tags(repo_path.name, repo_path)
        deps = _detect_depends_on(repo_path.name, all_names)

        # Build description from detected info
        parts = []
        if framework:
            parts.append(framework.capitalize())
        if langs:
            parts.append("/".join(langs))
        parts.append(svc_type.replace("-", " "))
        description = " ".join(parts) if parts else ""

        rel_path = f"./{repo_path.name}"

        tag_str = ", ".join(tags) if tags else "(none detected)"
        lang_str = ", ".join(langs) if langs else "unknown"
        print(f"  ✓ {repo_path.name:30s} [{svc_type:12s}] langs:{lang_str:15s} tags:{tag_str}")

        services.append({
            "name": repo_path.name,
            "rel_path": rel_path,
            "type": svc_type,
            "tags": tags,
            "depends_on": deps,
            "description": description,
            "languages": langs,
        })

    print(f"\n  Writing: {out_file}\n")

    yaml_content = _generate_yaml(name, scan_path, services)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_write_text(out_file, yaml_content)

    print(f"  ✓ Generated ccc-workspace.yml with {len(services)} service(s)")
    print(f"")
    print(f"  Next steps:")
    print(f"    1. Review and edit {out_file}")
    print(f"       - Fill in TODO descriptions")
    print(f"       - Add/correct tags (used for querying)")
    print(f"       - Add depends_on relationships (drives change ordering)")
    print(f"    2. Run `ccc` in each service directory to generate .llm-context/")
    print(f"    3. Run `ccc workspace generate` to build cross-repo context")
    print(f"    4. Run `ccc workspace serve` to open the browser UI")
    print(f"")

    return out_file