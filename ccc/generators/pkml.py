"""
PKML bootstrapper — generates a pkml.json draft from .llm-context/ output.

Reads the generated context files and produces a structured pkml.json
that can be imported into the PKML editor for refinement.

Usage:
  ccc pkml                        # generate pkml.json in current directory
  ccc pkml --output my-product    # custom output path
  ccc pkml --open                 # open in PKML editor after generating

Output: product-knowledge/pkml.json

PKML spec: https://github.com/benneberg/pkml
"""
import json
import re
import subprocess
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils.files import safe_read_text
from ..utils.formatting import get_timestamp


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_context_file(context_dir: Path, filename: str) -> Optional[str]:
    """Read a file from .llm-context/, return None if missing."""
    path = context_dir / filename
    if path.exists():
        return safe_read_text(path)
    return None


def _parse_routes(routes_txt: str) -> List[Dict]:
    """Parse routes.txt into a list of {method, path, file} dicts."""
    routes = []
    current_file = None
    for line in routes_txt.splitlines():
        if line.startswith("##"):
            current_file = line[2:].strip()
        elif line.strip() and not line.startswith("#"):
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                method, path = parts
                routes.append({
                    "method": method.upper(),
                    "path": path,
                    "file": current_file,
                })
    return routes


def _extract_tech_stack(context_dir: Path) -> Dict[str, List[str]]:
    """Infer tech stack from dependency files and generated context."""
    stack: Dict[str, List[str]] = {
        "frontend": [], "backend": [], "databases": [],
        "infrastructure": [], "testing": [], "monitoring": [],
    }

    # requirements.txt → backend Python packages
    req = _read_context_file(context_dir, "requirements.txt")
    if req:
        py_frameworks = {
            "fastapi": "FastAPI", "flask": "Flask", "django": "Django",
            "sqlalchemy": "SQLAlchemy", "pydantic": "Pydantic",
            "celery": "Celery", "redis": "Redis", "pymongo": "MongoDB",
            "psycopg2": "PostgreSQL", "pytest": "pytest",
            "httpx": "httpx", "uvicorn": "Uvicorn",
        }
        for pkg, name in py_frameworks.items():
            if pkg in req.lower():
                category = "backend"
                if pkg in ("pytest",):
                    category = "testing"
                elif pkg in ("psycopg2", "redis", "pymongo", "sqlalchemy"):
                    category = "databases"
                if name not in stack[category]:
                    stack[category].append(name)
        if "python" not in stack["backend"] and req:
            stack["backend"].insert(0, "Python")

    # package.json → frontend/backend JS packages
    pkg_json = _read_context_file(context_dir, "package.json")
    if pkg_json:
        try:
            pkg = json.loads(pkg_json)
            all_deps = {
                **pkg.get("dependencies", {}),
                **pkg.get("devDependencies", {}),
            }
            js_map = {
                "react": ("frontend", "React"),
                "next": ("frontend", "Next.js"),
                "vue": ("frontend", "Vue"),
                "svelte": ("frontend", "Svelte"),
                "express": ("backend", "Express"),
                "fastify": ("backend", "Fastify"),
                "@nestjs/core": ("backend", "NestJS"),
                "prisma": ("databases", "Prisma"),
                "typeorm": ("databases", "TypeORM"),
                "drizzle-orm": ("databases", "Drizzle"),
                "mongoose": ("databases", "MongoDB"),
                "pg": ("databases", "PostgreSQL"),
                "redis": ("databases", "Redis"),
                "jest": ("testing", "Jest"),
                "vitest": ("testing", "Vitest"),
                "playwright": ("testing", "Playwright"),
                "typescript": ("backend", "TypeScript"),
            }
            for dep, (cat, label) in js_map.items():
                if dep in all_deps and label not in stack[cat]:
                    stack[cat].append(label)
        except Exception:
            pass

    # Remove empty categories
    return {k: v for k, v in stack.items() if v}


def _extract_features_from_routes(routes: List[Dict]) -> List[Dict]:
    """Convert route groups into draft features."""
    # Group routes by resource (first path segment)
    groups: Dict[str, List[Dict]] = {}
    for route in routes:
        path = route.get("path", "")
        parts = [p for p in path.split("/") if p and not p.startswith("{") and not p.startswith(":")]
        resource = parts[0] if parts else "root"
        groups.setdefault(resource, []).append(route)

    features = []
    for i, (resource, group_routes) in enumerate(groups.items()):
        methods = sorted(set(r["method"] for r in group_routes))
        feature_id = f"feat_{resource.lower().replace('-', '_')}"
        name = f"{resource.replace('-', ' ').replace('_', ' ').title()} API"
        desc = f"Exposes {len(group_routes)} endpoint(s): {', '.join(methods)}"
        features.append({
            "id": feature_id,
            "name": name,
            "description": desc,
            "user_benefit": f"Allows clients to manage {resource} resources",
            "priority": "primary" if i < 3 else "secondary",
            "evidence": {
                "api_routes": [f"{r['method']} {r['path']}" for r in group_routes[:5]],
            },
        })
    return features[:10]  # cap at 10 draft features


def _extract_features_from_schemas(schemas_txt: str) -> List[Dict]:
    """Extract class/model names from schema files as draft features."""
    features = []
    seen: set = set()

    # Python: class Foo(BaseModel) or @dataclass
    for m in re.finditer(r'^class\s+(\w+)\s*\(', schemas_txt, re.MULTILINE):
        name = m.group(1)
        if name not in seen and not name.startswith("_"):
            seen.add(name)
            features.append({
                "id": f"feat_{name.lower()}",
                "name": name,
                "description": f"TODO: describe the {name} feature",
                "user_benefit": "TODO: describe the user benefit",
                "priority": "secondary",
            })

    # TypeScript: interface Foo or type Foo
    for m in re.finditer(r'^(?:interface|type)\s+(\w+)', schemas_txt, re.MULTILINE):
        name = m.group(1)
        if name not in seen and not name.startswith("_"):
            seen.add(name)

    return features[:8]


def bootstrap_pkml(
    root: Path,
    output_dir: Optional[Path] = None,
    open_editor: bool = False,
) -> Path:
    """
    Generate a pkml.json draft from a repository's .llm-context/ files.

    Returns the path to the generated file.
    """
    context_dir = root / ".llm-context"

    if not context_dir.exists():
        raise FileNotFoundError(
            f"No .llm-context/ found in {root}\n"
            "Run `ccc generate` first to produce context files."
        )

    now = datetime.now(timezone.utc).isoformat()
    project_name = root.name.replace("-", " ").replace("_", " ").title()

    # ── Collect raw context ───────────────────────────────────────────────────
    routes_txt     = _read_context_file(context_dir, "routes.txt") or ""
    schemas_py     = _read_context_file(context_dir, "schemas-extracted.py") or ""
    schemas_ts     = _read_context_file(context_dir, "types-extracted.ts") or ""
    ext_deps_raw   = _read_context_file(context_dir, "external-dependencies.json")
    symbol_raw     = _read_context_file(context_dir, "symbol-index.json")
    commits_txt    = _read_context_file(context_dir, "recent-commits.txt") or ""

    ext_deps: dict = {}
    if ext_deps_raw:
        try:
            ext_deps = json.loads(ext_deps_raw)
        except Exception:
            pass

    # ── Tech stack ────────────────────────────────────────────────────────────
    tech_stack = _extract_tech_stack(context_dir)

    # ── Features ──────────────────────────────────────────────────────────────
    routes = _parse_routes(routes_txt)
    features: List[Dict] = []

    if routes:
        features.extend(_extract_features_from_routes(routes))

    if not features:
        # Fall back to schema-based features
        combined_schemas = schemas_py + "\n" + schemas_ts
        features = _extract_features_from_schemas(combined_schemas)

    if not features:
        features = [{
            "id": "feat_core",
            "name": "Core Functionality",
            "description": "TODO: describe the core feature",
            "user_benefit": "TODO: describe the user benefit",
            "priority": "primary",
        }]

    # ── Categories from ext_deps tags ─────────────────────────────────────────
    categories: List[str] = ext_deps.get("tags", [])
    if not categories:
        # Guess from tech stack
        if tech_stack.get("frontend"):
            categories.append("frontend")
        if tech_stack.get("backend"):
            categories.append("developer-tool")

    # ── Integrations ──────────────────────────────────────────────────────────
    integrations: List[Dict] = []
    for ext_api in ext_deps.get("depends_on", {}).get("external_apis", []):
        integrations.append({
            "id": f"int_{ext_api.lower().replace(' ', '_')}",
            "name": ext_api,
            "category": "external-api",
            "description": f"TODO: describe {ext_api} integration",
            "required": False,
        })

    # ── Workflows (stub one from routes) ──────────────────────────────────────
    workflows: List[Dict] = []
    if routes:
        first_resource = features[0]["name"] if features else "core workflow"
        first_route = routes[0]
        workflows.append({
            "id": "workflow_getting_started",
            "name": "Getting Started",
            "description": f"Basic workflow showing how to use {project_name}",
            "difficulty": "beginner",
            "estimated_time": "5 minutes",
            "steps": [
                {
                    "order": 1,
                    "action": f"Make a {first_route['method']} request to {first_route['path']}",
                    "expected_outcome": "Successful response",
                }
            ],
            "outcome": f"You have successfully interacted with {project_name}",
        })

    # ── Assemble PKML ─────────────────────────────────────────────────────────
    pkml: Dict[str, Any] = {
        "$schema": "https://pkml.dev/schema/v0.1.json",
        "meta": {
            "version": "1.0.0",
            "pkml_version": "0.1.0",
            "last_updated": now,
            "created_at": now,
            "generated_by": "ccc",
            "generated_from": str(root),
        },
        "product": {
            "name": project_name,
            "tagline": f"TODO: one-sentence description of {project_name}",
            "description": f"TODO: 2-3 sentence description of {project_name}",
            "category": categories or ["developer-tool"],
            "repository": ext_deps.get("repository"),
        },
        "features": features,
        "tech_stack": tech_stack,
    }

    if workflows:
        pkml["workflows"] = workflows

    if integrations:
        pkml["integrations"] = integrations

    # Repository info
    if ext_deps.get("exposes", {}).get("api"):
        pkml["product"]["api_base"] = "TODO: your API base URL"

    # ── Write output ──────────────────────────────────────────────────────────
    out_dir = output_dir or (root / "product-knowledge")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "pkml.json"

    out_path.write_text(json.dumps(pkml, indent=2, default=str), encoding="utf-8")

    print(f"  Generated: {out_path}")
    print(f"  Product:   {project_name}")
    print(f"  Features:  {len(features)}")
    print(f"  Routes:    {len(routes)}")
    print(f"  Tech:      {', '.join(v for vals in tech_stack.values() for v in vals)}")
    print()
    print("  Next steps:")
    print("  1. Edit product-knowledge/pkml.json — fill in all TODO fields")
    print("  2. Open in PKML editor: https://github.com/benneberg/pkml")
    print("  3. Publish to the PKML registry")

    if open_editor:
        url = "https://pkml.dev"
        print(f"\n  Opening {url} ...")
        webbrowser.open(url)

    return out_path
