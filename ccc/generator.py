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

from .generators.claude_md import ClaudeMdEnhancer
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
from .generators.entrypoints import EntryPointGenerator
from .generators.database import DatabaseSchemaGenerator
from .generators.contracts import ContractsGenerator
from .generators.external import ExternalDependencyGenerator
from .generators.capabilities import CapabilityGenerator
from .utils.files import safe_read_text, safe_write_text, EXCLUDE_DIRS
from .utils.formatting import get_timestamp, human_readable_size

try:
    from . import VERSION
except ImportError:
    VERSION = "0.1.0"


# ── Framework detection ───────────────────────────────────────────────────────

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
    """Stream a file line-by-line; return True on first indicator match."""
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


# ── Project detection ─────────────────────────────────────────────────────────

class ProjectDetector:
    """Detect project type, languages, and framework using the FileIndex."""

    def __init__(self, root: Path, file_index: FileIndex):
        self.root = root
        self.index = file_index

    def detect(self) -> ProjectInfo:
        info = ProjectInfo(root=self.root)
        info.name = self.root.name
        info.languages = self.index.detect_languages()
        self._detect_from_configs(info)
        info.framework = self._detect_framework()
        info.has_docker = any(
            (self.root / f).exists()
            for f in ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"]
        )
        info.has_ci = (
            (self.root / ".github" / "workflows").exists()
            or (self.root / ".gitlab-ci.yml").exists()
            or (self.root / "Jenkinsfile").exists()
        )
        info.has_tests = any(
            (self.root / d).exists() for d in ["tests", "test", "__tests__", "spec"]
        )
        return info

    def _detect_from_configs(self, info: ProjectInfo) -> None:
        pyproject = self.root / "pyproject.toml"
        if pyproject.exists():
            info.package_manager = "poetry/pip"
            content = safe_read_text(pyproject) or ""
            m = re.search(r'description\s*=\s*"([^"]*)"', content)
            if m:
                info.description = m.group(1)

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
        detected = []
        dep_candidates = [self.root / f for f in DEP_FILES if (self.root / f).exists()]

        for framework, indicators in FRAMEWORK_INDICATORS.items():
            for dep_file in dep_candidates:
                if _file_contains_any(dep_file, indicators):
                    detected.append(framework)
                    break

        already = set(detected)
        remaining = {fw: ind for fw, ind in FRAMEWORK_INDICATORS.items() if fw not in already}
        if remaining:
            candidates = sorted(self.index.all_files(), key=lambda f: f.size)[:60]
            for framework, indicators in remaining.items():
                for fi in candidates:
                    if _file_contains_any(fi.path, indicators):
                        detected.append(framework)
                        break

        return ", ".join(detected) if detected else "unknown"


# ── Main orchestrator ─────────────────────────────────────────────────────────

class LLMContextGenerator:
    """
    Main orchestrator for single-repository context generation.

    - Single filesystem scan (FileIndex)
    - Mtime-gated hash cache (HashCache)
    - Independent generators run in parallel (ThreadPoolExecutor)
    - Streaming framework detection
    - No bridge to standalone script — all generators are in the package
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

        # Step 1: single filesystem scan
        print("-> Building file index...")
        file_index = FileIndex(self.root, EXCLUDE_DIRS).build()
        stats = file_index.stats()
        print(f"   {stats['total_files']} files indexed")

        hash_cache = HashCache(self.root)

        # Step 2: project detection
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

        gc = dict(self.config["generate"])
        if self.quick_mode:
            gc["module_summaries"] = False
            gc["db_schema"] = False

        # Step 3: parallel generation
        parallel = []
        if gc.get("tree"):
            parallel.append(("tree",       self._gen_tree,        (file_index,)))
        if gc.get("schemas"):
            parallel.append(("schemas",    self._gen_schemas,     (project, file_index)))
        if gc.get("routes"):
            parallel.append(("routes",     self._gen_routes,      (project, file_index)))
        if gc.get("public_api"):
            parallel.append(("public_api", self._gen_public_api,  (project, file_index)))
        if gc.get("dependencies"):
            parallel.append(("deps",       self._gen_dependencies,(project, file_index, gc)))
        if gc.get("symbol_index", True):
            parallel.append(("symbols",    self._gen_symbols,     (project, file_index)))
        if gc.get("entry_points"):
            parallel.append(("entries",    self._gen_entrypoints, (file_index,)))
        if gc.get("db_schema"):
            parallel.append(("db_schema",  self._gen_db_schema,   (file_index,)))
        if gc.get("api_contract"):
            parallel.append(("contract",   self._gen_api_contract,()))

        print(f"-> Running {len(parallel)} generators in parallel...")
        with ThreadPoolExecutor(max_workers=min(len(parallel), 6)) as pool:
            futures = {pool.submit(fn, *args): name for name, fn, args in parallel}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    print(f"   Warning: {name} failed — {exc}")

        # Step 4: sequential tasks
        if gc.get("env_shape"):
            self._gen_env_shape()
        self._copy_dep_files()
        if gc.get("recent_activity"):
            self._gen_recent_activity()
        if gc.get("external_dependencies", True):
            self._gen_external_deps(project, file_index)
        if gc.get("capabilities", True):
            self._gen_capabilities(project, file_index)
        if gc.get("module_summaries") and not self.quick_mode:
            self._gen_summaries(project, file_index)
        if gc.get("claude_md_scaffold"):
            self._gen_llm_md(project)
        if gc.get("architecture_md_scaffold"):
            self._gen_architecture_md(project)

        # Step 5: persist
        hash_cache.save()
        self.updater.new_manifest.save(self.root)
        self.security.log_audit("generate", {"mode": mode})

        print("")
        print("=" * 60)
        print(f"  Done. Context written to: {self.output_dir}")
        self.updater.print_summary()

    # ── Write helper ──────────────────────────────────────────────────────────

    def _write(self, filename: str, content: str) -> None:
        if filename.startswith("../"):
            path = (self.output_dir / filename).resolve()
        else:
            path = self.output_dir / filename
        safe_write_text(path, content)

    # ── Parallel generators ───────────────────────────────────────────────────

    def _gen_tree(self, file_index: FileIndex) -> None:
        should, reason = self.updater.should_regenerate("tree.txt")
        if should:
            print(f"   tree.txt ({reason})")
            content, sources = TreeGenerator(self.root, self.config, file_index).generate()
            self._write("tree.txt", content)
            self.updater.mark_generated("tree.txt", content, sources)
        else:
            self.updater.mark_skipped("tree.txt")

    def _gen_schemas(self, project: ProjectInfo, file_index: FileIndex) -> None:
        gen = SchemaGenerator(self.root, self.config, file_index)
        for filename, (content, sources) in gen.generate_all().items():
            if not content.strip():
                continue
            should, reason = self.updater.should_regenerate(filename, sources)
            if should:
                print(f"   {filename} ({reason})")
                self._write(filename, content)
                self.updater.mark_generated(filename, content, sources)
            else:
                self.updater.mark_skipped(filename)

    def _gen_routes(self, project: ProjectInfo, file_index: FileIndex) -> None:
        content, sources = APIGenerator(
            self.root, self.config, file_index, project.framework
        ).generate_routes()
        if content:
            should, reason = self.updater.should_regenerate("routes.txt", sources)
            if should:
                print(f"   routes.txt ({reason})")
                self._write("routes.txt", content)
                self.updater.mark_generated("routes.txt", content, sources)
            else:
                self.updater.mark_skipped("routes.txt")

    def _gen_public_api(self, project: ProjectInfo, file_index: FileIndex) -> None:
        content, sources = APIGenerator(
            self.root, self.config, file_index, project.framework
        ).generate_public_api()
        if content:
            should, reason = self.updater.should_regenerate("public-api.txt", sources)
            if should:
                print(f"   public-api.txt ({reason})")
                self._write("public-api.txt", content)
                self.updater.mark_generated("public-api.txt", content, sources)
            else:
                self.updater.mark_skipped("public-api.txt")

    def _gen_dependencies(
        self, project: ProjectInfo, file_index: FileIndex, gc: dict
    ) -> None:
        gen = DependencyGenerator(self.root, self.config, file_index)
        content, sources = gen.generate()
        if content:
            should, reason = self.updater.should_regenerate("dependency-graph.txt", sources)
            if should:
                print(f"   dependency-graph.txt ({reason})")
                self._write("dependency-graph.txt", content)
                self.updater.mark_generated("dependency-graph.txt", content, sources)
                if gc.get("dependency_graph_mermaid"):
                    mermaid = gen.generate_mermaid(content)
                    self._write("dependency-graph.md", mermaid)
                    self.updater.mark_generated("dependency-graph.md", mermaid, sources)
            else:
                self.updater.mark_skipped("dependency-graph.txt")
                if gc.get("dependency_graph_mermaid"):
                    self.updater.mark_skipped("dependency-graph.md")

    def _gen_symbols(self, project: ProjectInfo, file_index: FileIndex) -> None:
        gen = SymbolIndexGenerator(self.root, self.config, file_index)
        src_paths = [fi.path for fi in file_index.by_extension(".py", ".ts", ".tsx")]
        should, reason = self.updater.should_regenerate("symbol-index.json", src_paths)
        if should:
            print(f"   symbol-index.json ({reason})")
            content, sources = gen.generate()
            self._write("symbol-index.json", content)
            self.updater.mark_generated("symbol-index.json", content, sources)
        else:
            self.updater.mark_skipped("symbol-index.json")

    def _gen_entrypoints(self, file_index: FileIndex) -> None:
        gen = EntryPointGenerator(self.root, self.config, file_index)
        should, reason = self.updater.should_regenerate("entry-points.json")
        if should:
            print(f"   entry-points.json ({reason})")
            content, sources = gen.generate()
            self._write("entry-points.json", content)
            self.updater.mark_generated("entry-points.json", content, sources)
        else:
            self.updater.mark_skipped("entry-points.json")

    def _gen_db_schema(self, file_index: FileIndex) -> None:
        gen = DatabaseSchemaGenerator(self.root, self.config, file_index)
        content, sources = gen.generate()
        if content:
            should, reason = self.updater.should_regenerate("db-schema.txt", sources)
            if should:
                print(f"   db-schema.txt ({reason})")
                self._write("db-schema.txt", content)
                self.updater.mark_generated("db-schema.txt", content, sources)
            else:
                self.updater.mark_skipped("db-schema.txt")

    def _gen_api_contract(self) -> None:
        gen = ContractsGenerator(self.root, self.config)
        content, sources = gen.generate()
        if content:
            should, reason = self.updater.should_regenerate("api-contract.md", sources)
            if should:
                print(f"   api-contract.md ({reason})")
                self._write("api-contract.md", content)
                self.updater.mark_generated("api-contract.md", content, sources)
            else:
                self.updater.mark_skipped("api-contract.md")

    # ── Sequential tasks ──────────────────────────────────────────────────────

    def _gen_env_shape(self) -> None:
        for name in [".env.example", ".env.template", ".env.sample"]:
            path = self.root / name
            if path.exists():
                should, reason = self.updater.should_regenerate("env-shape.txt", [path])
                if should:
                    print(f"   env-shape.txt ({reason})")
                    content = self.security.redact_content(safe_read_text(path) or "")
                    self._write("env-shape.txt", content)
                    self.updater.mark_generated("env-shape.txt", content, [path])
                else:
                    self.updater.mark_skipped("env-shape.txt")
                break

    def _copy_dep_files(self) -> None:
        for name in DEP_FILES:
            path = self.root / name
            if path.exists():
                should, reason = self.updater.should_regenerate(name, [path])
                if should:
                    content = safe_read_text(path) or ""
                    self._write(name, content)
                    self.updater.mark_generated(name, content, [path])
                else:
                    self.updater.mark_skipped(name)

    def _gen_recent_activity(self) -> None:
        print("   recent git activity")
        try:
            for cmd, fname in [
                (["git", "log", "--oneline", "-20"], "recent-commits.txt"),
                (["git", "diff", "--stat", "HEAD~5"], "recent-changes.txt"),
            ]:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, cwd=self.root
                )
                if result.returncode == 0 and result.stdout:
                    self._write(fname, result.stdout)
                    self.updater.mark_generated(fname, result.stdout)
        except Exception:
            pass

    def _gen_external_deps(
        self, project: ProjectInfo, file_index: FileIndex
    ) -> None:
        gen = ExternalDependencyGenerator(
            self.root, self.config, file_index,
            project.languages, project.framework
        )
        should, reason = self.updater.should_regenerate("external-dependencies.json")
        if should:
            print(f"   external-dependencies.json ({reason})")
            content, sources = gen.generate()
            self._write("external-dependencies.json", content)
            self.updater.mark_generated("external-dependencies.json", content, sources)
        else:
            self.updater.mark_skipped("external-dependencies.json")

    def _gen_capabilities(
        self, project: ProjectInfo, file_index: FileIndex
    ) -> None:
        """Generate capabilities.json using if-missing strategy.

        Capabilities are auto-generated on first run, then human-editable.
        Re-generation only happens on --force or if the file is missing.
        This preserves human-curated descriptions and custom edits.
        """
        output_path = self.output_dir / "capabilities.json"

        # if-missing: never overwrite once the file exists (unless --force)
        if not self.updater.force and output_path.exists():
            self.updater.mark_skipped("capabilities.json")
            return

        # capabilities.json reads from other artifacts — check they exist first
        has_routes = (self.output_dir / "routes.txt").exists()
        has_schemas = (
            (self.output_dir / "schemas-extracted.py").exists() or
            (self.output_dir / "types-extracted.ts").exists()
        )
        has_ext_deps = (self.output_dir / "external-dependencies.json").exists()

        if not has_routes and not has_schemas and not has_ext_deps:
            return  # nothing to build from yet

        reason = "force mode" if self.updater.force else "file missing"
        print(f"   capabilities.json ({reason})")
        gen = CapabilityGenerator(
            self.root, self.config, file_index,
            project.languages, project.framework,
            service_name=project.name,
        )
        content, sources = gen.generate()
        self._write("capabilities.json", content)
        self.updater.mark_generated("capabilities.json", content, sources)

    def _gen_summaries(
        self, project: ProjectInfo, file_index: FileIndex
    ) -> None:
        if not self.security.is_ai_enabled():
            print("   module summaries skipped (AI disabled in offline mode)")
            return
        from .generators.summaries import ModuleSummaryGenerator
        gen = ModuleSummaryGenerator(self.root, self.config, file_index)
        results = gen.generate_all()
        if not results:
            return
        modules_dir = self.output_dir / "modules"
        modules_dir.mkdir(exist_ok=True)
        for filename, (content, sources) in results.items():
            safe_write_text(modules_dir / filename, content)
            self.updater.mark_generated(f"modules/{filename}", content, sources)
        index, _ = gen.generate()
        self._write("module-index.md", index)
        self.updater.mark_generated("module-index.md", index)

    def _gen_llm_md(self, project: ProjectInfo) -> None:
        path = self.root / "LLM.md"
        should, reason = self.updater.should_regenerate("../LLM.md")
        if should:
            print(f"   LLM.md (auto-detecting conventions...)")
            enhancer = ClaudeMdEnhancer(self.root)
            content = enhancer.generate_enhanced_llm_md(project)
            safe_write_text(path, content)
            self.updater.mark_generated("../LLM.md", content, is_new=True)
        else:
            self.updater.mark_skipped("../LLM.md")

    def _gen_architecture_md(self, project: ProjectInfo) -> None:
        path = self.root / "ARCHITECTURE.md"
        should, reason = self.updater.should_regenerate("../ARCHITECTURE.md")
        if should:
            print(f"   ARCHITECTURE.md scaffold ({reason})")
            content = _architecture_md_scaffold(project)
            safe_write_text(path, content)
            self.updater.mark_generated("../ARCHITECTURE.md", content, is_new=True)
        else:
            self.updater.mark_skipped("../ARCHITECTURE.md")


# ── Scaffold templates ────────────────────────────────────────────────────────
def _architecture_md_scaffold(project: ProjectInfo) -> str:
    langs = ", ".join(project.languages) if project.languages else "unknown"
    return f"""# {project.name} — Architecture

> Auto-generated by CCC. Edit to describe the system architecture.

## Overview

- **Languages**: {langs}
- **Framework**: {project.framework}

## Components

- TODO: list major components/modules

## Data Flow

- TODO: how data moves through the system

## External Dependencies

- TODO: external services, APIs, databases

## Deployment

- {"Docker: detected" if project.has_docker else "Docker: not detected"}
- {"CI/CD: detected" if project.has_ci else "CI/CD: not detected"}
"""