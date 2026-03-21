"""
Service Index Generator — builds workspace-context/service-index.json

This is the single cached artifact that enables workspace queries without
requiring all repos to be cloned locally. Commit it to the workspace repo.

Schema:
{
  "workspace": "platform-name",
  "generated": "2026-03-20T...",
  "version": "1",
  "services": {
    "auth-service": {
      "name": "auth-service",
      "type": "backend-api",
      "tags": ["auth", "security", "core"],
      "description": "...",
      "languages": ["typescript"],
      "depends_on": ["shared-types"],
      "exposes": {
        "api": ["POST /auth/login", "POST /auth/refresh"],
        "events": ["user.authenticated"],
        "types": ["AuthToken", "UserSession"]
      },
      "context_generated": "2026-03-19T...",   # when ccc last ran on this repo
      "path": "./auth-service",                 # relative path in workspace
      "has_context": true                       # whether .llm-context/ exists
    }
  },
  "all_tags": ["auth", "core", "security", ...],
  "all_services": ["auth-service", "user-service", ...]
}
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import ServiceConfig
from ..utils.files import safe_read_text, safe_write_text
from ..utils.formatting import get_timestamp
from .manifest import WorkspaceManifest


def _load_external_deps(service: ServiceConfig) -> Optional[Dict]:
    """Load external-dependencies.json from a service's .llm-context/."""
    ext_file = service.path / ".llm-context" / "external-dependencies.json"
    if not ext_file.exists():
        return None
    content = safe_read_text(ext_file)
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _load_manifest_json(service: ServiceConfig) -> Optional[Dict]:
    """Load generation manifest to get context timestamp."""
    manifest_file = service.path / ".llm-context" / "manifest.json"
    if not manifest_file.exists():
        return None
    content = safe_read_text(manifest_file)
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _detect_languages(service: ServiceConfig) -> List[str]:
    """Detect languages from repo if not already in external deps."""
    langs = []
    if not service.path.exists():
        return langs
    if any(service.path.rglob("*.py")):
        langs.append("python")
    if any(service.path.rglob("*.ts")):
        langs.append("typescript")
    elif any(service.path.rglob("*.js")):
        langs.append("javascript")
    if any(service.path.rglob("*.go")):
        langs.append("go")
    if any(service.path.rglob("*.rs")):
        langs.append("rust")
    return langs[:2]


def build_service_index(
    manifest: WorkspaceManifest,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Build workspace-context/service-index.json from all services in the manifest.

    Reads each service's .llm-context/external-dependencies.json if available,
    falls back to manifest data only if not. This means it works even when
    not all repos are cloned — it just has less data for those services.

    Returns:
        Path to written service-index.json
    """
    out_dir = output_dir or (manifest.root / "workspace-context")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "service-index.json"

    all_tags: set = set()
    services_data: Dict[str, Any] = {}

    for name, service in manifest.services.items():
        all_tags.update(service.tags)

        # Start with manifest data (always available)
        entry: Dict[str, Any] = {
            "name": name,
            "type": service.service_type,
            "tags": service.tags,
            "description": service.description,
            "depends_on": service.depends_on,
            "path": str(service.path.relative_to(manifest.root))
                    if service.path.is_relative_to(manifest.root)
                    else str(service.path),
            "has_context": (service.path / ".llm-context").exists(),
            "exposes": {"api": [], "events": [], "types": []},
            "languages": [],
            "context_generated": None,
            "framework": None,
        }

        # Enrich with generated context if available
        ext_deps = _load_external_deps(service)
        if ext_deps:
            entry["exposes"] = ext_deps.get("exposes", entry["exposes"])
            # Merge detected languages
            detected_langs = ext_deps.get("languages", [])
            if detected_langs:
                entry["languages"] = detected_langs

            # Pull in framework if detected
            if ext_deps.get("framework"):
                entry["framework"] = ext_deps["framework"]

            # Pull detected tags from external deps and merge
            detected_tags = ext_deps.get("tags", [])
            if detected_tags:
                merged = list(dict.fromkeys(service.tags + detected_tags))
                entry["tags"] = merged
                all_tags.update(detected_tags)

        # Detect languages from file system if not already known
        if not entry["languages"] and service.path.exists():
            entry["languages"] = _detect_languages(service)

        # Get context generation timestamp
        mf = _load_manifest_json(service)
        if mf:
            entry["context_generated"] = mf.get("generated_at") or mf.get("timestamp")

        services_data[name] = entry

    index: Dict[str, Any] = {
        "workspace": manifest.name,
        "generated": get_timestamp(),
        "version": manifest.version,
        "services": services_data,
        "all_tags": sorted(all_tags),
        "all_services": sorted(services_data.keys()),
    }

    content = json.dumps(index, indent=2, default=str)
    safe_write_text(out_file, content)

    return out_file