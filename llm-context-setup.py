#!/usr/bin/env python3
"""
llm-context-setup.py — Smart LLM Context Generator with Incremental Updates

Drop this into any repo and run it, or install as a tool.

Features:
- Auto-detects project type and languages
- Generates context files optimized for LLMs
- Smart incremental updates (only regenerates what changed)
- Multiple operation modes: full, quick, watch
- Auto-detects conventions for enhanced CLAUDE.md
- Database schema extraction
- Zero required dependencies for core functionality

Usage:
    python3 llm-context-setup.py                    # Full generation
    python3 llm-context-setup.py --quick-update     # Fast incremental update
    python3 llm-context-setup.py --watch            # Watch mode
    python3 llm-context-setup.py --force            # Force full regeneration

Version: 0.3.0
"""

import subprocess
import sys
import os
import json
import re
import ast
import hashlib
import time
import threading
from pathlib import Path
from typing import Optional, Literal, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from collections import defaultdict

# ──────────────────────────────────────────────
# Version & Metadata
# ──────────────────────────────────────────────

VERSION = "0.3.0"
MANIFEST_VERSION = "3"

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

UpdateStrategy = Literal["always", "if-changed", "if-missing", "never"]

DEFAULT_CONFIG = {
    "version": MANIFEST_VERSION,
    "output_dir": ".llm-context",
    "exclude_patterns": [
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
        "*.pyc", "*.pyo", "*.egg-info", ".DS_Store", "*.lock",
        "migrations/versions", "coverage", ".coverage",
        "*.min.js", "*.min.css", "*.map", ".next", ".nuxt",
        "target/debug", "target/release",
    ],
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
    },
    "llm_summaries": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "max_modules": 30,
        "min_file_size_bytes": 300
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
        "db-schema.sql": "if-changed",
        "api-contract.md": "if-changed",
        "modules/*.md": "if-changed",
        "../CLAUDE.md": "if-missing",
        "../ARCHITECTURE.md": "if-missing",
    }
}


@dataclass
class FileManifestEntry:
    """Metadata for a generated file."""
    hash: str
    size: int
    generated_at: str
    source_files: list[str] = field(default_factory=list)
    source_hashes: list[str] = field(default_factory=list)
    strategy: UpdateStrategy = "always"


@dataclass
class GenerationManifest:
    """Tracks what was generated and when, for incremental updates."""
    version: str
    generated_at: str
    project_fingerprint: str
    files: dict[str, dict[str, Any]]
    
    @classmethod
    def load(cls, path: Path) -> Optional['GenerationManifest']:
        """Load existing manifest."""
        manifest_file = path / ".llm-context" / "manifest.json"
        if not manifest_file.exists():
            return None
        try:
            data = json.loads(manifest_file.read_text())
            if data.get("version") != MANIFEST_VERSION:
                print(f"  ⚠ Manifest version mismatch (found {data.get('version')}, expected {MANIFEST_VERSION})")
                print("    Running full regeneration...")
                return None
            return cls(**data)
        except Exception as e:
            print(f"  ⚠ Error loading manifest: {e}")
            return None
    
    def save(self, path: Path):
        """Save manifest to disk."""
        manifest_file = path / ".llm-context" / "manifest.json"
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        manifest_file.write_text(json.dumps(asdict(self), indent=2))
    
    def get_entry(self, filename: str) -> Optional[FileManifestEntry]:
        """Get manifest entry for a file."""
        entry_dict = self.files.get(filename)
        if not entry_dict:
            return None
        return FileManifestEntry(**entry_dict)
    
    def set_entry(self, filename: str, entry: FileManifestEntry):
        """Set manifest entry for a file."""
        self.files[filename] = asdict(entry)


@dataclass
class ProjectInfo:
    """Auto-detected project metadata."""
    root: Path
    name: str = ""
    languages: list[str] = field(default_factory=list)
    framework: str = ""
    package_manager: str = ""
    has_docker: bool = False
    has_ci: bool = False
    has_tests: bool = False
    entry_points: list[str] = field(default_factory=list)
    description: str = ""
    python_version: str = ""
    node_version: str = ""


# ──────────────────────────────────────────────
# Utility functions
# ──────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _human_size(size: int) -> str:
    for unit in ["B", "KB", "MB"]:
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}GB"


def _should_skip_path(path: Path) -> bool:
    skip_parts = {
        "node_modules", ".venv", "venv", "__pycache__",
        "dist", "build", ".git", "migrations", ".tox",
        ".mypy_cache", ".pytest_cache", "coverage",
        ".next", ".nuxt", "target",
    }
    return bool(set(path.parts) & skip_parts)


def load_config(root: Path) -> dict:
    config = DEFAULT_CONFIG.copy()
    
    config_file = root / "llm-context.yml"
    if config_file.exists():
        try:
            import yaml
            with open(config_file) as f:
                user_config = yaml.safe_load(f)
            if user_config:
                _deep_merge(config, user_config)
            print(f"  ✓ Loaded config from {config_file}")
            return config
        except ImportError:
            pass
    
    config_file = root / "llm-context.json"
    if config_file.exists():
        try:
            with open(config_file) as f:
                user_config = json.load(f)
            _deep_merge(config, user_config)
            print(f"  ✓ Loaded config from {config_file}")
        except Exception:
            pass
    
    return config


def _deep_merge(base: dict, override: dict):
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


# ──────────────────────────────────────────────
# Smart Update Manager
# ──────────────────────────────────────────────

class SmartUpdater:
    """Manages incremental updates based on file changes."""
    
    def __init__(self, root: Path, config: dict, force: bool = False):
        self.root = root
        self.config = config
        self.force = force
        self.old_manifest = None if force else GenerationManifest.load(root)
        self.new_manifest = GenerationManifest(
            version=MANIFEST_VERSION,
            generated_at=_now(),
            project_fingerprint=self._compute_project_fingerprint(),
            files={}
        )
        self.stats = {
            "regenerated": 0,
            "skipped": 0,
            "new": 0
        }
    
    def should_regenerate(self, filepath: str, source_files: list[Path] = None) -> tuple[bool, str]:
        """Determine if a file needs regeneration."""
        if self.force:
            return True, "force mode"
        
        strategy = self._get_strategy(filepath)
        
        if strategy == "always":
            return True, "always regenerate"
        
        if strategy == "never":
            return False, "never regenerate"
        
        if strategy == "if-missing":
            check_path = self.root / filepath
            if not check_path.exists():
                return True, "file missing"
            return False, "file exists"
        
        if strategy == "if-changed":
            if not self.old_manifest:
                return True, "first run"
            
            old_entry = self.old_manifest.get_entry(filepath)
            if not old_entry:
                return True, "new file"
            
            if source_files:
                old_hashes = old_entry.source_hashes
                new_hashes = [self._hash_file(f) for f in source_files]
                
                if new_hashes != old_hashes:
                    return True, "source files changed"
            
            if self.old_manifest.project_fingerprint != self.new_manifest.project_fingerprint:
                return True, "project dependencies changed"
            
            return False, "up to date"
        
        return True, "default"
    
    def mark_generated(self, filepath: str, content: str, source_files: list[Path] = None, is_new: bool = False):
        """Record that a file was generated."""
        strategy = self._get_strategy(filepath)
        
        entry = FileManifestEntry(
            hash=hashlib.sha256(content.encode()).hexdigest()[:16],
            size=len(content),
            generated_at=_now(),
            source_files=[str(f.relative_to(self.root)) for f in (source_files or [])],
            source_hashes=[self._hash_file(f) for f in (source_files or [])],
            strategy=strategy
        )
        
        self.new_manifest.set_entry(filepath, entry)
        
        if is_new:
            self.stats["new"] += 1
        else:
            self.stats["regenerated"] += 1
    
    def mark_skipped(self, filepath: str):
        """Record that a file was skipped (up to date)."""
        if self.old_manifest:
            old_entry = self.old_manifest.get_entry(filepath)
            if old_entry:
                self.new_manifest.set_entry(filepath, old_entry)
        
        self.stats["skipped"] += 1
    
    def _get_strategy(self, filepath: str) -> UpdateStrategy:
        """Get update strategy for a file."""
        strategies = self.config.get("update_strategies", {})
        
        if filepath in strategies:
            return strategies[filepath]
        
        for pattern, strategy in strategies.items():
            if "*" in pattern:
                import fnmatch
                if fnmatch.fnmatch(filepath, pattern):
                    return strategy
            elif filepath.endswith(pattern):
                return strategy
        
        return "always"
    
    def _hash_file(self, path: Path) -> str:
        """Fast file hash."""
        try:
            size = path.stat().st_size
            if size > 100_000:
                with open(path, 'rb') as f:
                    start = f.read(10000)
                    f.seek(-10000, 2)
                    end = f.read(10000)
                    return hashlib.md5(start + end).hexdigest()[:12]
            else:
                return hashlib.md5(path.read_bytes()).hexdigest()[:12]
        except Exception:
            return ""
    
    def _compute_project_fingerprint(self) -> str:
        """Hash of key project files to detect major changes."""
        key_files = [
            "pyproject.toml", "package.json", "Cargo.toml", "go.mod",
            "requirements.txt", "poetry.lock", "package-lock.json",
            ".env.example", "docker-compose.yml"
        ]
        
        fingerprint_parts = []
        for filename in key_files:
            path = self.root / filename
            if path.exists():
                file_hash = self._hash_file(path)
                fingerprint_parts.append(f"{filename}:{file_hash}")
        
        combined = "|".join(sorted(fingerprint_parts))
        return hashlib.md5(combined.encode()).hexdigest()[:16]
    
    def print_summary(self):
        """Print update statistics."""
        total = sum(self.stats.values())
        print(f"\n{'─' * 60}")
        print(f"  Update Summary:")
        print(f"  • Regenerated: {self.stats['regenerated']}")
        print(f"  • Skipped (up to date): {self.stats['skipped']}")
        print(f"  • New files: {self.stats['new']}")
        print(f"  • Total: {total}")
        print(f"{'─' * 60}\n")


# ──────────────────────────────────────────────
# Progress Indicator
# ──────────────────────────────────────────────

class ProgressIndicator:
    """Simple progress indicator for terminal."""
    
    def __init__(self, total: int, description: str = "Processing"):
        self.total = total
        self.current = 0
        self.description = description
        self.start_time = time.time()
    
    def update(self, increment: int = 1):
        """Update progress."""
        self.current += increment
        percent = (self.current / self.total) * 100 if self.total > 0 else 0
        elapsed = time.time() - self.start_time
        
        if self.current > 0:
            eta = (elapsed / self.current) * (self.total - self.current)
            eta_str = f"ETA: {int(eta)}s" if eta > 0 else "Done"
        else:
            eta_str = ""
        
        bar_length = 30
        filled = int(bar_length * percent / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        print(f"\r  {self.description}: [{bar}] {percent:5.1f}% ({self.current}/{self.total}) {eta_str}", end="", flush=True)
    
    def finish(self):
        """Mark as complete."""
        print()


# ──────────────────────────────────────────────
# Project Detection
# ──────────────────────────────────────────────

class ProjectDetector:
    """Detect project type, language, framework, and conventions."""

    FRAMEWORK_INDICATORS = {
        "fastapi": ["fastapi", "from fastapi"],
        "django": ["django", "DJANGO_SETTINGS_MODULE"],
        "flask": ["flask", "from flask"],
        "sqlalchemy": ["sqlalchemy", "from sqlalchemy"],
        "pydantic": ["pydantic", "BaseModel"],
        "react": ["react", "react-dom"],
        "nextjs": ["next", "next.config"],
        "express": ["express"],
        "nestjs": ["@nestjs"],
        "vue": ["vue"],
        "angular": ["@angular"],
        "svelte": ["svelte"],
        "actix": ["actix-web"],
        "axum": ["axum"],
        "tokio": ["tokio"],
        "gin": ["github.com/gin-gonic/gin"],
        "echo": ["github.com/labstack/echo"],
        "fiber": ["github.com/gofiber/fiber"],
    }

    def __init__(self, root: Path):
        self.root = root

    def detect(self) -> ProjectInfo:
        info = ProjectInfo(root=self.root)
        info.name = self.root.name
        info.languages = self._detect_languages()
        self._detect_from_configs(info)
        info.framework = self._detect_framework(info)
        info.has_docker = (self.root / "Dockerfile").exists() or (self.root / "docker-compose.yml").exists()
        info.has_ci = any([
            (self.root / ".github/workflows").exists(),
            (self.root / ".gitlab-ci.yml").exists(),
            (self.root / "Jenkinsfile").exists(),
            (self.root / ".circleci").exists(),
        ])
        info.has_tests = any([
            (self.root / "tests").exists(),
            (self.root / "test").exists(),
            (self.root / "__tests__").exists(),
            (self.root / "spec").exists(),
        ])
        return info

    def _detect_languages(self) -> list[str]:
        extensions = {}
        for f in self._walk_files():
            ext = f.suffix.lower()
            extensions[ext] = extensions.get(ext, 0) + 1

        lang_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".tsx": "typescript", ".jsx": "javascript", ".rs": "rust",
            ".go": "go", ".java": "java", ".cs": "csharp", ".rb": "ruby",
            ".php": "php", ".swift": "swift", ".kt": "kotlin",
        }

        langs = []
        for ext, count in sorted(extensions.items(), key=lambda x: -x[1]):
            if ext in lang_map and count >= 2:
                langs.append(lang_map[ext])

        return langs[:5]

    def _detect_from_configs(self, info: ProjectInfo):
        if (self.root / "pyproject.toml").exists():
            info.package_manager = "poetry/pip"
            try:
                content = (self.root / "pyproject.toml").read_text()
                if match := re.search(r'description\s*=\s*"([^"]*)"', content):
                    info.description = match.group(1)
                if match := re.search(r'python\s*=\s*"([^"]*)"', content):
                    info.python_version = match.group(1)
            except Exception:
                pass

        if (self.root / "package.json").exists():
            info.package_manager = "npm/yarn"
            try:
                pkg = json.loads((self.root / "package.json").read_text())
                info.description = pkg.get("description", "")
                if "main" in pkg:
                    info.entry_points.append(pkg["main"])
            except Exception:
                pass

        if (self.root / "Cargo.toml").exists():
            info.package_manager = "cargo"

        if (self.root / "go.mod").exists():
            info.package_manager = "go modules"

    def _detect_framework(self, info: ProjectInfo) -> str:
        """Scan key files for framework imports."""
        files_to_scan = list(self._walk_files(max_files=100))
        content_sample = ""

        for f in files_to_scan[:50]:
            try:
                if f.stat().st_size < 50_000:
                    content_sample += f.read_text(errors="ignore")
            except Exception:
                continue

        for dep_file in ["requirements.txt", "pyproject.toml", "package.json", "Cargo.toml", "go.mod"]:
            p = self.root / dep_file
            if p.exists():
                try:
                    content_sample += p.read_text()
                except Exception:
                    pass

        detected = []
        for framework, indicators in self.FRAMEWORK_INDICATORS.items():
            for indicator in indicators:
                if indicator.lower() in content_sample.lower():
                    detected.append(framework)
                    break

        return ", ".join(detected) if detected else "unknown"

    def _walk_files(self, max_files: int = 1000):
        count = 0
        exclude = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".tox"}
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in exclude]
            for f in filenames:
                if count >= max_files:
                    return
                yield Path(dirpath) / f
                count += 1


# ──────────────────────────────────────────────
# CLAUDE.md Enhancer with Auto-Detection
# ──────────────────────────────────────────────

class ClaudeMdEnhancer:
    """Auto-detect conventions and patterns to pre-fill CLAUDE.md."""
    
    def __init__(self, root: Path):
        self.root = root
    
    def detect_conventions(self, project: ProjectInfo) -> dict:
        """Auto-detect project conventions."""
        return {
            "error_handling": self._detect_error_pattern(),
            "testing_framework": self._detect_test_framework(),
            "async_pattern": self._detect_async_usage(),
            "orm_pattern": self._detect_orm(),
            "api_style": self._detect_api_style(),
            "logging_pattern": self._detect_logging(),
            "dangerous_files": self._find_dangerous_files(),
            "code_quality_tools": self._detect_quality_tools(),
        }
    
    def _detect_error_pattern(self) -> str:
        """Detect: exceptions vs Result pattern vs error codes."""
        samples = list(self.root.rglob("*.py"))[:20]
        
        result_count = 0
        exception_count = 0
        
        for f in samples:
            if _should_skip_path(f):
                continue
            try:
                content = f.read_text(errors="ignore")
                if "Result[" in content or "from result import" in content:
                    result_count += 1
                if "raise " in content:
                    exception_count += content.count("raise ")
            except Exception:
                continue
        
        if result_count > 5:
            return "Result pattern (functional error handling) — Use Result[T, E] instead of exceptions for business logic errors"
        elif exception_count > 20:
            return "Exception-based — Use try/except for error handling"
        return "Mixed/unclear (TODO: document your error handling strategy)"
    
    def _detect_test_framework(self) -> dict:
        """Detect pytest vs unittest vs jest vs others."""
        frameworks = {"python": None, "javascript": None}
        
        if (self.root / "pytest.ini").exists():
            frameworks["python"] = "pytest"
        else:
            test_files = list(self.root.rglob("test_*.py"))[:5]
            for tf in test_files:
                try:
                    content = tf.read_text(errors="ignore")
                    if "import pytest" in content:
                        frameworks["python"] = "pytest"
                        break
                    if "import unittest" in content:
                        frameworks["python"] = "unittest"
                        break
                except Exception:
                    continue
        
        if (self.root / "package.json").exists():
            try:
                pkg = json.loads((self.root / "package.json").read_text())
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                
                if "jest" in deps:
                    frameworks["javascript"] = "jest"
                elif "vitest" in deps:
                    frameworks["javascript"] = "vitest"
                elif "mocha" in deps:
                    frameworks["javascript"] = "mocha"
                elif "@playwright/test" in deps:
                    frameworks["javascript"] = "playwright"
            except Exception:
                pass
        
        return {k: v for k, v in frameworks.items() if v}
    
    def _detect_async_usage(self) -> Optional[str]:
        """Detect if project uses async/await heavily."""
        py_files = list(self.root.rglob("*.py"))[:30]
        async_count = 0
        total_functions = 0
        
        for f in py_files:
            if _should_skip_path(f):
                continue
            try:
                content = f.read_text(errors="ignore")
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        total_functions += 1
                    elif isinstance(node, ast.AsyncFunctionDef):
                        async_count += 1
                        total_functions += 1
            except Exception:
                continue
        
        if total_functions == 0:
            return None
        
        async_ratio = async_count / total_functions
        
        if async_ratio > 0.3:
            return f"Heavy async usage (~{int(async_ratio*100)}% of functions) — Always use async/await, avoid blocking calls"
        elif async_ratio > 0.1:
            return "Mixed sync/async — Be careful with blocking calls in async functions"
        return None
    
    def _detect_orm(self) -> Optional[str]:
        """Detect ORM/database layer."""
        orms = []
        
        for indicator_file in ["requirements.txt", "pyproject.toml"]:
            path = self.root / indicator_file
            if path.exists():
                content = path.read_text()
                if "sqlalchemy" in content.lower():
                    orms.append("SQLAlchemy")
                if "django" in content.lower():
                    orms.append("Django ORM")
                if "tortoise" in content.lower():
                    orms.append("Tortoise ORM")
        
        pkg_json = self.root / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                
                if "typeorm" in deps:
                    orms.append("TypeORM")
                if "prisma" in deps:
                    orms.append("Prisma")
                if "sequelize" in deps:
                    orms.append("Sequelize")
                if "mongoose" in deps:
                    orms.append("Mongoose")
            except Exception:
                pass
        
        return ", ".join(orms) if orms else None
    
    def _detect_api_style(self) -> str:
        """Detect REST vs GraphQL vs gRPC."""
        styles = []
        
        if any((self.root / p).exists() for p in ["schema.graphql", "schema.gql"]):
            styles.append("GraphQL")
        
        for dep_file in ["requirements.txt", "pyproject.toml", "package.json"]:
            path = self.root / dep_file
            if path.exists():
                content = path.read_text().lower()
                if "graphql" in content and "GraphQL" not in styles:
                    styles.append("GraphQL")
                if "grpc" in content or "protobuf" in content:
                    styles.append("gRPC")
        
        route_count = 0
        for py_file in list(self.root.rglob("*.py"))[:20]:
            if _should_skip_path(py_file):
                continue
            try:
                content = py_file.read_text(errors="ignore")
                if re.search(r'@(?:app|router)\.(get|post|put|delete)', content):
                    route_count += 1
                    if route_count >= 3:
                        styles.insert(0, "REST")
                        break
            except Exception:
                continue
        
        return " + ".join(styles) if styles else "REST (assumed)"
    
    def _detect_logging(self) -> Optional[str]:
        """Detect logging framework."""
        py_files = list(self.root.rglob("*.py"))[:20]
        logging_libs = set()
        
        for f in py_files:
            if _should_skip_path(f):
                continue
            try:
                content = f.read_text(errors="ignore")
                if "import logging" in content:
                    logging_libs.add("stdlib logging")
                if "from loguru import" in content:
                    logging_libs.add("loguru")
                if "import structlog" in content:
                    logging_libs.add("structlog")
            except Exception:
                continue
        
        return ", ".join(logging_libs) if logging_libs else None
    
    def _find_dangerous_files(self) -> list[dict]:
        """Find files with danger signals."""
        dangerous = []
        
        danger_keywords = {
            "payment": "💰 Payment processing",
            "billing": "💳 Billing logic",
            "auth": "🔐 Authentication",
            "password": "🔑 Password handling",
            "crypto": "🔒 Cryptography",
            "encrypt": "🔒 Encryption",
            "private_key": "🔑 Private key usage",
            "migration": "🗄️ Database migration",
            "delete from": "⚠️ Data deletion",
            "drop table": "💥 Schema destruction",
        }
        
        for py_file in self.root.rglob("*.py"):
            if _should_skip_path(py_file):
                continue
            try:
                content = py_file.read_text(errors="ignore").lower()
                matches = []
                
                for keyword, description in danger_keywords.items():
                    if keyword in content:
                        matches.append(description)
                
                if matches:
                    dangerous.append({
                        "file": str(py_file.relative_to(self.root)),
                        "reasons": matches
                    })
            except Exception:
                continue
        
        dangerous.sort(key=lambda x: len(x["reasons"]), reverse=True)
        return dangerous[:10]
    
    def _detect_quality_tools(self) -> dict:
        """Detect linters, formatters, type checkers."""
        tools = {"linters": [], "formatters": [], "type_checkers": []}
        
        for config_file in ["pyproject.toml", "setup.cfg", ".flake8", "tox.ini"]:
            path = self.root / config_file
            if path.exists():
                content = path.read_text()
                if "ruff" in content:
                    tools["linters"].append("ruff")
                if "flake8" in content and "ruff" not in tools["linters"]:
                    tools["linters"].append("flake8")
                if "pylint" in content:
                    tools["linters"].append("pylint")
                if "black" in content:
                    tools["formatters"].append("black")
                if "isort" in content:
                    tools["formatters"].append("isort")
                if "mypy" in content:
                    tools["type_checkers"].append("mypy")
                if "pyright" in content:
                    tools["type_checkers"].append("pyright")
        
        pkg_json = self.root / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                
                if "eslint" in deps:
                    tools["linters"].append("eslint")
                if "prettier" in deps:
                    tools["formatters"].append("prettier")
                if "typescript" in deps:
                    tools["type_checkers"].append("tsc")
            except Exception:
                pass
        
        return {k: v for k, v in tools.items() if v}
    
    def generate_enhanced_claude_md(self, project: ProjectInfo) -> str:
        """Generate CLAUDE.md with auto-detected patterns."""
        conventions = self.detect_conventions(project)
        test_frameworks = conventions.get('testing_framework', {})
        quality_tools = conventions.get('code_quality_tools', {})
        
        test_section = ""
        if test_frameworks:
            test_section = "\n### Testing\n"
            for lang, framework in test_frameworks.items():
                test_section += f"- {lang.capitalize()}: {framework}\n"
        
        quality_section = ""
        if quality_tools:
            quality_section = "\n### Code Quality\n"
            if quality_tools.get("linters"):
                quality_section += f"- Linters: {', '.join(quality_tools['linters'])}\n"
            if quality_tools.get("formatters"):
                quality_section += f"- Formatters: {', '.join(quality_tools['formatters'])}\n"
            if quality_tools.get("type_checkers"):
                quality_section += f"- Type checking: {', '.join(quality_tools['type_checkers'])}\n"
        
        dangerous_section = ""
        dangerous_files = conventions.get('dangerous_files', [])
        if dangerous_files:
            dangerous_section = "\n## Dangerous Areas\n"
            dangerous_section += "<!-- These files contain sensitive logic. Extra care required. -->\n\n"
            for item in dangerous_files[:5]:
                reasons = " | ".join(item['reasons'])
                dangerous_section += f"- **`{item['file']}`** — {reasons}\n"
                dangerous_section += "  - TODO: Add specific gotchas and review requirements\n\n"
        
        p = project
        async_section = ""
        if conventions.get('async_pattern'):
            async_section = f"\n### Async/Await\n{conventions['async_pattern']}\n"
        
        return f"""# CLAUDE.md — Project: {p.name}

## Identity
You are a senior developer on this project with deep knowledge of the codebase.

## Stack
- **Languages**: {', '.join(p.languages) or 'Unknown'}
- **Framework**: {p.framework or 'Unknown'}
- **Package Manager**: {p.package_manager or 'Unknown'}
{f"- **Python**: {p.python_version}" if p.python_version else ""}
- **API Style**: {conventions.get('api_style', 'Unknown')}
{f"- **Database**: {conventions['orm_pattern']}" if conventions.get('orm_pattern') else ""}
{f"- **Logging**: {conventions['logging_pattern']}" if conventions.get('logging_pattern') else ""}
{"- **Containerized**: Docker" if p.has_docker else ""}
{"- **CI/CD**: Configured" if p.has_ci else ""}

## Project Description
{p.description or "TODO: Add a one-paragraph description of what this project does."}

## Critical Conventions

### Error Handling
{conventions['error_handling']}
<!-- TODO: Add specifics about when to use which pattern -->
{test_section}
{async_section}
{quality_section}

### Code Style
- TODO: Max function length?
- TODO: Naming conventions?
- TODO: Import organization?
{dangerous_section}
## Current State
<!-- TODO: What's in progress? What's deprecated? -->
- TODO: Any ongoing migrations or refactors?
- TODO: Any deprecated patterns to avoid?
- TODO: What's the current sprint/milestone focus?

## Common Tasks

### Running the Project
# TODO: How to start development
# TODO: How to run tests
# TODO: How to build for production

### Adding New Features
# TODO: Step-by-step guide for common additions

### Deployment
# TODO: How to deploy changes

## Common Gotchas
<!-- Things that aren't obvious from reading the code -->
# TODO: Race conditions to watch for?
# TODO: Order-dependent operations?
# TODO: Performance bottlenecks?
## Emergency Contacts
<!-- Who to notify for critical issues -->
# Database issues: TODO
# Production incidents: TODO
# Security concerns: TODO
"""
# ──────────────────────────────────────────────
# Generators with src file tracking
# ──────────────────────────────────────────────
class TreeGenerator:
"""Generate file tree with intelligent filtering."""
def __init__(self, root: Path, config: dict):
    self.root = root
    self.config = config

def generate(self) -> tuple[str, list[Path]]:
    """Generate file tree."""
    lines = [f"# File Tree: {self.root.name}", f"# Generated: {_now()}", ""]
    self._walk(self.root, "", lines, depth=0)
    source_files = []
    return "\n".join(lines), source_files

def _walk(self, directory: Path, prefix: str, lines: list, depth: int):
    if depth > self.config.get("max_tree_depth", 6):
        lines.append(f"{prefix}... (depth limit)")
        return
    if len(lines) > self.config.get("max_files_in_tree", 500):
        lines.append(f"{prefix}... (file limit reached)")
        return

    try:
        entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return

    entries = [e for e in entries if not self._should_exclude(e)]

    for i, entry in enumerate(entries):
        is_last = (i == len(entries) - 1)
        connector = "└── " if is_last else "├── "
        extension = "    " if is_last else "│   "

        if entry.is_dir():
            try:
                file_count = sum(1 for _ in entry.rglob("*") if _.is_file())
            except (PermissionError, OSError):
                file_count = "?"
            lines.append(f"{prefix}{connector}{entry.name}/ ({file_count} files)")
            self._walk(entry, prefix + extension, lines, depth + 1)
        else:
            try:
                size = entry.stat().st_size
                size_str = _human_size(size)
                lines.append(f"{prefix}{connector}{entry.name} ({size_str})")
            except (PermissionError, OSError):
                lines.append(f"{prefix}{connector}{entry.name}")

def _should_exclude(self, path: Path) -> bool:
    name = path.name
    exclude = self.config.get("exclude_patterns", [])
    for pattern in exclude:
        if pattern.startswith("*"):
            if name.endswith(pattern[1:]):
                return True
        elif name == pattern:
            return True
    return False

class SchemaExtractor:
"""Extract type definitions, schemas, interfaces from source code."""
def __init__(self, root: Path, languages: list[str]):
    self.root = root
    self.languages = languages

def extract(self) -> dict[str, tuple[str, list[Path]]]:
    """Extract schemas for all languages."""
    results = {}

    if "python" in self.languages:
        content, sources = self._extract_python()
        if content:
            results["schemas-extracted.py"] = (content, sources)
    
    if "typescript" in self.languages:
        content, sources = self._extract_typescript()
        if content:
            results["types-extracted.ts"] = (content, sources)
    
    if "rust" in self.languages:
        content, sources = self._extract_rust()
        if content:
            results["rust-types.rs"] = (content, sources)
    
    if "go" in self.languages:
        content, sources = self._extract_go()
        if content:
            results["go-types.go"] = (content, sources)
    
    if "csharp" in self.languages:
        content, sources = self._extract_csharp()
        if content:
            results["csharp-types.cs"] = (content, sources)

    return results

def _extract_python(self) -> tuple[str, list[Path]]:
    """Extract Pydantic models, dataclasses, TypedDicts, enums."""
    output_lines = ["# Auto-extracted Python type definitions", f"# Generated: {_now()}", ""]
    source_files = []

    for py_file in self.root.rglob("*.py"):
        if _should_skip_path(py_file):
            continue

        try:
            content = py_file.read_text(errors="ignore")
            tree = ast.parse(content)
        except (SyntaxError, Exception):
            continue

        classes_in_file = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                base_names = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        base_names.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        base_names.append(base.attr)

                interesting_bases = {"BaseModel", "BaseSchema", "TypedDict", "Enum", "IntEnum", "StrEnum"}

                is_dataclass = any(
                    isinstance(d, ast.Name) and d.id == "dataclass"
                    or isinstance(d, ast.Attribute) and d.attr == "dataclass"
                    for d in node.decorator_list
                )

                if set(base_names) & interesting_bases or is_dataclass:
                    start = node.lineno - 1
                    end = node.end_lineno or start + 1
                    source_lines = content.split("\n")[start:end]
                    classes_in_file.append("\n".join(source_lines))

        if classes_in_file:
            source_files.append(py_file)
            rel_path = py_file.relative_to(self.root)
            output_lines.append(f"\n# ── {rel_path} ──")
            output_lines.extend(classes_in_file)
            output_lines.append("")

    return "\n".join(output_lines), source_files

def _extract_typescript(self) -> tuple[str, list[Path]]:
    """Extract interfaces, type aliases, enums from TS files."""
    output_lines = ["// Auto-extracted TypeScript type definitions", f"// Generated: {_now()}", ""]
    source_files = []

    pattern = re.compile(
        r'^export\s+(?:interface|type|enum|const\s+enum)\s+.*?(?:\{[\s\S]*?\n\}|=\s*[\s\S]*?;)',
        re.MULTILINE
    )

    for ts_file in self.root.rglob("*.ts"):
        if _should_skip_path(ts_file) or ts_file.suffix == ".spec.ts":
            continue

        try:
            content = ts_file.read_text(errors="ignore")
        except Exception:
            continue

        matches = pattern.findall(content)
        if matches:
            source_files.append(ts_file)
            rel_path = ts_file.relative_to(self.root)
            output_lines.append(f"\n// ── {rel_path} ──")
            for match in matches:
                output_lines.append(match.strip())
                output_lines.append("")

    return "\n".join(output_lines), source_files

def _extract_rust(self) -> tuple[str, list[Path]]:
    """Extract structs, enums, traits from Rust files."""
    output_lines = ["// Auto-extracted Rust type definitions", f"// Generated: {_now()}", ""]
    source_files = []

    pattern = re.compile(
        r'(?:#\[derive\(.*?\)\]\s*)?pub\s+(?:struct|enum|trait)\s+\w+[\s\S]*?\n\}',
        re.MULTILINE
    )

    for rs_file in self.root.rglob("*.rs"):
        if _should_skip_path(rs_file):
            continue
        try:
            content = rs_file.read_text(errors="ignore")
        except Exception:
            continue

        matches = pattern.findall(content)
        if matches:
            source_files.append(rs_file)
            rel_path = rs_file.relative_to(self.root)
            output_lines.append(f"\n// ── {rel_path} ──")
            for match in matches:
                output_lines.append(match.strip())
                output_lines.append("")

    return "\n".join(output_lines), source_files

def _extract_go(self) -> tuple[str, list[Path]]:
    """Extract structs, interfaces from Go files."""
    output_lines = ["// Auto-extracted Go type definitions", f"// Generated: {_now()}", ""]
    source_files = []

    pattern = re.compile(r'type\s+\w+\s+(?:struct|interface)\s*\{[\s\S]*?\n\}', re.MULTILINE)

    for go_file in self.root.rglob("*.go"):
        if _should_skip_path(go_file) or "_test.go" in go_file.name:
            continue
        try:
            content = go_file.read_text(errors="ignore")
        except Exception:
            continue

        matches = pattern.findall(content)
        if matches:
            source_files.append(go_file)
            rel_path = go_file.relative_to(self.root)
            output_lines.append(f"\n// ── {rel_path} ──")
            for match in matches:
                output_lines.append(match.strip())
                output_lines.append("")

    return "\n".join(output_lines), source_files

def _extract_csharp(self) -> tuple[str, list[Path]]:
    """Extract classes, records, enums, interfaces from C# files."""
    output_lines = ["// Auto-extracted C# type definitions", f"// Generated: {_now()}", ""]
    source_files = []

    pattern = re.compile(
        r'public\s+(?:sealed\s+|abstract\s+|partial\s+|static\s+)*(?:class|record|enum|interface|struct)\s+\w+[\s\S]*?\n\}',
        re.MULTILINE
    )

    for cs_file in self.root.rglob("*.cs"):
        if _should_skip_path(cs_file):
            continue
        try:
            content = cs_file.read_text(errors="ignore")
        except Exception:
            continue

        matches = pattern.findall(content)
        if matches:
            source_files.append(cs_file)
            rel_path = cs_file.relative_to(self.root)
            output_lines.append(f"\n// ── {rel_path} ──")
            for match in matches:
                output_lines.append(match.strip())
                output_lines.append("")

    return "\n".join(output_lines), source_files

class APIExtractor:
"""Extract route definitions and public function signatures."""
def __init__(self, root: Path, languages: list[str], framework: str):
    self.root = root
    self.languages = languages
    self.framework = framework

def extract_routes(self) -> tuple[str, list[Path]]:
    """Extract API routes."""
    lines = [f"# API Routes", f"# Generated: {_now()}", ""]
    source_files = []

    if "python" in self.languages:
        content, sources = self._extract_python_routes()
        lines.extend(content)
        source_files.extend(sources)
    
    if "typescript" in self.languages or "javascript" in self.languages:
        content, sources = self._extract_js_routes()
        lines.extend(content)
        source_files.extend(sources)

    return "\n".join(lines) if len(lines) > 3 else "", source_files

def extract_public_api(self) -> tuple[str, list[Path]]:
    """Extract public function signatures."""
    lines = [f"# Public API (function signatures)", f"# Generated: {_now()}", ""]
    source_files = []

    if "python" in self.languages:
        content, sources = self._extract_python_signatures()
        lines.extend(content)
        source_files.extend(sources)
    
    if "typescript" in self.languages:
        content, sources = self._extract_ts_signatures()
        lines.extend(content)
        source_files.extend(sources)

    return "\n".join(lines), source_files

def _extract_python_routes(self) -> tuple[list[str], list[Path]]:
    lines = []
    source_files = []
    route_pattern = re.compile(
        r'@(?:app|router|api)\.(get|post|put|patch|delete|head|options|websocket)\s*\(\s*["\']([^"\']*)["\']'
    )

    for py_file in self.root.rglob("*.py"):
        if _should_skip_path(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")
        except Exception:
            continue

        matches = route_pattern.findall(content)
        if matches:
            source_files.append(py_file)
            rel = py_file.relative_to(self.root)
            lines.append(f"\n## {rel}")
            for method, path in matches:
                lines.append(f"  {method.upper():8s} {path}")

    return lines, source_files

def _extract_js_routes(self) -> tuple[list[str], list[Path]]:
    lines = []
    source_files = []
    route_pattern = re.compile(
        r'(?:app|router|server)\.(get|post|put|patch|delete)\s*\(\s*["\'/]([^"\']*)["\']'
    )

    for ext in ["*.js", "*.ts"]:
        for js_file in self.root.rglob(ext):
            if _should_skip_path(js_file):
                continue
            try:
                content = js_file.read_text(errors="ignore")
            except Exception:
                continue

            matches = route_pattern.findall(content)
            if matches:
                source_files.append(js_file)
                rel = js_file.relative_to(self.root)
                lines.append(f"\n## {rel}")
                for method, path in matches:
                    lines.append(f"  {method.upper():8s} {path}")

    return lines, source_files

def _extract_python_signatures(self) -> tuple[list[str], list[Path]]:
    lines = []
    source_files = []

    for py_file in self.root.rglob("*.py"):
        if _should_skip_path(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")
            tree = ast.parse(content)
        except Exception:
            continue

        sigs = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    sig = self._format_python_sig(node)
                    sigs.append(sig)
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not item.name.startswith("_") or item.name == "__init__":
                            sig = self._format_python_sig(item, class_name=node.name)
                            sigs.append(sig)

        if sigs:
            source_files.append(py_file)
            rel = py_file.relative_to(self.root)
            lines.append(f"\n## {rel}")
            lines.extend(sigs)

    return lines, source_files

def _format_python_sig(self, node: ast.FunctionDef, class_name: str = "") -> str:
    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    name = f"{class_name}.{node.name}" if class_name else node.name

    args = []
    for arg in node.args.args:
        if arg.arg == "self":
            continue
        annotation = ""
        if arg.annotation:
            annotation = f": {ast.unparse(arg.annotation)}"
        args.append(f"{arg.arg}{annotation}")

    returns = ""
    if node.returns:
        returns = f" -> {ast.unparse(node.returns)}"

    return f"  {prefix}def {name}({', '.join(args)}){returns}"

def _extract_ts_signatures(self) -> tuple[list[str], list[Path]]:
    lines = []
    source_files = []
    pattern = re.compile(
        r'^export\s+(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)\s*(?::\s*([^\{]*))?',
        re.MULTILINE
    )

    for ts_file in self.root.rglob("*.ts"):
        if _should_skip_path(ts_file):
            continue
        try:
            content = ts_file.read_text(errors="ignore")
        except Exception:
            continue

        matches = pattern.findall(content)
        if matches:
            source_files.append(ts_file)
            rel = ts_file.relative_to(self.root)
            lines.append(f"\n## {rel}")
            for name, params, return_type in matches:
                ret = f": {return_type.strip()}" if return_type.strip() else ""
                lines.append(f"  function {name}({params}){ret}")

    return lines, source_files

class DependencyAnalyzer:
"""Analyze internal import/dependency relationships."""
def __init__(self, root: Path, languages: list[str]):
    self.root = root
    self.languages = languages

def analyze(self) -> tuple[str, list[Path]]:
    """Analyze dependencies and return text + source files."""
    lines = [f"# Internal Dependency Graph", f"# Generated: {_now()}", ""]
    source_files = []

    if "python" in self.languages:
        content, sources = self._analyze_python()
        lines.extend(content)
        source_files.extend(sources)
    
    if "typescript" in self.languages or "javascript" in self.languages:
        content, sources = self._analyze_js()
        lines.extend(content)
        source_files.extend(sources)

    return "\n".join(lines), source_files

def _analyze_python(self) -> tuple[list[str], list[Path]]:
    lines = ["## Python Imports", ""]
    source_files = []
    import_pattern = re.compile(r'^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))', re.MULTILINE)

    src_dirs = [d for d in ["src", "app", "lib", self.root.name] if (self.root / d).is_dir()]
    package_root = src_dirs[0] if src_dirs else ""

    graph = {}
    for py_file in self.root.rglob("*.py"):
        if _should_skip_path(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")
        except Exception:
            continue

        source_files.append(py_file)
        rel = str(py_file.relative_to(self.root))
        imports = []
        for match in import_pattern.finditer(content):
            module = match.group(1) or match.group(2)
            if package_root and module.startswith(package_root):
                imports.append(module)
            elif module.startswith("."):
                imports.append(module)

        if imports:
            graph[rel] = imports

    for file, imports in sorted(graph.items()):
        lines.append(f"{file}")
        for imp in imports:
            lines.append(f"  → {imp}")
        lines.append("")

    return lines, source_files

def _analyze_js(self) -> tuple[list[str], list[Path]]:
    lines = ["## JavaScript/TypeScript Imports", ""]
    source_files = []
    import_pattern = re.compile(r"""(?:import|require)\s*\(?['"](\.[^'"]+)['"]""", re.MULTILINE)

    graph = {}
    for ext in ["*.js", "*.ts", "*.tsx", "*.jsx"]:
        for f in self.root.rglob(ext):
            if _should_skip_path(f):
                continue
            try:
                content = f.read_text(errors="ignore")
            except Exception:
                continue

            source_files.append(f)
            rel = str(f.relative_to(self.root))
            imports = [m for m in import_pattern.findall(content)]
            if imports:
                graph[rel] = imports

    for file, imports in sorted(graph.items()):
        lines.append(f"{file}")
        for imp in imports:
            lines.append(f"  → {imp}")
        lines.append("")

    return lines, source_files

class DependencyGraphVisualizer:
"""Generate visual dependency graphs in Mermaid format."""
def generate_mermaid(self, dependency_text: str) -> str:
    """Convert text dependency output to Mermaid diagram."""
    lines = ["# Dependency Graph Visualization", "", "```mermaid", "graph LR"]
    
    current_file = None
    edges = []
    
    for line in dependency_text.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        if line.startswith('##'):
            continue
        
        if line.startswith('→'):
            dep = line[1:].strip()
            if current_file and dep:
                edges.append((current_file, dep))
        else:
            current_file = line
    
    def sanitize(name: str) -> str:
        return name.replace("/", "_").replace(".", "_").replace("-", "_")
    
    seen = set()
    for source, target in edges:
        source_id = sanitize(source)
        target_id = sanitize(target)
        edge = f"{source_id} --> {target_id}"
        if edge not in seen:
            lines.append(f"  {edge}")
            seen.add(edge)
    
    lines.append("```")
    return "\n".join(lines)

class DatabaseSchemaExtractor:
"""Extract database schema from various sources."""
def __init__(self, root: Path):
    self.root = root

def extract(self) -> Optional[tuple[str, list[Path]]]:
    """Extract database schema if available."""
    schema = self._from_sqlalchemy_models()
    if schema:
        return schema
    
    schema = self._from_django_models()
    if schema:
        return schema
    
    prisma_schema = self.root / "prisma/schema.prisma"
    if prisma_schema.exists():
        content = f"# Database Schema (Prisma)\n\n```prisma\n{prisma_schema.read_text()}\n```"
        return content, [prisma_schema]
    
    schema = self._from_typeorm_entities()
    if schema:
        return schema
    
    schema = self._from_live_db()
    if schema:
        return schema
    
    return None

def _from_sqlalchemy_models(self) -> Optional[tuple[str, list[Path]]]:
    """Parse SQLAlchemy models and generate schema."""
    model_files = []
    for py_file in self.root.rglob("*.py"):
        if "model" in py_file.name.lower():
            try:
                content = py_file.read_text(errors="ignore")
                if "from sqlalchemy" in content or "declarative_base" in content:
                    model_files.append(py_file)
            except Exception:
                continue
    
    if not model_files:
        return None
    
    lines = ["# Database Schema (from SQLAlchemy models)", ""]
    
    for model_file in model_files:
        try:
            content = model_file.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    has_tablename = any(
                        isinstance(item, ast.Assign) and 
                        any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in item.targets)
                        for item in node.body
                    )
                    
                    if has_tablename or any(isinstance(base, ast.Name) and "Base" in base.id for base in node.bases):
                        rel_path = model_file.relative_to(self.root)
                        lines.append(f"\n## {rel_path} — Table: {node.name}")
                        
                        for item in node.body:
                            if isinstance(item, ast.Assign):
                                try:
                                    source = ast.unparse(item)
                                    if "Column(" in source or "relationship(" in source:
                                        lines.append(f"  {source}")
                                except Exception:
                                    pass
                        lines.append("")
        except Exception:
            continue
    
    return "\n".join(lines) if len(lines) > 2 else None, model_files

def _from_django_models(self) -> Optional[tuple[str, list[Path]]]:
    """Parse Django models."""
    lines = ["# Database Schema (from Django models)", ""]
    found_models = False
    model_files = []
    
    for py_file in self.root.rglob("models.py"):
        if _should_skip_path(py_file):
            continue
        
        try:
            content = py_file.read_text()
            if "from django.db import models" not in content:
                continue
            
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    if any(isinstance(base, ast.Attribute) and base.attr == "Model" for base in node.bases):
                        found_models = True
                        model_files.append(py_file)
                        rel_path = py_file.relative_to(self.root)
                        lines.append(f"\n## {rel_path} — Model: {node.name}")
                        
                        for item in node.body:
                            if isinstance(item, ast.Assign):
                                try:
                                    source = ast.unparse(item)
                                    if "models." in source:
                                        lines.append(f"  {source}")
                                except Exception:
                                    pass
                        lines.append("")
        except Exception:
            continue
    
    return ("\n".join(lines), model_files) if found_models else None

def _from_typeorm_entities(self) -> Optional[tuple[str, list[Path]]]:
    """Extract TypeORM entities."""
    lines = ["# Database Schema (from TypeORM entities)", ""]
    found_entities = False
    entity_files = []
    
    entity_pattern = re.compile(r'@Entity\([^)]*\)\s*export\s+class\s+(\w+)\s*\{([^}]+)\}', re.DOTALL)
    column_pattern = re.compile(r'@(Column|PrimaryGeneratedColumn|ManyToOne|OneToMany|ManyToMany)\([^)]*\)')
    
    for ts_file in self.root.rglob("*.ts"):
        if _should_skip_path(ts_file) or "entity" not in ts_file.name.lower():
            continue
        
        try:
            content = ts_file.read_text()
            if "@Entity" not in content:
                continue
            
            matches = entity_pattern.findall(content)
            if matches:
                found_entities = True
                entity_files.append(ts_file)
                rel_path = ts_file.relative_to(self.root)
                lines.append(f"\n## {rel_path}")
                
                for class_name, body in matches:
                    lines.append(f"\n### Entity: {class_name}")
                    
                    for line in body.split('\n'):
                        line = line.strip()
                        if column_pattern.search(line) or line.startswith('@'):
                            lines.append(f"  {line}")
                    lines.append("")
        except Exception:
            continue
    
    return ("\n".join(lines), entity_files) if found_entities else None

def _from_live_db(self) -> Optional[tuple[str, list[Path]]]:
    """Connect to live database and extract schema."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return None
    
    try:
        if db_url.startswith("postgres"):
            result = subprocess.run(
                ["pg_dump", "--schema-only", db_url],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return f"# Database Schema (from live PostgreSQL)\n\n```sql\n{result.stdout}\n```", []
        
        elif "mysql" in db_url:
            import urllib.parse
            parsed = urllib.parse.urlparse(db_url)
            cmd = ["mysqldump", "--no-data", f"-h{parsed.hostname}", f"-u{parsed.username}"]
            if parsed.password:
                cmd.append(f"-p{parsed.password}")
            cmd.append(parsed.path.lstrip('/'))
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return f"# Database Schema (from live MySQL)\n\n```sql\n{result.stdout}\n```", []
    except Exception as e:
        print(f"  ⚠ Could not extract live DB schema: {e}")
    
    return None

class APIContractExtractor:
"""Extract API contracts from code or spec files."""
def __init__(self, root: Path):
    self.root = root

def extract(self) -> Optional[tuple[str, list[Path]]]:
    """Extract API contract if available."""
    for spec_file in ["openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json", "api-spec.yaml"]:
        path = self.root / spec_file
        if path.exists():
            content = path.read_text()
            return f"# API Contract\n\n```yaml\n{content}\n```", [path]
    
    for schema_file in ["schema.graphql", "schema.gql"]:
        path = self.root / schema_file
        if path.exists():
            content = path.read_text()
            return f"# GraphQL Schema\n\n```graphql\n{content}\n```", [path]
    
    for doc_file in ["API.md", "api/README.md", "docs/api.md"]:
        path = self.root / doc_file
        if path.exists():
            content = path.read_text()
            return f"# API Documentation\n\n{content}", [path]
    
    return None

class ScaffoldGenerator:
"""Generate CLAUDE.md and ARCHITECTURE.md scaffolds."""
def __init__(self, project: ProjectInfo):
    self.project = project

def generate_claude_md(self) -> str:
    """Generate enhanced CLAUDE.md with auto-detection."""
    enhancer = ClaudeMdEnhancer(self.project.root)
    return enhancer.generate_enhanced_claude_md(self.project)

def generate_architecture_md(self) -> str:
    p = self.project
    return f"""# Architecture Overview — {p.name}


    ## System Context
<!-- TODO: Fill in based on your project structure -->

## Data Model
<!-- TODO: Key entities and their relationships -->
## Entity A ──1:N──▶ Entity B ──N:M──▶ Entity C

## Key Design Decisions
<!-- TODO: Why did you make the choices you made? -->
# Why {p.framework}?: TODO
# Why this architecture?: TODO

## Infrastructure
{"- Docker: Yes" if p.has_docker else "- Docker: No"}
{"- CI/CD: Configured" if p.has_ci else "- CI/CD: Not configured"}
{"- Tests: Present" if p.has_tests else "- Tests: Not found"}

## External Dependencies
<!-- TODO: APIs, databases, services this connects to -->
### TODO: List external systems
"""
class ModuleSummaryGenerator:
"""Generate per-module summaries using an LLM."""
def __init__(self, root: Path, config: dict):
    self.root = root
    self.config = config
    self.client = None

def _get_client(self):
    if self.client:
        return self.client

    provider = self.config["llm_summaries"]["provider"]

    if provider == "anthropic":
        try:
            from anthropic import Anthropic
            self.client = Anthropic()
            return self.client
        except ImportError:
            print("  ⚠ pip install anthropic required for LLM summaries")
            return None
    elif provider == "openai":
        try:
            from openai import OpenAI
            self.client = OpenAI()
            return self.client
        except ImportError:
            print("  ⚠ pip install openai required for LLM summaries")
            return None

def generate(self, languages: list[str]) -> dict[str, tuple[str, list[Path]]]:
    """Generate summaries for all modules."""
    client = self._get_client()
    if not client:
        return {}

    results = {}
    extensions = {
        "python": "*.py", "typescript": "*.ts",
        "javascript": "*.js", "rust": "*.rs", "go": "*.go",
        "csharp": "*.cs",
    }

    files_to_summarize = []
    for lang in languages:
        if lang in extensions:
            for f in self.root.rglob(extensions[lang]):
                if not _should_skip_path(f):
                    try:
                        size = f.stat().st_size
                        min_size = self.config["llm_summaries"].get("min_file_size_bytes", 300)
                        if size > min_size and size < 100_000:
                            files_to_summarize.append(f)
                    except Exception:
                        continue

    max_modules = self.config["llm_summaries"].get("max_modules", 30)
    files_to_summarize.sort(key=lambda f: f.stat().st_size, reverse=True)
    files_to_summarize = files_to_summarize[:max_modules]

    if files_to_summarize:
        progress = ProgressIndicator(len(files_to_summarize), "Summarizing modules")
        
        for filepath in files_to_summarize:
            rel = filepath.relative_to(self.root)
            
            try:
                source = filepath.read_text(errors="ignore")
                if len(source) > 20_000:
                    source = source[:20_000] + "\n... [truncated]"

                summary = self._call_llm(client, str(rel), source)
                if summary:
                    key = str(rel).replace("/", "__").replace("\\", "__")
                    key = re.sub(r'\.\w+$', '.md', key)
                    content = f"# Module: {rel}\n\n{summary}\n"
                    results[key] = (content, [filepath])
            except Exception as e:
                print(f"\n  ⚠ Error summarizing {rel}: {e}")
            
            progress.update()
        
        progress.finish()

    return results

def _call_llm(self, client, filepath: str, source: str) -> Optional[str]:
    prompt = textwrap.dedent(f"""\
    Analyze this source module and produce a concise summary:
    Purpose: One sentence.
    Public Interface: Key functions/classes with brief descriptions.
    Dependencies: Internal and external dependencies.
    Key Patterns: Design patterns, invariants, gotchas.
    State/Data Flow: How data moves through this module.
    Be precise and concise. This will help another LLM understand and modify this code.

    File: {filepath}
    {source}
    """)

    provider = self.config["llm_summaries"]["provider"]
    model = self.config["llm_summaries"]["model"]

        if provider == "anthropic":
            response = client.messages.create(
                model=model,
                max_tokens=1200,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        elif provider == "openai":
            response = client.chat.completions.create(
                model=model,
                max_tokens=1200,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content


# ──────────────────────────────────────────────
# Main Orchestrator with Incremental Updates
# ──────────────────────────────────────────────

class LLMContextGenerator:
    """Main orchestrator with smart incremental updates."""

    def __init__(self, root: Path, config: Optional[dict] = None, quick_mode: bool = False, force: bool = False):
        self.root = root
        self.config = config or load_config(self.root)
        self.output_dir = self.root / self.config["output_dir"]
        self.quick_mode = quick_mode
        self.updater = SmartUpdater(self.root, self.config, force=force)

    def generate(self):
        mode = "Quick update" if self.quick_mode else "Force regeneration" if self.updater.force else "Incremental update" if self.updater.old_manifest else "Full generation"
        
        print(f"\n{'='*60}")
        print(f"  LLM Context Generator v{VERSION}")
        print(f"  Project: {self.root}")
        print(f"  Mode: {mode}")
        print(f"{'='*60}\n")

        print("→ Detecting project type...")
        detector = ProjectDetector(self.root)
        project = detector.detect()

        print(f"  Name: {project.name}")
        print(f"  Languages: {', '.join(project.languages) or 'unknown'}")
        print(f"  Framework: {project.framework}")
        if self.updater.old_manifest:
            print(f"  Last generated: {self.updater.old_manifest.generated_at}")
        print()

        self.output_dir.mkdir(parents=True, exist_ok=True)

        gen = self.config["generate"]

        if self.quick_mode:
            gen = {k: v for k, v in gen.items() if k not in ['module_summaries', 'db_schema']}

        if gen.get("tree"):
            should_regen, reason = self.updater.should_regenerate("tree.txt")
            if should_regen:
                print(f"→ Generating file tree... ({reason})")
                tree, sources = TreeGenerator(self.root, self.config).generate()
                self._write("tree.txt", tree)
                self.updater.mark_generated("tree.txt", tree, sources)
            else:
                print(f"  ✓ tree.txt ({reason})")
                self.updater.mark_skipped("tree.txt")

        if gen.get("schemas"):
            print("→ Checking schemas/types...")
            extractor = SchemaExtractor(self.root, project.languages)
            schemas = extractor.extract()
            
            for filename, (content, sources) in schemas.items():
                if not content.strip():
                    continue
                
                should_regen, reason = self.updater.should_regenerate(filename, sources)
                if should_regen:
                    print(f"  Extracting {filename}... ({reason})")
                    self._write(filename, content)
                    self.updater.mark_generated(filename, content, sources)
                else:
                    print(f"  ✓ {filename} ({reason})")
                    self.updater.mark_skipped(filename)

        if gen.get("routes") or gen.get("public_api"):
            api = APIExtractor(self.root, project.languages, project.framework)

            if gen.get("routes"):
                routes, sources = api.extract_routes()
                if routes:
                    should_regen, reason = self.updater.should_regenerate("routes.txt", sources)
                    if should_regen:
                        print(f"→ Extracting routes... ({reason})")
                        self._write("routes.txt", routes)
                        self.updater.mark_generated("routes.txt", routes, sources)
                    else:
                        print(f"  ✓ routes.txt ({reason})")
                        self.updater.mark_skipped("routes.txt")

            if gen.get("public_api"):
                public_api, sources = api.extract_public_api()
                if public_api:
                    should_regen, reason = self.updater.should_regenerate("public-api.txt", sources)
                    if should_regen:
                        print(f"→ Extracting public API... ({reason})")
                        self._write("public-api.txt", public_api)
                        self.updater.mark_generated("public-api.txt", public_api, sources)
                    else:
                        print(f"  ✓ public-api.txt ({reason})")
                        self.updater.mark_skipped("public-api.txt")

        if gen.get("dependencies"):
            analyzer = DependencyAnalyzer(self.root, project.languages)
            deps, sources = analyzer.analyze()
            
            if deps:
                should_regen, reason = self.updater.should_regenerate("dependency-graph.txt", sources)
                if should_regen:
                    print(f"→ Analyzing dependencies... ({reason})")
                    self._write("dependency-graph.txt", deps)
                    self.updater.mark_generated("dependency-graph.txt", deps, sources)
                    
                    if gen.get("dependency_graph_mermaid"):
                        visualizer = DependencyGraphVisualizer()
                        mermaid = visualizer.generate_mermaid(deps)
                        self._write("dependency-graph.md", mermaid)
                        self.updater.mark_generated("dependency-graph.md", mermaid, sources)
                else:
                    print(f"  ✓ dependency-graph.txt ({reason})")
                    self.updater.mark_skipped("dependency-graph.txt")
                    if gen.get("dependency_graph_mermaid"):
                        self.updater.mark_skipped("dependency-graph.md")

        if gen.get("db_schema"):
            extractor = DatabaseSchemaExtractor(self.root)
            result = extractor.extract()
            
            if result:
                schema, sources = result
                should_regen, reason = self.updater.should_regenerate("db-schema.sql", sources)
                if should_regen:
                    print(f"→ Extracting database schema... ({reason})")
                    self._write("db-schema.sql", schema)
                    self.updater.mark_generated("db-schema.sql", schema, sources)
                else:
                    print(f"  ✓ db-schema.sql ({reason})")
                    self.updater.mark_skipped("db-schema.sql")

        if gen.get("api_contract"):
            extractor = APIContractExtractor(self.root)
            result = extractor.extract()
            
            if result:
                content, sources = result
                should_regen, reason = self.updater.should_regenerate("api-contract.md", sources)
                if should_regen:
                    print(f"→ Extracting API contract... ({reason})")
                    self._write("api-contract.md", content)
                    self.updater.mark_generated("api-contract.md", content, sources)
                else:
                    print(f"  ✓ api-contract.md ({reason})")
                    self.updater.mark_skipped("api-contract.md")

        if gen.get("env_shape"):
            for env_file in [".env.example", ".env.template", ".env.sample"]:
                env_path = self.root / env_file
                if env_path.exists():
                    should_regen, reason = self.updater.should_regenerate("env-shape.txt", [env_path])
                    if should_regen:
                        print(f"→ Copying {env_file}... ({reason})")
                        content = env_path.read_text(errors="ignore")
                        self._write("env-shape.txt", content)
                        self.updater.mark_generated("env-shape.txt", content, [env_path])
                    else:
                        print(f"  ✓ env-shape.txt ({reason})")
                        self.updater.mark_skipped("env-shape.txt")
                    break

        if gen.get("dependencies"):
            for dep_file in ["requirements.txt", "pyproject.toml", "package.json", "Cargo.toml", "go.mod", "Gemfile"]:
                dep_path = self.root / dep_file
                if dep_path.exists():
                    should_regen, reason = self.updater.should_regenerate(dep_file, [dep_path])
                    if should_regen:
                        print(f"→ Copying {dep_file}... ({reason})")
                        content = dep_path.read_text(errors="ignore")
                        self._write(dep_file, content)
                        self.updater.mark_generated(dep_file, content, [dep_path])
                    else:
                        print(f"  ✓ {dep_file} ({reason})")
                        self.updater.mark_skipped(dep_file)

        if gen.get("recent_activity"):
            print("→ Capturing recent git activity...")
            try:
                log = subprocess.run(
                    ["git", "log", "--oneline", "-20"],
                    capture_output=True, text=True, cwd=self.root
                )
                if log.returncode == 0:
                    self._write("recent-commits.txt", log.stdout)
                    self.updater.mark_generated("recent-commits.txt", log.stdout)

                diff = subprocess.run(
                    ["git", "diff", "--stat", "HEAD~5"],
                    capture_output=True, text=True, cwd=self.root
                )
                if diff.returncode == 0:
                    self._write("recent-changes.txt", diff.stdout)
                    self.updater.mark_generated("recent-changes.txt", diff.stdout)
            except Exception:
                pass

        if gen.get("claude_md_scaffold"):
            claude_path = self.root / "CLAUDE.md"
            should_regen, reason = self.updater.should_regenerate("../CLAUDE.md")
            
            if should_regen:
                print(f"→ Generating enhanced CLAUDE.md scaffold... ({reason})")
                scaffold = ScaffoldGenerator(project)
                content = scaffold.generate_claude_md()
                claude_path.write_text(content)
                self.updater.mark_generated("../CLAUDE.md", content, is_new=True)
            else:
                print(f"  ✓ CLAUDE.md ({reason})")
                self.updater.mark_skipped("../CLAUDE.md")

        if gen.get("architecture_md_scaffold"):
            arch_path = self.root / "ARCHITECTURE.md"
            should_regen, reason = self.updater.should_regenerate("../ARCHITECTURE.md")
            
            if should_regen:
                print(f"→ Generating ARCHITECTURE.md scaffold... ({reason})")
                scaffold = ScaffoldGenerator(project)
                content = scaffold.generate_architecture_md()
                arch_path.write_text(content)
                self.updater.mark_generated("../ARCHITECTURE.md", content, is_new=True)
            else:
                print(f"  ✓ ARCHITECTURE.md ({reason})")
                self.updater.mark_skipped("../ARCHITECTURE.md")

        if gen.get("module_summaries") and not self.quick_mode:
            print("→ Generating LLM-powered module summaries...")
            summary_gen = ModuleSummaryGenerator(self.root, self.config)
            summaries = summary_gen.generate(project.languages)

            modules_dir = self.output_dir / "modules"
            modules_dir.mkdir(exist_ok=True)

            for filename, (content, sources) in summaries.items():
                module_path = f"modules/{filename}"
                (modules_dir / filename).write_text(content)
                self.updater.mark_generated(module_path, content, sources)

            if summaries:
                index = "# Module Summaries Index\n\n"
                for f in sorted(summaries.keys()):
                    index += f"- [{f}](modules/{f})\n"
                self._write("module-index.md", index)
                self.updater.mark_generated("module-index.md", index)

        self.updater.new_manifest.save(self.root)

        print(f"\n{'='*60}")
        print(f"  ✅ Context generated in {self.output_dir}")
        self.updater.print_summary()

        if self.updater.stats["regenerated"] > 0 or self.updater.stats["new"] > 0:
            print("Updated/new files:")
            for f in sorted(self.output_dir.rglob("*")):
                if f.is_file():
                    rel = f.relative_to(self.output_dir)
                    size = _human_size(f.stat().st_size)
                    
                    entry = self.updater.new_manifest.get_entry(str(rel))
                    if entry and entry.generated_at == self.updater.new_manifest.generated_at:
                        print(f"  • {rel} ({size})")

    def _write(self, filename: str, content: str):
        """Write a file to the output directory."""
        if filename.startswith("../"):
            path = (self.output_dir / filename).resolve()
        else:
            path = self.output_dir / filename
        
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


# ──────────────────────────────────────────────
# Watch Mode
# ──────────────────────────────────────────────

def watch_mode(root: Path, config: dict):
    """Enhanced watch mode with smarter debouncing."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("  ⚠ Watch mode requires: pip install watchdog")
        sys.exit(1)
    
    class SmartContextUpdateHandler(FileSystemEventHandler):
        def __init__(self):
            self.last_update = time.time()
            self.pending_changes = set()
            self.debounce_timer = None
        
        def on_any_event(self, event):
            """Handle any file system event."""
            if event.is_directory:
                return
            
            path = Path(event.src_path)
            
            if ".llm-context" in path.parts or _should_skip_path(path):
                return
            
            source_extensions = {'.py', '.ts', '.js', '.rs', '.go', '.cs', '.rb', '.java', '.jsx', '.tsx'}
            if path.suffix not in source_extensions:
                return
            
            if not path.exists():
                return
            
            self.pending_changes.add(path)
            
            if self.debounce_timer:
                self.debounce_timer.cancel()
            
            self.debounce_timer = threading.Timer(2.0, self.process_changes)
            self.debounce_timer.start()
        
        def process_changes(self):
            """Process accumulated changes."""
            if not self.pending_changes:
                return
            
            changes = self.pending_changes.copy()
            self.pending_changes.clear()
            
            print(f"\n{'─'*60}")
            print(f"  📝 Detected {len(changes)} file change(s)")
            
            for p in sorted(list(changes)[:10]):
                try:
                    rel_path = p.relative_to(root)
                    print(f"     • {rel_path}")
                except ValueError:
                    print(f"     • {p.name}")
            
            if len(changes) > 10:
                print(f"     ... and {len(changes) - 10} more")
            
            print(f"{'─'*60}\n")
            
            try:
                generator = LLMContextGenerator(root, config, quick_mode=True)
                generator.generate()
            except Exception as e:
                print(f"  ❌ Error during update: {e}")
            
            self.last_update = time.time()
    
    handler = SmartContextUpdateHandler()
    observer = Observer()
    observer.schedule(handler, str(root), recursive=True)
    observer.start()
    
    print(f"👁️  Watching {root} for changes...")
    print("   Quick updates will run 2 seconds after you stop editing")
    print("   Press Ctrl+C to stop\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  Stopping watch mode...")
        if handler.debounce_timer:
            handler.debounce_timer.cancel()
        observer.stop()
    observer.join()


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate LLM context files for a codebase with smart incremental updates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Full generation (or incremental if manifest exists)
  %(prog)s --quick-update            # Fast incremental update (skip expensive operations)
  %(prog)s --force                   # Force full regeneration
  %(prog)s --watch                   # Watch mode (auto-update on file changes)
  %(prog)s --with-summaries          # Include LLM-generated module summaries
        """
    )
    parser.add_argument("path", nargs="?", default=".", help="Path to project root (default: current directory)")
    parser.add_argument("--quick-update", "-q", action="store_true", help="Fast incremental update (skip expensive operations like LLM summaries)")
    parser.add_argument("--force", "-f", action="store_true", help="Force full regeneration (ignore existing manifest)")
    parser.add_argument("--watch", "-w", action="store_true", help="Watch for file changes and auto-update")
    parser.add_argument("--with-summaries", action="store_true", help="Generate LLM-powered module summaries (requires API key)")
    parser.add_argument("--output", "-o", help="Output directory (default: .llm-context)")
    parser.add_argument("--config", "-c", help="Path to config file (default: llm-context.yml in project root)")
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {VERSION}")

    args = parser.parse_args()

    root = Path(args.path).resolve()
    
    if args.config:
        config_path = Path(args.config)
        if config_path.suffix in ('.yml', '.yaml'):
            try:
                import yaml
                with open(config_path) as f:
                    config = yaml.safe_load(f)
                _deep_merge(DEFAULT_CONFIG.copy(), config)
            except ImportError:
                print("  ⚠ YAML config requires: pip install pyyaml")
                sys.exit(1)
        else:
            with open(config_path) as f:
                config = json.load(f)
            _deep_merge(DEFAULT_CONFIG.copy(), config)
    else:
        config = load_config(root)

    if args.output:
        config["output_dir"] = args.output

    if args.with_summaries:
        config["generate"]["module_summaries"] = True

    if args.watch:
        watch_mode(root, config)
        return

    generator = LLMContextGenerator(root=root, config=config, quick_mode=args.quick_update, force=args.force)
    generator.generate()


if __name__ == "__main__":
    main()
