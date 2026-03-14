"""
Main context generator orchestrator.

Performance architecture:
  1. FileIndex    — single filesystem scan shared by all generators
  2. HashCache    — mtime-gated hash cache for fast incremental checks
  3. ThreadPool   — independent generators run in parallel
  4. Streaming    — framework detection reads line-by-line, stops early
"""
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

from .config import load_config
from .file_index import FileIndex, HashCache
from .manifest import SmartUpdater
from .models import ProjectInfo
from .security.manager import SecurityManager
from .generators.tree import TreeGenerator
from .generators.schemas import SchemaGenerator
from .generators.api import APIGenerator
from .generators.dependencies import DependencyGenerator
from .generators.symbols import SymbolIndexGenerator
from .utils.files import safe_read_text, safe_write_text, EXCLUDE_DIRS
from .utils.formatting import get_timestamp, human_readable_size

try:
    from . import VERSION
except ImportError:
    VERSION = "0.1.0"


# ── Framework detection helpers ───────────────────────────────────────────────

FRAMEWORK_INDICATORS: Dict[str, List[str]] = {
    "fastapi":    ["fastapi", "from fastapi"],
    "django":     ["django", "django_settings_module"],
    "flask":      ["from flask", "flask.flask"],
    "sqlalchemy": ["sqlalchemy", "from sqlalchemy"],
    "express":    ["require('express')", 'require("express")'],
    "nextjs":     ["from 'next'", 'from "next"', "next.config"],
    "nestjs":     ["@nestjs/", "@module(", "@controller("],
    "react":      ["from 'react'", 'from "react"'],
    "vue":        ["from 'vue'", 'from "vue"', "createapp("],
    "actix":      ["actix-web", "use actix_web"],
    "axum":       ["use axum", "axum::router"],
    "gin":        ["github.com/gin-gonic/gin"],
    "fiber":      ["github.com/gofiber/fiber"],
}

DEP_FILES = [
    "requirements.txt", "pyproject.toml", "package.json",
    "Cargo.toml", "go.mod", "Gemfile",
]


def _file_contains_any(path: Path, indicators: List[str]) -> bool:
    """Stream a file line-by-line and return True on first indicator match."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                lower = line.lower()
                for indicator in indicators:
                    if indicator in lower:
                        return True
    except Exception:
        pass
    return False


class ProjectDetector:
    """
    Detect project type, languages, and framework.

    Uses FileIndex for language detection (no extra scan).
    Uses streaming line-by-line reads for framework detection.
    """

    def __init__(self, root: Path, file_index: FileIndex):
        self.root = root
        self.index = file_index

    def detect(self) -> ProjectInfo:
        info = ProjectInfo(root=self.root)
        info.name = self.root.name
        info.languages = self.index.detect_languages()
        self._detect_from_configs(info)
        info.framework = self._detect_framework()
        info.has_docker = self._has_docker()
        info.has_ci = self._has_ci()
        info.has_tests = self._has_tests()
        return info

    def _detect_from_configs(self, info: ProjectInfo) -> None:
        pyproject = self.root / "pyproject.toml"
        if pyproject.exists():
            info.package_manager = "poetry/pip"
            content = safe_read_text(pyproject) or ""
            m = re.search(r'description\s*=\s*"([^"]*)"', content)
            if m:
                info.description = m.group(1)
            m = re.search(r'python\s*=\s*"([^"]*)"', content)
            if m:
                info.python_version = m.group(1)

        package_json = self.root / "package.json"
        if package_json.exists():
            info.package_manager = "npm/yarn"
            content = safe_read_text(package_json)
            if content:
                try:
                    pkg = json.loads(content)
                    info.description = pkg.get("description", "")
                    if pkg.get("main"):
                        info.entry_points.append(pkg["main"])
                except Exception:
                    pass

        if (self.root / "Cargo.toml").exists():
            info.package_manager = "cargo"
        if (self.root / "go.mod").exists():
            info.package_manager = "go modules"

    def _detect_framework(self) -> str:
        """
        Streaming framework detection.

        Checks dependency manifests first (cheap), then scans source files
        line-by-line stopping as soon as an indicator is found.
        """
        detected = []

        # 1. Cheap pass: dependency files only
        dep_candidates = [self.root / f for f in DEP_FILES if (self.root / f).exists()]
        for framework, indicators in FRAMEWORK_INDICATORS.items():
            for dep_file in dep_candidates:
                if _file_contains_any(dep_file, indicators):
                    detected.append(framework)
                    break

        # 2. Source file pass for anything not found in deps (limit to 60 files)
        already_found = set(detected)
        remaining = {
            fw: ind for fw, ind in FRAMEWORK_INDICATORS.items()
            if fw not in already_found
        }
        if remaining:
            # Prioritise smaller files for speed
            candidates = sorted(
                self.index.all_files(), key=lambda f: f.size
            )[:60]
            for framework, indicators in remaining.items():
                for fi in candidates:
                    if _file_contains_any(fi.path, indicators):
                        detected.append(framework)
                        break

        return ", ".join(detected) if detected else "unknown"

    def _has_docker(self) -> bool:
        return any(
            (self.root / f).exists()
            for f in ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"]
        )

    def _has_ci(self) -> bool:
        return (
            (self.root / ".github" / "workflows").exists()
            or (self.root / ".gitlab-ci.yml").exists()
            or (self.root / "Jenkinsfile").exists()
            or (self.root / ".circleci").exists()
        )

    def _has_tests(self) -> bool:
        return any(
            (self.root / d).exists()
            for d in ["tests", "test", "__tests__", "spec"]
        )


# ── Main orchestrator ─────────────────────────────────────────────────────────

class LLMContextGenerator:
    """
    Main orchestrator for single-repository context generation.

    Performance characteristics:
    - Single filesystem scan via FileIndex
    - Mtime-gated hash cache via HashCache
    - Independent generators run in parallel via ThreadPoolExecutor
    - Framework detection streams files line-by-line
    """

    def __init__(
        self,
        root: Path,
        config: Optional[dict] = None,
        quick_mode: bool = False,
        force: bool = False,
    ):
        self.root = root
        self.config = config or load_config(self.root)
        self.output_dir = self.root / self.config["output_dir"]
        self.quick_mode = quick_mode
        self.updater = SmartUpdater(self.root, self.config, force=force)
        self.security = SecurityManager(self.root, self.config)

    def generate(self) -> None:
        if self.quick_mode:
            mode = "Quick update"
        elif self.updater.force:
            mode = "Force regeneration"
        elif self.updater.old_manifest:
            mode = "Incremental update"
        else:
            mode = "Full generation"

        print("")
        print("=" * 60)
        print(f"  CCC — Code Context Compiler v{VERSION}")
        print(f"  Project: {self.root}")
        print(f"  Mode:    {mode}")
        print(f"  Security:{self.security.mode}")
        print("=" * 60)
        print("")

        # ── Step 1: Single filesystem scan ────────────────────────────────────
        print("-> Building file index...")
        file_index = FileIndex(self.root, EXCLUDE_DIRS).build()
        stats = file_index.stats()
        print(f"   {stats['total_files']} files indexed")

        hash_cache = HashCache(self.root)

        # ── Step 2: Project detection (uses index, no extra scan) ─────────────
        print("-> Detecting project type...")
        detector = ProjectDetector(self.root, file_index)
        project = detector.detect()
        print(f"   Name:      {project.name}")
        print(f"   Languages: {', '.join(project.languages) or 'unknown'}")
        print(f"   Framework: {project.framework}")
        if self.updater.old_manifest:
            print(f"   Last run:  {self.updater.old_manifest.generated_at}")
        print("")

        self.output_dir.mkdir(parents=True, exist_ok=True)

        gen_config = dict(self.config["generate"])
        if self.quick_mode:
            gen_config["module_summaries"] = False
            gen_config["db_schema"] = False

        # ── Step 3: Parallel generation ───────────────────────────────────────
        # Tasks that are independent of each other run concurrently.
        # Sequential tasks (env, deps copy, git, scaffolds) run after.
        parallel_tasks = []
        if gen_config.get("tree"):
            parallel_tasks.append(("tree", self._generate_tree, (file_index,)))
        if gen_config.get("schemas"):
            parallel_tasks.append(("schemas", self._generate_schemas, (project, file_index)))
        if gen_config.get("routes"):
            parallel_tasks.append(("routes", self._generate_routes, (project, file_index)))
        if gen_config.get("public_api"):
            parallel_tasks.append(("public_api", self._generate_public_api, (project, file_index)))
        if gen_config.get("dependencies"):
            parallel_tasks.append(("deps", self._generate_dependencies, (project, file_index, gen_config)))
        if gen_config.get("symbol_index", True):
            parallel_tasks.append(("symbols", self._generate_symbols, (project, file_index)))

        print(f"-> Running {len(parallel_tasks)} generators in parallel...")
        max_workers = min(len(parallel_tasks), 6)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(fn, *args): name
                for name, fn, args in parallel_tasks
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    print(f"   Warning: {name} failed — {exc}")

        # ── Step 4: Sequential tasks ──────────────────────────────────────────
        if gen_config.get("env_shape"):
            self._generate_env_shape()
        self._copy_dependency_files()
        if gen_config.get("recent_activity"):
            self._generate_recent_activity()
        if gen_config.get("external_dependencies", True):
            self._generate_external_dependencies(project)
        if gen_config.get("claude_md_scaffold"):
            self._generate_llm_md(project)
        if gen_config.get("architecture_md_scaffold"):
            self._generate_architecture_md(project)

        # ── Step 5: Persist ───────────────────────────────────────────────────
        hash_cache.save()
        self.updater.new_manifest.save(self.root)
        self.security.log_audit("generate", {"mode": mode})

        print("")
        print("=" * 60)
        print(f"  Done. Context in: {self.output_dir}")
        self.updater.print_summary()

    # ── Write helper ──────────────────────────────────────────────────────────

    def _write(self, filename: str, content: str) -> None:
        if filename.startswith("../"):
            path = (self.output_dir / filename).resolve()
        else:
            path = self.output_dir / filename
        safe_write_text(path, content)

    # ── Parallel generator methods ────────────────────────────────────────────

    def _generate_tree(self, file_index: FileIndex) -> None:
        should_regen, reason = self.updater.should_regenerate("tree.txt")
        if should_regen:
            print(f"   tree.txt — generating ({reason})")
            gen = TreeGenerator(self.root, self.config, file_index)
            content, sources = gen.generate()
            self._write("tree.txt", content)
            self.updater.mark_generated("tree.txt", content, sources)
        else:
            print(f"   tree.txt — {reason}")
            self.updater.mark_skipped("tree.txt")

    def _generate_schemas(self, project: ProjectInfo, file_index: FileIndex) -> None:
        gen = SchemaGenerator(self.root, self.config, file_index)
        all_schemas = gen.generate_all()
        for filename, (content, sources) in all_schemas.items():
            if not content.strip():
                continue
            should_regen, reason = self.updater.should_regenerate(filename, sources)
            if should_regen:
                print(f"   {filename} — generating ({reason})")
                self._write(filename, content)
                self.updater.mark_generated(filename, content, sources)
            else:
                print(f"   {filename} — {reason}")
                self.updater.mark_skipped(filename)

    def _generate_routes(self, project: ProjectInfo, file_index: FileIndex) -> None:
        gen = APIGenerator(self.root, self.config, file_index, project.framework)
        content, sources = gen.generate_routes()
        if content:
            should_regen, reason = self.updater.should_regenerate("routes.txt", sources)
            if should_regen:
                print(f"   routes.txt — generating ({reason})")
                self._write("routes.txt", content)
                self.updater.mark_generated("routes.txt", content, sources)
            else:
                print(f"   routes.txt — {reason}")
                self.updater.mark_skipped("routes.txt")

    def _generate_public_api(self, project: ProjectInfo, file_index: FileIndex) -> None:
        gen = APIGenerator(self.root, self.config, file_index, project.framework)
        content, sources = gen.generate_public_api()
        if content:
            should_regen, reason = self.updater.should_regenerate("public-api.txt", sources)
            if should_regen:
                print(f"   public-api.txt — generating ({reason})")
                self._write("public-api.txt", content)
                self.updater.mark_generated("public-api.txt", content, sources)
            else:
                print(f"   public-api.txt — {reason}")
                self.updater.mark_skipped("public-api.txt")

    def _generate_dependencies(
        self, project: ProjectInfo, file_index: FileIndex, gen_config: dict
    ) -> None:
        gen = DependencyGenerator(self.root, self.config, file_index)
        content, sources = gen.generate()
        if content:
            should_regen, reason = self.updater.should_regenerate(
                "dependency-graph.txt", sources
            )
            if should_regen:
                print(f"   dependency-graph.txt — generating ({reason})")
                self._write("dependency-graph.txt", content)
                self.updater.mark_generated("dependency-graph.txt", content, sources)
                if gen_config.get("dependency_graph_mermaid"):
                    mermaid = gen.generate_mermaid(content)
                    self._write("dependency-graph.md", mermaid)
                    self.updater.mark_generated("dependency-graph.md", mermaid, sources)
            else:
                print(f"   dependency-graph.txt — {reason}")
                self.updater.mark_skipped("dependency-graph.txt")
                if gen_config.get("dependency_graph_mermaid"):
                    self.updater.mark_skipped("dependency-graph.md")

    def _generate_symbols(self, project: ProjectInfo, file_index: FileIndex) -> None:
        gen = SymbolIndexGenerator(self.root, self.config, file_index)
        sources = (
            file_index.by_extension(".py")
            + file_index.by_extension(".ts", ".tsx")
        )
        source_paths = [fi.path for fi in sources]
        should_regen, reason = self.updater.should_regenerate(
            "symbol-index.json", source_paths
        )
        if should_regen:
            print(f"   symbol-index.json — generating ({reason})")
            content, src_files = gen.generate()
            self._write("symbol-index.json", content)
            self.updater.mark_generated("symbol-index.json", content, src_files)
        else:
            print(f"   symbol-index.json — {reason}")
            self.updater.mark_skipped("symbol-index.json")

    # ── Sequential tasks ──────────────────────────────────────────────────────

    def _generate_env_shape(self) -> None:
        for env_file in [".env.example", ".env.template", ".env.sample"]:
            env_path = self.root / env_file
            if env_path.exists():
                should_regen, reason = self.updater.should_regenerate(
                    "env-shape.txt", [env_path]
                )
                if should_regen:
                    print(f"   env-shape.txt — generating ({reason})")
                    content = self.security.redact_content(
                        safe_read_text(env_path) or ""
                    )
                    self._write("env-shape.txt", content)
                    self.updater.mark_generated("env-shape.txt", content, [env_path])
                else:
                    print(f"   env-shape.txt — {reason}")
                    self.updater.mark_skipped("env-shape.txt")
                break

    def _copy_dependency_files(self) -> None:
        for dep_file in DEP_FILES:
            dep_path = self.root / dep_file
            if dep_path.exists():
                should_regen, reason = self.updater.should_regenerate(
                    dep_file, [dep_path]
                )
                if should_regen:
                    print(f"   {dep_file} — copying ({reason})")
                    content = safe_read_text(dep_path) or ""
                    self._write(dep_file, content)
                    self.updater.mark_generated(dep_file, content, [dep_path])
                else:
                    self.updater.mark_skipped(dep_file)

    def _generate_recent_activity(self) -> None:
        print("   recent git activity — capturing")
        try:
            for cmd, out_file in [
                (["git", "log", "--oneline", "-20"], "recent-commits.txt"),
                (["git", "diff", "--stat", "HEAD~5"], "recent-changes.txt"),
            ]:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, cwd=self.root
                )
                if result.returncode == 0 and result.stdout:
                    self._write(out_file, result.stdout)
                    self.updater.mark_generated(out_file, result.stdout)
        except Exception:
            pass  # Not a git repo or git not installed

    def _generate_external_dependencies(self, project: ProjectInfo) -> None:
        """Bridge to ExternalDependencyDetector in the standalone script."""
        try:
            import importlib.util
            import ccc
            script_path = Path(ccc.__file__).parent.parent / "llm-context-setup.py"
            if script_path.exists():
                spec = importlib.util.spec_from_file_location("_llm_setup", script_path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                detector = mod.ExternalDependencyDetector(
                    self.root, project.languages, project.framework
                )
                should_regen, reason = self.updater.should_regenerate(
                    "external-dependencies.json"
                )
                if should_regen:
                    print(f"   external-dependencies.json — generating ({reason})")
                    deps = detector.detect()
                    content = json.dumps(deps, indent=2)
                    self._write("external-dependencies.json", content)
                    self.updater.mark_generated(
                        "external-dependencies.json", content, []
                    )
                else:
                    print(f"   external-dependencies.json — {reason}")
                    self.updater.mark_skipped("external-dependencies.json")
            else:
                print("   external-dependencies.json — skipped (script not found)")
        except Exception as e:
            print(f"   external-dependencies.json — skipped ({e})")

    def _generate_llm_md(self, project: ProjectInfo) -> None:
        llm_path = self.root / "LLM.md"
        should_regen, reason = self.updater.should_regenerate("../LLM.md")
        if should_regen:
            print(f"   LLM.md — generating scaffold ({reason})")
            content = _llm_md_scaffold(project)
            safe_write_text(llm_path, content)
            self.updater.mark_generated("../LLM.md", content, is_new=True)
        else:
            print(f"   LLM.md — {reason}")
            self.updater.mark_skipped("../LLM.md")

    def _generate_architecture_md(self, project: ProjectInfo) -> None:
        arch_path = self.root / "ARCHITECTURE.md"
        should_regen, reason = self.updater.should_regenerate("../ARCHITECTURE.md")
        if should_regen:
            print(f"   ARCHITECTURE.md — generating scaffold ({reason})")
            content = _architecture_md_scaffold(project)
            safe_write_text(arch_path, content)
            self.updater.mark_generated("../ARCHITECTURE.md", content, is_new=True)
        else:
            print(f"   ARCHITECTURE.md — {reason}")
            self.updater.mark_skipped("../ARCHITECTURE.md")


# ── Scaffold templates ────────────────────────────────────────────────────────

def _llm_md_scaffold(project: ProjectInfo) -> str:
    langs = ", ".join(project.languages) if project.languages else "unknown"
    return f"""# {project.name} — LLM Context

> Auto-generated by CCC. Edit this file to add project-specific guidance.

## Project Overview

- **Languages**: {langs}
- **Framework**: {project.framework}
- **Description**: {project.description or "TODO: add description"}

## Key Conventions

- TODO: document coding conventions
- TODO: document naming conventions
- TODO: document architectural patterns

## Important Areas

- TODO: list critical/dangerous files or modules
- TODO: list frequently changed areas
- TODO: list known gotchas

## Generated Context Files

See `.llm-context/` for auto-extracted context:
- `tree.txt` — file structure
- `routes.txt` — API routes
- `schemas-extracted.*` — type definitions
- `dependency-graph.*` — internal imports
- `symbol-index.json` — symbol navigation map
- `external-dependencies.json` — service boundary contracts
"""


def _architecture_md_scaffold(project: ProjectInfo) -> str:
    langs = ", ".join(project.languages) if project.languages else "unknown"
    return f"""# {project.name} — Architecture

> Auto-generated by CCC. Edit this file to describe the system architecture.

## Overview

- **Languages**: {langs}
- **Framework**: {project.framework}

## Components

- TODO: list major components/modules

## Data Flow

- TODO: describe how data moves through the system

## External Dependencies

- TODO: list external services, APIs, databases

## Deployment

- {"Docker: detected" if project.has_docker else "Docker: not detected"}
- {"CI/CD: detected" if project.has_ci else "CI/CD: not detected"}
"""