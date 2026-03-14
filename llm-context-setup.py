#!/usr/bin/env python3
"""
llm-context-setup.py - Single-file distribution

This file can work standalone OR use the ccc package if available.
When the package is available, it delegates to ccc.cli.main().
Otherwise, it includes all functionality inline


Features:
- Auto-detects project type and languages
- Generates context files optimized for LLMs
- Smart incremental updates (only regenerates what changed)
- Multiple operation modes: full, quick, watch
- Auto-detects conventions for enhanced CLAUDE.md
- Database schema extraction
- Security modes: offline, private-ai, public-ai
- Symbol indexing for navigation
- Zero required dependencies for core functionality

Usage:
    python3 llm-context-setup.py                    # Full generation
    python3 llm-context-setup.py --quick-update     # Fast incremental update
    python3 llm-context-setup.py --watch            # Watch mode
    python3 llm-context-setup.py --force            # Force full regeneration
    python3 llm-context-setup.py --doctor           # Diagnostics

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
import fnmatch
import argparse
from pathlib import Path
from typing import Optional, Literal, Any, Tuple, List, Dict, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


VERSION = "0.4.0"

# Try to use installed package
try:
    from ccc.cli import main as ccc_main
    USING_PACKAGE = True
except ImportError:
    USING_PACKAGE = False

if USING_PACKAGE:
    # Delegate to package
    if __name__ == "__main__":
        sys.exit(ccc_main())
else:
# Embedded standalone version - Wrapper starts
    
# Try to import from package
try:
    from ccc.utils.files import (
        is_binary_file,
        safe_read_text,
        safe_write_text,
        should_skip_path,
    )
    from ccc.utils.hashing import hash_file_quick, compute_fingerprint
    from ccc.utils.formatting import get_timestamp, human_readable_size
    USING_PACKAGE = True
except ImportError:
    USING_PACKAGE = False


MANIFEST_VERSION = "4"


BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp",
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".obj",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".pyc", ".pyo", ".class", ".o", ".a", ".lib",
    ".sqlite", ".db", ".sqlite3",
    ".ico", ".icns",
    ".DS_Store",
}


EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".env",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".next",
    ".nuxt",
    "target",
    ".terraform",
    "vendor",
    "coverage",
    ".coverage",
    "htmlcov",
    ".idea",
    ".vscode",
    "eggs",
    ".eggs",
    "*.egg-info",
    ".cache",
    ".parcel-cache",
    ".turbo",
}


SENSITIVE_PATTERNS = [
    "**/.env",
    "**/.env.*",
    "**/secrets/**",
    "**/certs/**",
    "**/keys/**",
    "**/credentials/**",
    "**/*_key",
    "**/*_secret",
    "**/*.pem",
    "**/*.key",
]


UpdateStrategy = Literal["always", "if-changed", "if-missing", "never"]
SecurityMode = Literal["offline", "private-ai", "public-ai"]

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
            "modules/*.md": "if-changed",
            "../CLAUDE.md": "if-missing",
            "../ARCHITECTURE.md": "if-missing",
            "external-dependencies.json": "if-changed",
        },
    }


def is_binary_file(path: Path) -> bool:
    """Check if a file is binary."""
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
        return b"\0" in chunk
    except Exception:
        return True


def safe_read_text(path: Path) -> Optional[str]:
    """Safely read a text file with UTF-8 encoding."""
    if is_binary_file(path):
        return None
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


def safe_write_text(path: Path, content: str) -> bool:
    """Safely write text to a file with UTF-8 encoding."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False


def get_timestamp() -> str:
    """Get current UTC timestamp as string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def human_readable_size(size_bytes: int) -> str:
    """Convert bytes to human readable string."""
    for unit in ["B", "KB", "MB"]:
        if size_bytes < 1024:
            if unit == "B":
                return f"{size_bytes:.0f}{unit}"
            return f"{size_bytes:.1f}{unit}"
        size_bytes = size_bytes / 1024
    return f"{size_bytes:.1f}GB"


def should_skip_path(path: Path) -> bool:
    """Check if path should be skipped based on exclusion rules."""
    path_parts = set(path.parts)
    if path_parts & EXCLUDE_DIRS:
        return True
    path_str = str(path)
    for pattern in SENSITIVE_PATTERNS:
        if fnmatch.fnmatch(path_str, pattern):
            return True
    return False


def hash_file_quick(path: Path) -> str:
    """Generate a quick hash of a file."""
    try:
        size = path.stat().st_size
        if size > 100000:
            with open(path, "rb") as f:
                start = f.read(10000)
                f.seek(-10000, 2)
                end = f.read(10000)
                data = start + end
        else:
            data = path.read_bytes()
        return hashlib.md5(data).hexdigest()[:12]
    except Exception:
        return ""


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


@dataclass
class FileManifestEntry:
    """Metadata for a generated file."""
    hash: str
    size: int
    generated_at: str
    source_files: List[str] = field(default_factory=list)
    source_hashes: List[str] = field(default_factory=list)
    strategy: str = "always"


@dataclass
class GenerationManifest:
    """Tracks what was generated and when."""
    version: str
    generated_at: str
    project_fingerprint: str
    files: Dict[str, Dict[str, Any]]
    
    @classmethod
    def load(cls, root: Path) -> Optional["GenerationManifest"]:
        """Load manifest from disk."""
        manifest_file = root / ".llm-context" / "manifest.json"
        if not manifest_file.exists():
            return None
        try:
            content = safe_read_text(manifest_file)
            if not content:
                return None
            data = json.loads(content)
            if data.get("version") != MANIFEST_VERSION:
                print(f"  Manifest version mismatch, will regenerate")
                return None
            return cls(
                version=data["version"],
                generated_at=data["generated_at"],
                project_fingerprint=data["project_fingerprint"],
                files=data["files"],
            )
        except Exception as e:
            print(f"  Warning: Could not load manifest: {e}")
            return None
    
    def save(self, root: Path) -> None:
        """Save manifest to disk."""
        manifest_file = root / ".llm-context" / "manifest.json"
        data = asdict(self)
        safe_write_text(manifest_file, json.dumps(data, indent=2))
    
    def get_entry(self, filename: str) -> Optional[FileManifestEntry]:
        """Get manifest entry for a file."""
        entry_dict = self.files.get(filename)
        if not entry_dict:
            return None
        return FileManifestEntry(**entry_dict)
    
    def set_entry(self, filename: str, entry: FileManifestEntry) -> None:
        """Set manifest entry for a file."""
        self.files[filename] = asdict(entry)


@dataclass
class ProjectInfo:
    """Auto-detected project metadata."""
    root: Path
    name: str = ""
    languages: List[str] = field(default_factory=list)
    framework: str = ""
    package_manager: str = ""
    has_docker: bool = False
    has_ci: bool = False
    has_tests: bool = False
    entry_points: List[str] = field(default_factory=list)
    description: str = ""
    python_version: str = ""
    node_version: str = ""


class SecurityManager:
    """Manage security settings and audit logging."""
    
    def __init__(self, root: Path, config: dict):
        self.root = root
        self.config = config
        security_config = config.get("security", {})
        self.mode = security_config.get("mode", "offline")
        self.audit_enabled = security_config.get("audit_log", True)
        self.redact_secrets = security_config.get("redact_secrets", True)
    
    def is_ai_enabled(self) -> bool:
        """Check if AI features are enabled."""
        return self.mode in ["private-ai", "public-ai"]
    
    def log_audit(self, action: str, details: dict) -> None:
        """Log an audit event."""
        if not self.audit_enabled:
            return
        audit_file = self.root / ".llm-context" / "audit.log"
        entry = {
            "timestamp": get_timestamp(),
            "action": action,
            "mode": self.mode,
        }
        entry.update(details)
        try:
            existing = ""
            if audit_file.exists():
                existing = safe_read_text(audit_file) or ""
            new_entry = json.dumps(entry) + "\n"
            safe_write_text(audit_file, existing + new_entry)
        except Exception:
            pass
    
    def redact_content(self, content: str) -> str:
        """Redact sensitive patterns from content."""
        if not self.redact_secrets:
            return content
        patterns = [
            (r"(API[_-]?KEY\s*=\s*)[\"']?[^\"'\s]+[\"']?", r"\1****"),
            (r"(PASSWORD\s*=\s*)[\"']?[^\"'\s]+[\"']?", r"\1****"),
            (r"(SECRET\s*=\s*)[\"']?[^\"'\s]+[\"']?", r"\1****"),
            (r"(TOKEN\s*=\s*)[\"']?[^\"'\s]+[\"']?", r"\1****"),
            (r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", "Bearer ****"),
        ]
        result = content
        for pattern, replacement in patterns:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        return result
    
    def print_status(self) -> None:
        """Print security status."""
        print("")
        print("=" * 60)
        print("  Security Status")
        print("=" * 60)
        print(f"  Mode: {self.mode.upper()}")
        if self.mode == "offline":
            print("  External APIs: DISABLED")
            print("  AI Features: DISABLED")
        elif self.mode == "private-ai":
            print("  External APIs: ALLOWED (Private infrastructure)")
            print("  AI Features: ENABLED")
        else:
            print("  External APIs: ALLOWED (Public services)")
            print("  AI Features: ENABLED")
            print("  WARNING: Code may be sent to external AI services")
        redact_status = "ENABLED" if self.redact_secrets else "DISABLED"
        audit_status = "ENABLED" if self.audit_enabled else "DISABLED"
        print(f"  Secret Redaction: {redact_status}")
        print(f"  Audit Logging: {audit_status}")
        print("=" * 60)
        print("")


class SmartUpdater:
    """Manages incremental updates based on file changes."""
    
    def __init__(self, root: Path, config: dict, force: bool = False):
        self.root = root
        self.config = config
        self.force = force
        if force:
            self.old_manifest = None
        else:
            self.old_manifest = GenerationManifest.load(root)
        self.new_manifest = GenerationManifest(
            version=MANIFEST_VERSION,
            generated_at=get_timestamp(),
            project_fingerprint=self._compute_fingerprint(),
            files={},
        )
        self.stats = {"regenerated": 0, "skipped": 0, "new": 0}
    
    def _compute_fingerprint(self) -> str:
        """Compute project fingerprint from key files."""
        key_files = [
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
            "go.mod",
            "requirements.txt",
            "poetry.lock",
            "package-lock.json",
            ".env.example",
            "docker-compose.yml",
        ]
        parts = []
        for filename in key_files:
            path = self.root / filename
            if path.exists():
                file_hash = hash_file_quick(path)
                parts.append(f"{filename}:{file_hash}")
        combined = "|".join(sorted(parts))
        return hashlib.md5(combined.encode()).hexdigest()[:16]
    
    def _get_strategy(self, filepath: str) -> str:
        """Get update strategy for a file."""
        strategies = self.config.get("update_strategies", {})
        if filepath in strategies:
            return strategies[filepath]
        for pattern, strategy in strategies.items():
            if "*" in pattern:
                if fnmatch.fnmatch(filepath, pattern):
                    return strategy
            elif filepath.endswith(pattern):
                return strategy
        return "always"
    
    def should_regenerate(
        self, filepath: str, source_files: List[Path] = None
    ) -> Tuple[bool, str]:
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
                new_hashes = [hash_file_quick(f) for f in source_files]
                if new_hashes != old_hashes:
                    return True, "source files changed"
            
            old_fp = self.old_manifest.project_fingerprint
            new_fp = self.new_manifest.project_fingerprint
            if old_fp != new_fp:
                return True, "project dependencies changed"
            
            return False, "up to date"
        
        return True, "default"
    
    def mark_generated(
        self,
        filepath: str,
        content: str,
        source_files: List[Path] = None,
        is_new: bool = False,
    ) -> None:
        """Record that a file was generated."""
        strategy = self._get_strategy(filepath)
        src_files = source_files or []
        entry = FileManifestEntry(
            hash=hashlib.sha256(content.encode()).hexdigest()[:16],
            size=len(content),
            generated_at=get_timestamp(),
            source_files=[str(f.relative_to(self.root)) for f in src_files],
            source_hashes=[hash_file_quick(f) for f in src_files],
            strategy=strategy,
        )
        self.new_manifest.set_entry(filepath, entry)
        if is_new:
            self.stats["new"] += 1
        else:
            self.stats["regenerated"] += 1
    
    def mark_skipped(self, filepath: str) -> None:
        """Record that a file was skipped."""
        if self.old_manifest:
            old_entry = self.old_manifest.get_entry(filepath)
            if old_entry:
                self.new_manifest.set_entry(filepath, old_entry)
        self.stats["skipped"] += 1
    
    def print_summary(self) -> None:
        """Print update statistics."""
        total = sum(self.stats.values())
        print("")
        print("-" * 60)
        print("  Update Summary:")
        print(f"  - Regenerated: {self.stats['regenerated']}")
        print(f"  - Skipped (up to date): {self.stats['skipped']}")
        print(f"  - New files: {self.stats['new']}")
        print(f"  - Total: {total}")
        print("-" * 60)
        print("")


class ProgressIndicator:
    """Simple progress indicator for terminal."""
    
    def __init__(self, total: int, description: str = "Processing"):
        self.total = total
        self.current = 0
        self.description = description
        self.start_time = time.time()
    
    def update(self, increment: int = 1) -> None:
        """Update progress."""
        self.current += increment
        if self.total > 0:
            percent = (self.current / self.total) * 100
        else:
            percent = 0
        
        elapsed = time.time() - self.start_time
        if self.current > 0:
            eta = (elapsed / self.current) * (self.total - self.current)
            if eta > 0:
                eta_str = f"ETA: {int(eta)}s"
            else:
                eta_str = "Done"
        else:
            eta_str = ""
        
        bar_length = 30
        filled = int(bar_length * percent / 100)
        bar = "#" * filled + "-" * (bar_length - filled)
        
        line = f"\r  {self.description}: [{bar}] {percent:5.1f}% "
        line += f"({self.current}/{self.total}) {eta_str}"
        print(line, end="", flush=True)
    
    def finish(self) -> None:
        """Mark as complete."""
        print("")


class ProjectDetector:
    """Detect project type, languages, and framework."""
    
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
        """Detect project information."""
        info = ProjectInfo(root=self.root)
        info.name = self.root.name
        info.languages = self._detect_languages()
        self._detect_from_configs(info)
        info.framework = self._detect_framework()
        info.has_docker = self._has_docker()
        info.has_ci = self._has_ci()
        info.has_tests = self._has_tests()
        return info
    
    def _detect_languages(self) -> List[str]:
        """Detect programming languages used."""
        extensions = {}
        for f in self._walk_files(max_files=500):
            ext = f.suffix.lower()
            extensions[ext] = extensions.get(ext, 0) + 1
        
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".cs": "csharp",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
        }
        
        langs = []
        sorted_exts = sorted(extensions.items(), key=lambda x: -x[1])
        for ext, count in sorted_exts:
            if ext in lang_map and count >= 2:
                lang = lang_map[ext]
                if lang not in langs:
                    langs.append(lang)
        
        return langs[:5]
    
    def _detect_from_configs(self, info: ProjectInfo) -> None:
        """Detect info from configuration files."""
        pyproject = self.root / "pyproject.toml"
        if pyproject.exists():
            info.package_manager = "poetry/pip"
            content = safe_read_text(pyproject) or ""
            match = re.search(r'description\s*=\s*"([^"]*)"', content)
            if match:
                info.description = match.group(1)
            match = re.search(r'python\s*=\s*"([^"]*)"', content)
            if match:
                info.python_version = match.group(1)
        
        package_json = self.root / "package.json"
        if package_json.exists():
            info.package_manager = "npm/yarn"
            content = safe_read_text(package_json)
            if content:
                try:
                    pkg = json.loads(content)
                    info.description = pkg.get("description", "")
                    main = pkg.get("main")
                    if main:
                        info.entry_points.append(main)
                except Exception:
                    pass
        
        if (self.root / "Cargo.toml").exists():
            info.package_manager = "cargo"
        
        if (self.root / "go.mod").exists():
            info.package_manager = "go modules"
    
    def _detect_framework(self) -> str:
        """Detect frameworks used."""
        files_to_scan = list(self._walk_files(max_files=100))
        content_sample = ""
        
        for f in files_to_scan[:50]:
            try:
                if f.stat().st_size < 50000:
                    text = safe_read_text(f)
                    if text:
                        content_sample += text
            except Exception:
                continue
        
        dep_files = [
            "requirements.txt",
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
            "go.mod",
        ]
        for dep_file in dep_files:
            path = self.root / dep_file
            if path.exists():
                text = safe_read_text(path)
                if text:
                    content_sample += text
        
        detected = []
        content_lower = content_sample.lower()
        for framework, indicators in self.FRAMEWORK_INDICATORS.items():
            for indicator in indicators:
                if indicator.lower() in content_lower:
                    detected.append(framework)
                    break
        
        if detected:
            return ", ".join(detected)
        return "unknown"
    
    def _has_docker(self) -> bool:
        """Check for Docker files."""
        return (
            (self.root / "Dockerfile").exists()
            or (self.root / "docker-compose.yml").exists()
            or (self.root / "docker-compose.yaml").exists()
        )
    
    def _has_ci(self) -> bool:
        """Check for CI/CD configuration."""
        return (
            (self.root / ".github" / "workflows").exists()
            or (self.root / ".gitlab-ci.yml").exists()
            or (self.root / "Jenkinsfile").exists()
            or (self.root / ".circleci").exists()
        )
    
    def _has_tests(self) -> bool:
        """Check for test directories."""
        return (
            (self.root / "tests").exists()
            or (self.root / "test").exists()
            or (self.root / "__tests__").exists()
            or (self.root / "spec").exists()
        )
    
    def _walk_files(self, max_files: int = 1000):
        """Walk files in project, respecting exclusions."""
        count = 0
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
            for filename in filenames:
                if count >= max_files:
                    return
                filepath = Path(dirpath) / filename
                if not should_skip_path(filepath):
                    yield filepath
                    count += 1


class ClaudeMdEnhancer:
    """Auto-detect conventions for enhanced CLAUDE.md."""
    
    def __init__(self, root: Path):
        self.root = root
    
    def detect_conventions(self) -> dict:
        """Detect project conventions."""
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
        """Detect error handling pattern."""
        py_files = list(self.root.rglob("*.py"))[:20]
        result_count = 0
        exception_count = 0
        
        for f in py_files:
            if should_skip_path(f):
                continue
            content = safe_read_text(f)
            if not content:
                continue
            if "Result[" in content or "from result import" in content:
                result_count += 1
            exception_count += content.count("raise ")
        
        if result_count > 5:
            return "Result pattern (functional error handling)"
        elif exception_count > 20:
            return "Exception-based (try/except)"
        return "Mixed/unclear (TODO: document your strategy)"
    
    def _detect_test_framework(self) -> dict:
        """Detect test frameworks."""
        frameworks = {}
        
        if (self.root / "pytest.ini").exists():
            frameworks["python"] = "pytest"
        else:
            pyproject = self.root / "pyproject.toml"
            if pyproject.exists():
                content = safe_read_text(pyproject) or ""
                if "pytest" in content:
                    frameworks["python"] = "pytest"
        
        if not frameworks.get("python"):
            test_files = list(self.root.rglob("test_*.py"))[:5]
            for tf in test_files:
                content = safe_read_text(tf) or ""
                if "import pytest" in content:
                    frameworks["python"] = "pytest"
                    break
                if "import unittest" in content:
                    frameworks["python"] = "unittest"
                    break
        
        package_json = self.root / "package.json"
        if package_json.exists():
            content = safe_read_text(package_json)
            if content:
                try:
                    pkg = json.loads(content)
                    deps = {}
                    deps.update(pkg.get("dependencies", {}))
                    deps.update(pkg.get("devDependencies", {}))
                    if "jest" in deps:
                        frameworks["javascript"] = "jest"
                    elif "vitest" in deps:
                        frameworks["javascript"] = "vitest"
                    elif "mocha" in deps:
                        frameworks["javascript"] = "mocha"
                except Exception:
                    pass
        
        return frameworks
    
    def _detect_async_usage(self) -> Optional[str]:
        """Detect async/await usage."""
        py_files = list(self.root.rglob("*.py"))[:30]
        async_count = 0
        total_functions = 0
        
        for f in py_files:
            if should_skip_path(f):
                continue
            content = safe_read_text(f)
            if not content:
                continue
            try:
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
            pct = int(async_ratio * 100)
            return f"Heavy async (~{pct}% of functions)"
        elif async_ratio > 0.1:
            return "Mixed sync/async"
        return None
    
    def _detect_orm(self) -> Optional[str]:
        """Detect ORM/database layer."""
        orms = []
        
        for config_file in ["requirements.txt", "pyproject.toml"]:
            path = self.root / config_file
            if path.exists():
                content = (safe_read_text(path) or "").lower()
                if "sqlalchemy" in content:
                    orms.append("SQLAlchemy")
                if "django" in content:
                    orms.append("Django ORM")
                if "tortoise" in content:
                    orms.append("Tortoise ORM")
        
        package_json = self.root / "package.json"
        if package_json.exists():
            content = safe_read_text(package_json)
            if content:
                try:
                    pkg = json.loads(content)
                    deps = {}
                    deps.update(pkg.get("dependencies", {}))
                    deps.update(pkg.get("devDependencies", {}))
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
        
        if orms:
            return ", ".join(orms)
        return None
    
    def _detect_api_style(self) -> str:
        """Detect API style (REST/GraphQL/gRPC)."""
        styles = []
        
        graphql_files = ["schema.graphql", "schema.gql"]
        for gf in graphql_files:
            if (self.root / gf).exists():
                styles.append("GraphQL")
                break
        
        dep_files = ["requirements.txt", "pyproject.toml", "package.json"]
        for dep_file in dep_files:
            path = self.root / dep_file
            if path.exists():
                content = (safe_read_text(path) or "").lower()
                if "graphql" in content and "GraphQL" not in styles:
                    styles.append("GraphQL")
                if "grpc" in content or "protobuf" in content:
                    if "gRPC" not in styles:
                        styles.append("gRPC")
        
        route_count = 0
        py_files = list(self.root.rglob("*.py"))[:20]
        for py_file in py_files:
            if should_skip_path(py_file):
                continue
            content = safe_read_text(py_file) or ""
            if re.search(r"@(?:app|router)\.(get|post|put|delete)", content):
                route_count += 1
                if route_count >= 3:
                    styles.insert(0, "REST")
                    break
        
        if styles:
            return " + ".join(styles)
        return "REST (assumed)"
    
    def _detect_logging(self) -> Optional[str]:
        """Detect logging framework."""
        py_files = list(self.root.rglob("*.py"))[:20]
        logging_libs = set()
        
        for f in py_files:
            if should_skip_path(f):
                continue
            content = safe_read_text(f) or ""
            if "import logging" in content:
                logging_libs.add("stdlib logging")
            if "from loguru import" in content:
                logging_libs.add("loguru")
            if "import structlog" in content:
                logging_libs.add("structlog")
        
        if logging_libs:
            return ", ".join(logging_libs)
        return None
    
    def _find_dangerous_files(self) -> List[dict]:
        """Find files with danger signals."""
        dangerous = []
        
        danger_keywords = {
            "payment": "Payment processing",
            "billing": "Billing logic",
            "auth": "Authentication",
            "password": "Password handling",
            "crypto": "Cryptography",
            "encrypt": "Encryption",
            "private_key": "Private key usage",
            "migration": "Database migration",
        }
        
        for py_file in self.root.rglob("*.py"):
            if should_skip_path(py_file):
                continue
            content = safe_read_text(py_file)
            if not content:
                continue
            content_lower = content.lower()
            matches = []
            for keyword, description in danger_keywords.items():
                if keyword in content_lower:
                    matches.append(description)
            if matches:
                try:
                    rel_path = str(py_file.relative_to(self.root))
                    dangerous.append({"file": rel_path, "reasons": matches})
                except Exception:
                    pass
        
        dangerous.sort(key=lambda x: len(x["reasons"]), reverse=True)
        return dangerous[:10]
    
    def _detect_quality_tools(self) -> dict:
        """Detect linters, formatters, type checkers."""
        tools = {"linters": [], "formatters": [], "type_checkers": []}
        
        config_files = ["pyproject.toml", "setup.cfg", ".flake8", "tox.ini"]
        for config_file in config_files:
            path = self.root / config_file
            if path.exists():
                content = safe_read_text(path) or ""
                if "ruff" in content:
                    if "ruff" not in tools["linters"]:
                        tools["linters"].append("ruff")
                if "flake8" in content:
                    if "flake8" not in tools["linters"]:
                        tools["linters"].append("flake8")
                if "pylint" in content:
                    if "pylint" not in tools["linters"]:
                        tools["linters"].append("pylint")
                if "black" in content:
                    if "black" not in tools["formatters"]:
                        tools["formatters"].append("black")
                if "isort" in content:
                    if "isort" not in tools["formatters"]:
                        tools["formatters"].append("isort")
                if "mypy" in content:
                    if "mypy" not in tools["type_checkers"]:
                        tools["type_checkers"].append("mypy")
                if "pyright" in content:
                    if "pyright" not in tools["type_checkers"]:
                        tools["type_checkers"].append("pyright")
        
        package_json = self.root / "package.json"
        if package_json.exists():
            content = safe_read_text(package_json)
            if content:
                try:
                    pkg = json.loads(content)
                    deps = {}
                    deps.update(pkg.get("dependencies", {}))
                    deps.update(pkg.get("devDependencies", {}))
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
        """Generate enhanced CLAUDE.md content."""
        conventions = self.detect_conventions()
        test_frameworks = conventions.get("testing_framework", {})
        quality_tools = conventions.get("code_quality_tools", {})
        
        lines = []
        lines.append(f"# CLAUDE.md - Project: {project.name}")
        lines.append("")
        lines.append("## Identity")
        lines.append("You are a senior developer on this project with deep knowledge of the codebase.")
        lines.append("")
        lines.append("## Stack")
        
        if project.languages:
            lines.append(f"- **Languages**: {', '.join(project.languages)}")
        else:
            lines.append("- **Languages**: Unknown")
        
        lines.append(f"- **Framework**: {project.framework or 'Unknown'}")
        lines.append(f"- **Package Manager**: {project.package_manager or 'Unknown'}")
        
        if project.python_version:
            lines.append(f"- **Python**: {project.python_version}")
        
        api_style = conventions.get("api_style", "Unknown")
        lines.append(f"- **API Style**: {api_style}")
        
        orm = conventions.get("orm_pattern")
        if orm:
            lines.append(f"- **Database**: {orm}")
        
        logging = conventions.get("logging_pattern")
        if logging:
            lines.append(f"- **Logging**: {logging}")
        
        if project.has_docker:
            lines.append("- **Containerized**: Docker")
        
        if project.has_ci:
            lines.append("- **CI/CD**: Configured")
        
        lines.append("")
        lines.append("## Project Description")
        if project.description:
            lines.append(project.description)
        else:
            lines.append("TODO: Add a one-paragraph description of what this project does.")
        
        lines.append("")
        lines.append("## Critical Conventions")
        lines.append("")
        lines.append("### Error Handling")
        lines.append(conventions.get("error_handling", "TODO: Document error handling strategy"))
        
        if test_frameworks:
            lines.append("")
            lines.append("### Testing")
            for lang, framework in test_frameworks.items():
                lines.append(f"- {lang.capitalize()}: {framework}")
        
        async_pattern = conventions.get("async_pattern")
        if async_pattern:
            lines.append("")
            lines.append("### Async/Await")
            lines.append(async_pattern)
        
        if quality_tools:
            lines.append("")
            lines.append("### Code Quality")
            if quality_tools.get("linters"):
                lines.append(f"- Linters: {', '.join(quality_tools['linters'])}")
            if quality_tools.get("formatters"):
                lines.append(f"- Formatters: {', '.join(quality_tools['formatters'])}")
            if quality_tools.get("type_checkers"):
                lines.append(f"- Type checking: {', '.join(quality_tools['type_checkers'])}")
        
        lines.append("")
        lines.append("### Code Style")
        lines.append("- TODO: Max function length?")
        lines.append("- TODO: Naming conventions?")
        lines.append("- TODO: Import organization?")
        
        dangerous_files = conventions.get("dangerous_files", [])
        if dangerous_files:
            lines.append("")
            lines.append("## Dangerous Areas")
            lines.append("<!-- These files contain sensitive logic. Extra care required. -->")
            lines.append("")
            for item in dangerous_files[:5]:
                reasons = " | ".join(item["reasons"])
                lines.append(f"- **`{item['file']}`** - {reasons}")
                lines.append("  - TODO: Add specific gotchas")
        
        lines.append("")
        lines.append("## Current State")
        lines.append("<!-- TODO: What's in progress? What's deprecated? -->")
        lines.append("- TODO: Any ongoing migrations or refactors?")
        lines.append("- TODO: Any deprecated patterns to avoid?")
        
        lines.append("")
        lines.append("## Common Tasks")
        lines.append("")
        lines.append("### Running the Project")
        lines.append("```bash")
        lines.append("# TODO: How to start development")
        lines.append("# TODO: How to run tests")
        lines.append("# TODO: How to build for production")
        lines.append("```")
        
        lines.append("")
        lines.append("### Adding New Features")
        lines.append("TODO: Step-by-step guide for common additions")
        
        lines.append("")
        lines.append("## Common Gotchas")
        lines.append("<!-- Things that aren't obvious from reading the code -->")
        lines.append("- TODO: Race conditions to watch for?")
        lines.append("- TODO: Order-dependent operations?")
        lines.append("- TODO: Performance bottlenecks?")
        
        lines.append("")
        
        return "\n".join(lines)


class TreeGenerator:
    """Generate file tree."""
    
    def __init__(self, root: Path, config: dict):
        self.root = root
        self.config = config
    
    def generate(self) -> Tuple[str, List[Path]]:
        """Generate file tree."""
        lines = []
        lines.append(f"# File Tree: {self.root.name}")
        lines.append(f"# Generated: {get_timestamp()}")
        lines.append("")
        
        max_depth = self.config.get("max_tree_depth", 6)
        max_files = self.config.get("max_files_in_tree", 500)
        
        self._walk(self.root, "", lines, 0, max_depth, max_files)
        
        return "\n".join(lines), []
    
    def _walk(
        self,
        directory: Path,
        prefix: str,
        lines: list,
        depth: int,
        max_depth: int,
        max_files: int,
    ) -> None:
        """Walk directory tree."""
        if depth > max_depth:
            lines.append(f"{prefix}... (depth limit)")
            return
        
        if len(lines) > max_files:
            lines.append(f"{prefix}... (file limit reached)")
            return
        
        try:
            entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return
        
        entries = [e for e in entries if e.name not in EXCLUDE_DIRS]
        
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "`-- " if is_last else "|-- "
            extension = "    " if is_last else "|   "
            
            if entry.is_dir():
                try:
                    file_count = sum(1 for _ in entry.rglob("*") if _.is_file())
                except Exception:
                    file_count = "?"
                lines.append(f"{prefix}{connector}{entry.name}/ ({file_count} files)")
                self._walk(entry, prefix + extension, lines, depth + 1, max_depth, max_files)
            else:
                try:
                    size = entry.stat().st_size
                    size_str = human_readable_size(size)
                    lines.append(f"{prefix}{connector}{entry.name} ({size_str})")
                except Exception:
                    lines.append(f"{prefix}{connector}{entry.name}")


class SchemaExtractor:
    """Extract type definitions and schemas."""
    
    def __init__(self, root: Path, languages: List[str]):
        self.root = root
        self.languages = languages
    
    def extract(self) -> Dict[str, Tuple[str, List[Path]]]:
        """Extract schemas for all detected languages."""
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
    
    def _extract_python(self) -> Tuple[str, List[Path]]:
        """Extract Python type definitions."""
        lines = []
        lines.append("# Auto-extracted Python type definitions")
        lines.append(f"# Generated: {get_timestamp()}")
        lines.append("")
        
        source_files = []
        
        for py_file in self.root.rglob("*.py"):
            if should_skip_path(py_file):
                continue
            
            content = safe_read_text(py_file)
            if not content:
                continue
            
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            
            classes_in_file = []
            
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                
                base_names = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        base_names.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        base_names.append(base.attr)
                
                interesting = {"BaseModel", "BaseSchema", "TypedDict", "Enum", "IntEnum", "StrEnum"}
                
                is_dataclass = False
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name) and decorator.id == "dataclass":
                        is_dataclass = True
                    elif isinstance(decorator, ast.Attribute) and decorator.attr == "dataclass":
                        is_dataclass = True
                
                if set(base_names) & interesting or is_dataclass:
                    start = node.lineno - 1
                    end = node.end_lineno or start + 1
                    source_lines = content.split("\n")[start:end]
                    classes_in_file.append("\n".join(source_lines))
            
            if classes_in_file:
                source_files.append(py_file)
                rel_path = py_file.relative_to(self.root)
                lines.append(f"\n# -- {rel_path} --")
                lines.extend(classes_in_file)
                lines.append("")
        
        return "\n".join(lines), source_files
    
    def _extract_typescript(self) -> Tuple[str, List[Path]]:
        """Extract TypeScript type definitions."""
        lines = []
        lines.append("// Auto-extracted TypeScript type definitions")
        lines.append(f"// Generated: {get_timestamp()}")
        lines.append("")
        
        source_files = []
        
        pattern = re.compile(
            r"^export\s+(?:interface|type|enum|const\s+enum)\s+.*?(?:\{[\s\S]*?\n\}|=\s*[\s\S]*?;)",
            re.MULTILINE,
        )
        
        for ts_file in self.root.rglob("*.ts"):
            if should_skip_path(ts_file):
                continue
            if ".spec.ts" in ts_file.name or ".test.ts" in ts_file.name:
                continue
            
            content = safe_read_text(ts_file)
            if not content:
                continue
            
            matches = pattern.findall(content)
            if matches:
                source_files.append(ts_file)
                rel_path = ts_file.relative_to(self.root)
                lines.append(f"\n// -- {rel_path} --")
                for match in matches:
                    lines.append(match.strip())
                    lines.append("")
        
        return "\n".join(lines), source_files
    
    def _extract_rust(self) -> Tuple[str, List[Path]]:
        """Extract Rust type definitions."""
        lines = []
        lines.append("// Auto-extracted Rust type definitions")
        lines.append(f"// Generated: {get_timestamp()}")
        lines.append("")
        
        source_files = []
        
        pattern = re.compile(
            r"(?:#\[derive\(.*?\)\]\s*)?pub\s+(?:struct|enum|trait)\s+\w+[\s\S]*?\n\}",
            re.MULTILINE,
        )
        
        for rs_file in self.root.rglob("*.rs"):
            if should_skip_path(rs_file):
                continue
            
            content = safe_read_text(rs_file)
            if not content:
                continue
            
            matches = pattern.findall(content)
            if matches:
                source_files.append(rs_file)
                rel_path = rs_file.relative_to(self.root)
                lines.append(f"\n// -- {rel_path} --")
                for match in matches:
                    lines.append(match.strip())
                    lines.append("")
        
        return "\n".join(lines), source_files
    
    def _extract_go(self) -> Tuple[str, List[Path]]:
        """Extract Go type definitions."""
        lines = []
        lines.append("// Auto-extracted Go type definitions")
        lines.append(f"// Generated: {get_timestamp()}")
        lines.append("")
        
        source_files = []
        
        pattern = re.compile(
            r"type\s+\w+\s+(?:struct|interface)\s*\{[\s\S]*?\n\}",
            re.MULTILINE,
        )
        
        for go_file in self.root.rglob("*.go"):
            if should_skip_path(go_file):
                continue
            if "_test.go" in go_file.name:
                continue
            
            content = safe_read_text(go_file)
            if not content:
                continue
            
            matches = pattern.findall(content)
            if matches:
                source_files.append(go_file)
                rel_path = go_file.relative_to(self.root)
                lines.append(f"\n// -- {rel_path} --")
                for match in matches:
                    lines.append(match.strip())
                    lines.append("")
        
        return "\n".join(lines), source_files
    
    def _extract_csharp(self) -> Tuple[str, List[Path]]:
        """Extract C# type definitions."""
        lines = []
        lines.append("// Auto-extracted C# type definitions")
        lines.append(f"// Generated: {get_timestamp()}")
        lines.append("")
        
        source_files = []
        
        pattern = re.compile(
            r"public\s+(?:sealed\s+|abstract\s+|partial\s+|static\s+)*"
            r"(?:class|record|enum|interface|struct)\s+\w+[\s\S]*?\n\}",
            re.MULTILINE,
        )
        
        for cs_file in self.root.rglob("*.cs"):
            if should_skip_path(cs_file):
                continue
            
            content = safe_read_text(cs_file)
            if not content:
                continue
            
            matches = pattern.findall(content)
            if matches:
                source_files.append(cs_file)
                rel_path = cs_file.relative_to(self.root)
                lines.append(f"\n// -- {rel_path} --")
                for match in matches:
                    lines.append(match.strip())
                    lines.append("")
        
        return "\n".join(lines), source_files


class APIExtractor:
    """Extract API routes and public function signatures."""
    
    def __init__(self, root: Path, languages: List[str], framework: str):
        self.root = root
        self.languages = languages
        self.framework = framework
    
    def extract_routes(self) -> Tuple[str, List[Path]]:
        """Extract API routes."""
        lines = []
        lines.append("# API Routes")
        lines.append(f"# Generated: {get_timestamp()}")
        lines.append("")
        
        source_files = []
        
        if "python" in self.languages:
            py_lines, py_files = self._extract_python_routes()
            lines.extend(py_lines)
            source_files.extend(py_files)
        
        if "typescript" in self.languages or "javascript" in self.languages:
            js_lines, js_files = self._extract_js_routes()
            lines.extend(js_lines)
            source_files.extend(js_files)
        
        if len(lines) <= 3:
            return "", []
        
        return "\n".join(lines), source_files
    
    def extract_public_api(self) -> Tuple[str, List[Path]]:
        """Extract public function signatures."""
        lines = []
        lines.append("# Public API (function signatures)")
        lines.append(f"# Generated: {get_timestamp()}")
        lines.append("")
        
        source_files = []
        
        if "python" in self.languages:
            py_lines, py_files = self._extract_python_signatures()
            lines.extend(py_lines)
            source_files.extend(py_files)
        
        if "typescript" in self.languages:
            ts_lines, ts_files = self._extract_ts_signatures()
            lines.extend(ts_lines)
            source_files.extend(ts_files)
        
        return "\n".join(lines), source_files
    
    def _extract_python_routes(self) -> Tuple[List[str], List[Path]]:
        """Extract Python routes."""
        lines = []
        source_files = []
        
        route_pattern = re.compile(
            r"@(?:app|router|api)\.(get|post|put|patch|delete|head|options|websocket)"
            r'\s*\(\s*["\']([^"\']*)["\']'
        )
        
        for py_file in self.root.rglob("*.py"):
            if should_skip_path(py_file):
                continue
            
            content = safe_read_text(py_file)
            if not content:
                continue
            
            matches = route_pattern.findall(content)
            if matches:
                source_files.append(py_file)
                rel = py_file.relative_to(self.root)
                lines.append(f"\n## {rel}")
                for method, path in matches:
                    lines.append(f"  {method.upper():8s} {path}")
        
        return lines, source_files
    
    def _extract_js_routes(self) -> Tuple[List[str], List[Path]]:
        """Extract JavaScript/TypeScript routes."""
        lines = []
        source_files = []
        
        route_pattern = re.compile(
            r"(?:app|router|server)\.(get|post|put|patch|delete)"
            r'\s*\(\s*["\'/]([^"\']*)["\']'
        )
        
        for ext in ["*.js", "*.ts"]:
            for js_file in self.root.rglob(ext):
                if should_skip_path(js_file):
                    continue
                
                content = safe_read_text(js_file)
                if not content:
                    continue
                
                matches = route_pattern.findall(content)
                if matches:
                    source_files.append(js_file)
                    rel = js_file.relative_to(self.root)
                    lines.append(f"\n## {rel}")
                    for method, path in matches:
                        lines.append(f"  {method.upper():8s} {path}")
        
        return lines, source_files
    
    def _extract_python_signatures(self) -> Tuple[List[str], List[Path]]:
        """Extract Python function signatures."""
        lines = []
        source_files = []
        
        for py_file in self.root.rglob("*.py"):
            if should_skip_path(py_file):
                continue
            
            content = safe_read_text(py_file)
            if not content:
                continue
            
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            
            sigs = []
            
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("_"):
                        sig = self._format_python_sig(node, "")
                        sigs.append(sig)
                elif isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if not item.name.startswith("_") or item.name == "__init__":
                                sig = self._format_python_sig(item, node.name)
                                sigs.append(sig)
            
            if sigs:
                source_files.append(py_file)
                rel = py_file.relative_to(self.root)
                lines.append(f"\n## {rel}")
                lines.extend(sigs)
        
        return lines, source_files
    
    def _format_python_sig(self, node, class_name: str) -> str:
        """Format a Python function signature."""
        if isinstance(node, ast.AsyncFunctionDef):
            prefix = "async "
        else:
            prefix = ""
        
        if class_name:
            name = f"{class_name}.{node.name}"
        else:
            name = node.name
        
        args = []
        for arg in node.args.args:
            if arg.arg == "self":
                continue
            if arg.annotation:
                try:
                    annotation = f": {ast.unparse(arg.annotation)}"
                except Exception:
                    annotation = ""
            else:
                annotation = ""
            args.append(f"{arg.arg}{annotation}")
        
        returns = ""
        if node.returns:
            try:
                returns = f" -> {ast.unparse(node.returns)}"
            except Exception:
                pass
        
        args_str = ", ".join(args)
        return f"  {prefix}def {name}({args_str}){returns}"
    
    def _extract_ts_signatures(self) -> Tuple[List[str], List[Path]]:
        """Extract TypeScript function signatures."""
        lines = []
        source_files = []
        
        pattern = re.compile(
            r"^export\s+(?:async\s+)?function\s+(\w+)\s*"
            r"\(([^)]*)\)\s*(?::\s*([^\{]*))?",
            re.MULTILINE,
        )
        
        for ts_file in self.root.rglob("*.ts"):
            if should_skip_path(ts_file):
                continue
            
            content = safe_read_text(ts_file)
            if not content:
                continue
            
            matches = pattern.findall(content)
            if matches:
                source_files.append(ts_file)
                rel = ts_file.relative_to(self.root)
                lines.append(f"\n## {rel}")
                for name, params, return_type in matches:
                    ret = ""
                    if return_type and return_type.strip():
                        ret = f": {return_type.strip()}"
                    lines.append(f"  function {name}({params}){ret}")
        
        return lines, source_files


class DependencyAnalyzer:
    """Analyze internal import dependencies."""
    
    def __init__(self, root: Path, languages: List[str]):
        self.root = root
        self.languages = languages
    
    def analyze(self) -> Tuple[str, List[Path]]:
        """Analyze dependencies."""
        lines = []
        lines.append("# Internal Dependency Graph")
        lines.append(f"# Generated: {get_timestamp()}")
        lines.append("")
        
        source_files = []
        
        if "python" in self.languages:
            py_lines, py_files = self._analyze_python()
            lines.extend(py_lines)
            source_files.extend(py_files)
        
        if "typescript" in self.languages or "javascript" in self.languages:
            js_lines, js_files = self._analyze_js()
            lines.extend(js_lines)
            source_files.extend(js_files)
        
        return "\n".join(lines), source_files
    
    def _analyze_python(self) -> Tuple[List[str], List[Path]]:
        """Analyze Python imports."""
        lines = ["## Python Imports", ""]
        source_files = []
        
        import_pattern = re.compile(
            r"^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
            re.MULTILINE,
        )
        
        src_dirs = []
        for d in ["src", "app", "lib", self.root.name]:
            if (self.root / d).is_dir():
                src_dirs.append(d)
        package_root = src_dirs[0] if src_dirs else ""
        
        graph = {}
        
        for py_file in self.root.rglob("*.py"):
            if should_skip_path(py_file):
                continue
            
            content = safe_read_text(py_file)
            if not content:
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
                lines.append(f"  -> {imp}")
            lines.append("")
        
        return lines, source_files
    
    def _analyze_js(self) -> Tuple[List[str], List[Path]]:
        """Analyze JavaScript/TypeScript imports."""
        lines = ["## JavaScript/TypeScript Imports", ""]
        source_files = []
        
        import_pattern = re.compile(
            r"""(?:import|require)\s*\(?['"](\.[^'"]+)['"]""",
            re.MULTILINE,
        )
        
        graph = {}
        
        for ext in ["*.js", "*.ts", "*.tsx", "*.jsx"]:
            for f in self.root.rglob(ext):
                if should_skip_path(f):
                    continue
                
                content = safe_read_text(f)
                if not content:
                    continue
                
                source_files.append(f)
                rel = str(f.relative_to(self.root))
                
                imports = import_pattern.findall(content)
                if imports:
                    graph[rel] = imports
        
        for file, imports in sorted(graph.items()):
            lines.append(f"{file}")
            for imp in imports:
                lines.append(f"  -> {imp}")
            lines.append("")
        
        return lines, source_files


class DependencyGraphVisualizer:
    """Generate Mermaid dependency graph."""
    
    def generate_mermaid(self, dependency_text: str) -> str:
        """Convert dependency text to Mermaid diagram."""
        lines = []
        lines.append("# Dependency Graph Visualization")
        lines.append("")
        lines.append("```mermaid")
        lines.append("graph LR")
        
        current_file = None
        edges = []
        
        for line in dependency_text.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("##"):
                continue
            if line.startswith("->"):
                dep = line[2:].strip()
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


class SymbolIndexGenerator:
    """Generate symbol index for navigation."""
    
    def __init__(self, root: Path, languages: List[str]):
        self.root = root
        self.languages = languages
    
    def generate(self) -> Tuple[str, List[Path]]:
        """Generate symbol index."""
        symbols = {
            "classes": {},
            "functions": {},
            "routes": {},
        }
        source_files = []
        
        if "python" in self.languages:
            py_symbols, py_files = self._index_python()
            symbols["classes"].update(py_symbols.get("classes", {}))
            symbols["functions"].update(py_symbols.get("functions", {}))
            source_files.extend(py_files)
        
        if "typescript" in self.languages or "javascript" in self.languages:
            ts_symbols, ts_files = self._index_typescript()
            symbols["classes"].update(ts_symbols.get("classes", {}))
            symbols["functions"].update(ts_symbols.get("functions", {}))
            source_files.extend(ts_files)
        
        return json.dumps(symbols, indent=2), source_files
    
    def _index_python(self) -> Tuple[dict, List[Path]]:
        """Index Python symbols."""
        symbols = {"classes": {}, "functions": {}}
        files = []
        
        for py_file in self.root.rglob("*.py"):
            if should_skip_path(py_file):
                continue
            
            content = safe_read_text(py_file)
            if not content:
                continue
            
            try:
                tree = ast.parse(content)
                files.append(py_file)
                rel_path = str(py_file.relative_to(self.root))
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        symbols["classes"][node.name] = rel_path
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not node.name.startswith("_"):
                            symbols["functions"][node.name] = rel_path
            except Exception:
                continue
        
        return symbols, files
    
    def _index_typescript(self) -> Tuple[dict, List[Path]]:
        """Index TypeScript symbols."""
        symbols = {"classes": {}, "functions": {}}
        files = []
        
        class_pattern = re.compile(r"(?:export\s+)?class\s+(\w+)")
        function_pattern = re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)")
        
        for ts_file in self.root.rglob("*.ts"):
            if should_skip_path(ts_file):
                continue
            
            content = safe_read_text(ts_file)
            if not content:
                continue
            
            files.append(ts_file)
            rel_path = str(ts_file.relative_to(self.root))
            
            for match in class_pattern.finditer(content):
                symbols["classes"][match.group(1)] = rel_path
            
            for match in function_pattern.finditer(content):
                symbols["functions"][match.group(1)] = rel_path
        
        return symbols, files


class EntryPointDetector:
    """Detect application entry points."""
    
    def __init__(self, root: Path, languages: List[str]):
        self.root = root
        self.languages = languages
    
    def detect(self) -> Tuple[str, List[Path]]:
        """Detect entry points."""
        entry_points = {
            "main_files": [],
            "server_files": [],
            "cli_files": [],
            "test_suites": [],
        }
        source_files = []
        
        main_patterns = [
            "main.py", "app.py", "__main__.py", "manage.py",
            "main.ts", "index.ts", "server.ts", "app.ts",
            "main.js", "index.js", "server.js", "app.js",
            "main.go", "main.rs",
        ]
        
        server_patterns = ["server.py", "wsgi.py", "asgi.py"]
        cli_patterns = ["cli.py", "cli.ts", "cmd.py"]
        
        for pattern in main_patterns:
            for f in self.root.rglob(pattern):
                if not should_skip_path(f):
                    rel_path = str(f.relative_to(self.root))
                    if rel_path not in entry_points["main_files"]:
                        entry_points["main_files"].append(rel_path)
                        source_files.append(f)
        
        for pattern in server_patterns:
            for f in self.root.rglob(pattern):
                if not should_skip_path(f):
                    rel_path = str(f.relative_to(self.root))
                    if rel_path not in entry_points["server_files"]:
                        entry_points["server_files"].append(rel_path)
        
        for pattern in cli_patterns:
            for f in self.root.rglob(pattern):
                if not should_skip_path(f):
                    rel_path = str(f.relative_to(self.root))
                    if rel_path not in entry_points["cli_files"]:
                        entry_points["cli_files"].append(rel_path)
        
        test_dirs = ["tests", "test", "__tests__", "spec"]
        for test_dir in test_dirs:
            test_path = self.root / test_dir
            if test_path.exists() and test_path.is_dir():
                entry_points["test_suites"].append(test_dir)
        
        return json.dumps(entry_points, indent=2), source_files


class DatabaseSchemaExtractor:
    """Extract database schema from various sources."""
    
    def __init__(self, root: Path):
        self.root = root
    
    def extract(self) -> Optional[Tuple[str, List[Path]]]:
        """Extract database schema."""
        result = self._from_sqlalchemy()
        if result:
            return result
        
        result = self._from_django()
        if result:
            return result
        
        prisma_schema = self.root / "prisma" / "schema.prisma"
        if prisma_schema.exists():
            content = safe_read_text(prisma_schema)
            if content:
                output = f"# Database Schema (Prisma)\n\n```prisma\n{content}\n```"
                return output, [prisma_schema]
        
        return None
    
    def _from_sqlalchemy(self) -> Optional[Tuple[str, List[Path]]]:
        """Extract from SQLAlchemy models."""
        model_files = []
        
        for py_file in self.root.rglob("*.py"):
            if "model" not in py_file.name.lower():
                continue
            content = safe_read_text(py_file)
            if not content:
                continue
            if "from sqlalchemy" in content or "declarative_base" in content:
                model_files.append(py_file)
        
        if not model_files:
            return None
        
        lines = ["# Database Schema (from SQLAlchemy models)", ""]
        
        for model_file in model_files:
            content = safe_read_text(model_file)
            if not content:
                continue
            
            try:
                tree = ast.parse(content)
            except Exception:
                continue
            
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                
                has_tablename = False
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                if target.id == "__tablename__":
                                    has_tablename = True
                
                has_base = False
                for base in node.bases:
                    if isinstance(base, ast.Name) and "Base" in base.id:
                        has_base = True
                
                if has_tablename or has_base:
                    rel_path = model_file.relative_to(self.root)
                    lines.append(f"\n## {rel_path} - Table: {node.name}")
                    
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            try:
                                source = ast.unparse(item)
                                if "Column(" in source or "relationship(" in source:
                                    lines.append(f"  {source}")
                            except Exception:
                                pass
                    lines.append("")
        
        if len(lines) <= 2:
            return None
        
        return "\n".join(lines), model_files
    
    def _from_django(self) -> Optional[Tuple[str, List[Path]]]:
        """Extract from Django models."""
        lines = ["# Database Schema (from Django models)", ""]
        model_files = []
        found = False
        
        for py_file in self.root.rglob("models.py"):
            if should_skip_path(py_file):
                continue
            
            content = safe_read_text(py_file)
            if not content:
                continue
            
            if "from django.db import models" not in content:
                continue
            
            try:
                tree = ast.parse(content)
            except Exception:
                continue
            
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                
                is_model = False
                for base in node.bases:
                    if isinstance(base, ast.Attribute) and base.attr == "Model":
                        is_model = True
                
                if is_model:
                    found = True
                    model_files.append(py_file)
                    rel_path = py_file.relative_to(self.root)
                    lines.append(f"\n## {rel_path} - Model: {node.name}")
                    
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            try:
                                source = ast.unparse(item)
                                if "models." in source:
                                    lines.append(f"  {source}")
                            except Exception:
                                pass
                    lines.append("")
        
        if not found:
            return None
        
        return "\n".join(lines), model_files


class APIContractExtractor:
    """Extract API contracts from spec files."""
    
    def __init__(self, root: Path):
        self.root = root
    
    def extract(self) -> Optional[Tuple[str, List[Path]]]:
        """Extract API contract."""
        openapi_files = [
            "openapi.yaml", "openapi.yml", "openapi.json",
            "swagger.yaml", "swagger.yml", "swagger.json",
            "api-spec.yaml", "api-spec.yml",
        ]
        
        for spec_file in openapi_files:
            path = self.root / spec_file
            if path.exists():
                content = safe_read_text(path)
                if content:
                    output = f"# API Contract\n\n```yaml\n{content}\n```"
                    return output, [path]
        
        graphql_files = ["schema.graphql", "schema.gql"]
        for gql_file in graphql_files:
            path = self.root / gql_file
            if path.exists():
                content = safe_read_text(path)
                if content:
                    output = f"# GraphQL Schema\n\n```graphql\n{content}\n```"
                    return output, [path]
        
        api_docs = ["API.md", "api/README.md", "docs/api.md"]
        for doc_file in api_docs:
            path = self.root / doc_file
            if path.exists():
                content = safe_read_text(path)
                if content:
                    output = f"# API Documentation\n\n{content}"
                    return output, [path]
        
        return None


class ScaffoldGenerator:
    """Generate CLAUDE.md and ARCHITECTURE.md scaffolds."""
    
    def __init__(self, project: ProjectInfo):
        self.project = project
    
    def generate_claude_md(self) -> str:
        """Generate enhanced CLAUDE.md."""
        enhancer = ClaudeMdEnhancer(self.project.root)
        return enhancer.generate_enhanced_claude_md(self.project)
    
    def generate_architecture_md(self) -> str:
        """Generate ARCHITECTURE.md scaffold."""
        p = self.project
        
        lines = []
        lines.append(f"# Architecture Overview - {p.name}")
        lines.append("")
        lines.append("## System Context")
        lines.append("<!-- TODO: What does this system do? What are its boundaries? -->")
        lines.append("```")
        lines.append("[External Client] -> [This System] -> [External Dependencies]")
        lines.append("```")
        lines.append("")
        lines.append("## Request Flow")
        lines.append("<!-- TODO: Trace a typical request through the system -->")
        lines.append("```")
        lines.append("Request -> ??? -> Response")
        lines.append("```")
        lines.append("")
        lines.append("## Directory -> Responsibility Mapping")
        lines.append("<!-- TODO: Fill in based on your project structure -->")
        lines.append("| Directory | Purpose | Key Patterns |")
        lines.append("|-----------|---------|--------------|")
        lines.append("| TODO      | TODO    | TODO         |")
        lines.append("")
        lines.append("## Data Model")
        lines.append("<!-- TODO: Key entities and their relationships -->")
        lines.append("```")
        lines.append("Entity A --1:N--> Entity B --N:M--> Entity C")
        lines.append("```")
        lines.append("")
        lines.append("## Key Design Decisions")
        lines.append(f"- **Why {p.framework}?**: TODO")
        lines.append("- **Why this architecture?**: TODO")
        lines.append("")
        lines.append("## Infrastructure")
        
        if p.has_docker:
            lines.append("- Docker: Yes")
        else:
            lines.append("- Docker: No")
        
        if p.has_ci:
            lines.append("- CI/CD: Configured")
        else:
            lines.append("- CI/CD: Not configured")
        
        if p.has_tests:
            lines.append("- Tests: Present")
        else:
            lines.append("- Tests: Not found")
        
        lines.append("")
        lines.append("## External Dependencies")
        lines.append("<!-- TODO: APIs, databases, services this connects to -->")
        lines.append("- TODO: List external systems")
        lines.append("")
        
        return "\n".join(lines)


class ModuleSummaryGenerator:
    """Generate module summaries using LLM."""
    
    def __init__(self, root: Path, config: dict):
        self.root = root
        self.config = config
        self.client = None
    
    def _get_client(self):
        """Get LLM client."""
        if self.client:
            return self.client
        
        provider = self.config["llm_summaries"]["provider"]
        
        if provider == "anthropic":
            try:
                from anthropic import Anthropic
                self.client = Anthropic()
                return self.client
            except ImportError:
                print("  Warning: pip install anthropic for LLM summaries")
                return None
        elif provider == "openai":
            try:
                from openai import OpenAI
                self.client = OpenAI()
                return self.client
            except ImportError:
                print("  Warning: pip install openai for LLM summaries")
                return None
        
        return None
    
    def generate(self, languages: List[str]) -> Dict[str, Tuple[str, List[Path]]]:
        """Generate summaries for modules."""
        client = self._get_client()
        if not client:
            return {}
        
        results = {}
        
        extensions = {
            "python": "*.py",
            "typescript": "*.ts",
            "javascript": "*.js",
            "rust": "*.rs",
            "go": "*.go",
            "csharp": "*.cs",
        }
        
        files_to_summarize = []
        
        for lang in languages:
            if lang not in extensions:
                continue
            for f in self.root.rglob(extensions[lang]):
                if should_skip_path(f):
                    continue
                try:
                    size = f.stat().st_size
                    min_size = self.config["llm_summaries"].get("min_file_size_bytes", 300)
                    if size > min_size and size < 100000:
                        files_to_summarize.append(f)
                except Exception:
                    continue
        
        max_modules = self.config["llm_summaries"].get("max_modules", 30)
        files_to_summarize.sort(key=lambda f: f.stat().st_size, reverse=True)
        files_to_summarize = files_to_summarize[:max_modules]
        
        if not files_to_summarize:
            return {}
        
        progress = ProgressIndicator(len(files_to_summarize), "Summarizing modules")
        
        for filepath in files_to_summarize:
            try:
                rel = filepath.relative_to(self.root)
                source = safe_read_text(filepath)
                if not source:
                    progress.update()
                    continue
                
                if len(source) > 20000:
                    source = source[:20000] + "\n... [truncated]"
                
                summary = self._call_llm(client, str(rel), source)
                if summary:
                    key = str(rel).replace("/", "__").replace("\\", "__")
                    key = re.sub(r"\.\w+$", ".md", key)
                    content = f"# Module: {rel}\n\n{summary}\n"
                    results[key] = (content, [filepath])
            except Exception as e:
                print(f"\n  Warning: Error summarizing {filepath}: {e}")
            
            progress.update()
        
        progress.finish()
        
        return results
    
def _call_llm(self, client, filepath: str, source: str) -> Optional[str]:
    """Call LLM for module summary."""

    provider = self.config["llm_summaries"]["provider"]
    model = self.config["llm_summaries"]["model"]

    MAX_SOURCE_CHARS = 12000
    if len(source) > MAX_SOURCE_CHARS:
        source = source[:MAX_SOURCE_CHARS] + "\n\n# [TRUNCATED]"

    prompt = f"""
Analyze this source module and produce a concise summary.

File: {filepath}

Source Code:
{source}

Provide:

1. Purpose — one sentence describing the module.
2. Public Interface — key classes/functions with short descriptions.
3. Dependencies — internal and external dependencies.
4. Key Patterns — design patterns, invariants, or gotchas.
5. State/Data Flow — how data moves through the module.

Be precise and concise.
"""

    if provider == "anthropic":
        response = client.messages.create(
            model=model,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    elif provider == "openai":
        response = client.chat.completions.create(
            model=model,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    return None


class DiagnosticTool:
    """Run diagnostics on the project."""
    
    def __init__(self, root: Path):
        self.root = root
    
    def run(self) -> None:
        """Run all diagnostics."""
        print("")
        print("=" * 60)
        print("  LLM Context Generator - Diagnostics")
        print("=" * 60)
        print("")
        
        self._check_environment()
        self._check_project()
        self._check_context()
        self._check_security()
        self._recommendations()
    
    def _check_environment(self) -> None:
        """Check system environment."""
        print("-> Environment Check")
        print(f"  Python: {sys.version.split()[0]}")
        print(f"  Platform: {sys.platform}")
        
        optional_deps = [
            ("yaml", "pyyaml", "YAML config"),
            ("anthropic", "anthropic", "Anthropic AI"),
            ("openai", "openai", "OpenAI"),
            ("watchdog", "watchdog", "Watch mode"),
        ]
        
        for module, package, feature in optional_deps:
            try:
                __import__(module)
                print(f"  {feature}: installed")
            except ImportError:
                print(f"  {feature}: not installed (pip install {package})")
        
        print("")
    
    def _check_project(self) -> None:
        """Check project structure."""
        print("-> Project Check")
        
        detector = ProjectDetector(self.root)
        project = detector.detect()
        
        print(f"  Name: {project.name}")
        print(f"  Languages: {', '.join(project.languages) or 'None detected'}")
        print(f"  Framework: {project.framework}")
        print(f"  Package Manager: {project.package_manager or 'Unknown'}")
        print(f"  Has Docker: {'Yes' if project.has_docker else 'No'}")
        print(f"  Has CI/CD: {'Yes' if project.has_ci else 'No'}")
        print(f"  Has Tests: {'Yes' if project.has_tests else 'No'}")
        print("")
    
    def _check_context(self) -> None:
        """Check generated context."""
        print("-> Generated Context Check")
        
        context_dir = self.root / ".llm-context"
        if not context_dir.exists():
            print("  Status: No context generated yet")
            print("  Run: python llm-context-setup.py")
            print("")
            return
        
        manifest = GenerationManifest.load(self.root)
        if manifest:
            print(f"  Last generated: {manifest.generated_at}")
            print(f"  Files tracked: {len(manifest.files)}")
            
            total_size = 0
            for f in context_dir.rglob("*"):
                if f.is_file():
                    total_size += f.stat().st_size
            print(f"  Total size: {human_readable_size(total_size)}")
        else:
            print("  Status: Manifest missing or outdated")
        
        print("")
    
    def _check_security(self) -> None:
        """Check security configuration."""
        print("-> Security Check")
        
        config = load_config(self.root)
        security = SecurityManager(self.root, config)
        
        print(f"  Mode: {security.mode}")
        print(f"  Secret Redaction: {'Enabled' if security.redact_secrets else 'Disabled'}")
        print(f"  Audit Logging: {'Enabled' if security.audit_enabled else 'Disabled'}")
        print("")
    
    def _recommendations(self) -> None:
        """Print recommendations."""
        print("-> Recommendations")
        
        recommendations = []
        
        if not (self.root / "CLAUDE.md").exists():
            recommendations.append("Create CLAUDE.md to capture project conventions")
        
        if not (self.root / "ARCHITECTURE.md").exists():
            recommendations.append("Create ARCHITECTURE.md to document system design")
        
        config_exists = (
            (self.root / "llm-context.yml").exists()
            or (self.root / "llm-context.json").exists()
        )
        if not config_exists:
            recommendations.append("Create llm-context.yml for custom settings")
        
        if not (self.root / ".git").exists():
            recommendations.append("Initialize git for version control")
        
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                print(f"  {i}. {rec}")
        else:
            print("  All checks passed!")
        
        print("")

# Add to current llm-context-setup.py
class ExternalDependencyDetector:
    """Detect external service calls and API dependencies."""
    
    def __init__(self, root: Path, languages: List[str]):
        self.root = root
        self.languages = languages
    
    def detect(self) -> dict:
        """Detect external dependencies from code patterns."""
        dependencies = {
            "service": self.root.name,
            "exposes": {
                "api": [],
                "events": [],
                "types": [],
            },
            "depends_on": {
                "services": [],
                "apis_consumed": [],
                "shared_types_from": [],
            },
            "tags": [],
        }
        
        if "python" in self.languages:
            self._detect_python_dependencies(dependencies)
        if "typescript" in self.languages or "javascript" in self.languages:
            self._detect_js_dependencies(dependencies)
        
        return dependencies
    
    def _detect_python_dependencies(self, deps: dict) -> None:
        """Detect Python external calls."""
        patterns = {
            "http_calls": [
                r"requests\.(get|post|put|delete|patch)\(['\"]([^'\"]+)",
                r"httpx\.(get|post|put|delete|patch)\(['\"]([^'\"]+)",
                r"fetch\(['\"]([^'\"]+)",
            ],
            "grpc_calls": [
                r"grpc\.(\w+)",
            ],
            "events": [
                r"@EventPattern\(['\"]([^'\"]+)",
                r"\.emit\(['\"]([^'\"]+)",
                r"kafka\.send\(['\"]([^'\"]+)",
            ],
        }
        
        for py_file in self.root.rglob("*.py"):
            if should_skip_path(py_file):
                continue
            content = safe_read_text(py_file)
            if not content:
                continue
            
            # Detect external HTTP calls
            for pattern in patterns["http_calls"]:
                for match in re.finditer(pattern, content):
                    url = match.group(2) if len(match.groups()) > 1 else match.group(1)
                    if url.startswith("http"):  # External call
                        deps["depends_on"]["apis_consumed"].append(url)
            
            # Detect event emissions
            for pattern in patterns["events"]:
                for match in re.finditer(pattern, content):
                    event = match.group(1)
                    deps["exposes"]["events"].append(event)

# ──────────────────────────────────────────────
# External Dependency Detection (Phase 1)
# ──────────────────────────────────────────────

class ExternalDependencyDetector:
    """Detect external service dependencies from code patterns."""
    
    def __init__(self, root: Path, languages: List[str], framework: str):
        self.root = root
        self.languages = languages
        self.framework = framework
    
    def detect(self) -> dict:
        """
        Detect external dependencies and API contracts.
        
        Returns a dictionary suitable for external-dependencies.json
        """
        dependencies = {
            "service": self.root.name,
            "repository": self._get_repo_url(),
            "exposes": {
                "api": [],
                "events": [],
                "types": [],
            },
            "depends_on": {
                "services": set(),
                "apis_consumed": [],
                "databases": [],
                "message_queues": [],
                "external_apis": [],
            },
            "tags": self._auto_detect_tags(),
            "detected_at": get_timestamp(),
        }
        
        if "python" in self.languages:
            self._detect_python_dependencies(dependencies)
        
        if "typescript" in self.languages or "javascript" in self.languages:
            self._detect_js_dependencies(dependencies)
        
        if "rust" in self.languages:
            self._detect_rust_dependencies(dependencies)
        
        if "go" in self.languages:
            self._detect_go_dependencies(dependencies)
        
        # Convert sets to lists for JSON serialization
        dependencies["depends_on"]["services"] = sorted(list(dependencies["depends_on"]["services"]))
        
        # Deduplicate lists
        for key in ["api", "events", "types"]:
            dependencies["exposes"][key] = sorted(list(set(dependencies["exposes"][key])))
        
        for key in dependencies["depends_on"]:
            if isinstance(dependencies["depends_on"][key], list):
                dependencies["depends_on"][key] = sorted(list(set(dependencies["depends_on"][key])))
        
        return dependencies
    
    def _get_repo_url(self) -> Optional[str]:
        """Try to get repository URL from git config."""
        try:
            result = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                cwd=self.root,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
    
    def _auto_detect_tags(self) -> List[str]:
        """Auto-detect tags based on project structure and framework."""
        tags = []
        
        # Framework-based tags
        framework_lower = self.framework.lower()
        if "fastapi" in framework_lower or "flask" in framework_lower or "django" in framework_lower:
            tags.append("backend-api")
        if "express" in framework_lower or "nestjs" in framework_lower:
            tags.append("backend-api")
        if "react" in framework_lower or "vue" in framework_lower or "angular" in framework_lower:
            tags.append("frontend")
        if "nextjs" in framework_lower:
            tags.extend(["frontend", "ssr"])
        
        # Directory-based tags
        if (self.root / "api").exists() or (self.root / "routes").exists():
            tags.append("api")
        if (self.root / "models").exists() or (self.root / "schemas").exists():
            tags.append("data")
        if (self.root / "services").exists():
            tags.append("services")
        if (self.root / "components").exists() or (self.root / "src" / "components").exists():
            tags.append("ui")
        if (self.root / "workers").exists() or (self.root / "tasks").exists():
            tags.append("background-jobs")
        if (self.root / "migrations").exists():
            tags.append("database")
        
        # Language-based tags
        for lang in self.languages:
            tags.append(lang)
        
        return sorted(list(set(tags)))
    
    def _detect_python_dependencies(self, deps: dict) -> None:
        """Detect Python external dependencies and API calls."""
        
        http_patterns = [
            (r'requests\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)', "requests"),
            (r'httpx\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)', "httpx"),
            (r'aiohttp\.ClientSession\(\)\.(?:get|post|put|delete)\s*\(\s*["\']([^"\']+)', "aiohttp"),
        ]
        
        grpc_patterns = [
            r'import\s+grpc',
            r'from\s+grpc\s+import',
        ]
        
        database_patterns = [
            (r'psycopg2', "PostgreSQL"),
            (r'pymongo', "MongoDB"),
            (r'redis', "Redis"),
            (r'sqlalchemy.*postgresql', "PostgreSQL"),
            (r'sqlalchemy.*mysql', "MySQL"),
            (r'motor', "MongoDB"),
        ]
        
        message_queue_patterns = [
            (r'kafka', "Kafka"),
            (r'celery', "Celery/Redis"),
            (r'pika', "RabbitMQ"),
            (r'boto3.*sqs', "AWS SQS"),
        ]
        
        event_patterns = [
            (r'@event\.emit\s*\(\s*["\']([^"\']+)', "event_emit"),
            (r'@EventPattern\s*\(\s*["\']([^"\']+)', "nestjs_event"),
            (r'\.publish\s*\(\s*["\']([^"\']+)', "publish"),
            (r'\.send_event\s*\(\s*["\']([^"\']+)', "send_event"),
        ]
        
        for py_file in self.root.rglob("*.py"):
            if should_skip_path(py_file):
                continue
            
            content = safe_read_text(py_file)
            if not content:
                continue
            
            # Detect HTTP calls
            for pattern, lib in http_patterns:
                for match in re.finditer(pattern, content):
                    if len(match.groups()) >= 2:
                        method = match.group(1).upper()
                        url = match.group(2)
                    else:
                        url = match.group(1)
                        method = "GET"
                    
                    # Check if external call (starts with http or contains domain)
                    if url.startswith("http") or "." in url:
                        deps["depends_on"]["apis_consumed"].append(f"{method} {url}")
                        
                        # Try to extract service name from URL
                        service_match = re.search(r'https?://([^/:\s]+)', url)
                        if service_match:
                            service = service_match.group(1)
                            if service not in ["localhost", "127.0.0.1"]:
                                deps["depends_on"]["services"].add(service)
                    # Internal API reference
                    elif url.startswith("/api/"):
                        deps["exposes"]["api"].append(f"{method} {url}")
            
            # Detect gRPC usage
            for pattern in grpc_patterns:
                if re.search(pattern, content):
                    deps["depends_on"]["services"].add("grpc-service")
                    break
            
            # Detect database connections
            for pattern, db_name in database_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    if db_name not in deps["depends_on"]["databases"]:
                        deps["depends_on"]["databases"].append(db_name)
            
            # Detect message queues
            for pattern, mq_name in message_queue_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    if mq_name not in deps["depends_on"]["message_queues"]:
                        deps["depends_on"]["message_queues"].append(mq_name)
            
            # Detect event emissions
            for pattern, event_type in event_patterns:
                for match in re.finditer(pattern, content):
                    event_name = match.group(1)
                    deps["exposes"]["events"].append(event_name)
            
            # Detect external API keys (service dependencies)
            external_api_patterns = [
                (r'STRIPE_', "Stripe"),
                (r'TWILIO_', "Twilio"),
                (r'SENDGRID_', "SendGrid"),
                (r'AWS_', "AWS"),
                (r'GOOGLE_CLOUD_', "Google Cloud"),
                (r'AZURE_', "Azure"),
            ]
            
            for pattern, service in external_api_patterns:
                if re.search(pattern, content):
                    if service not in deps["depends_on"]["external_apis"]:
                        deps["depends_on"]["external_apis"].append(service)
    
ExternalDependencyDetector with this enhanced version:

Python

    def _detect_js_dependencies(self, deps: dict) -> None:
        """
        Detect JavaScript/TypeScript external dependencies.
        
        Enhanced with comprehensive patterns for:
        - fetch, axios, got, node-fetch, ky
        - Next.js API routes and server actions
        - NestJS controllers, services, event handlers
        - tRPC routers and procedures
        - GraphQL clients (Apollo, urql)
        - Database ORMs (Prisma, TypeORM, Drizzle, Mongoose)
        - Message queues (Kafka, RabbitMQ, Bull, BullMQ)
        - WebSocket connections
        - Third-party SDK patterns
        """
        
        # ─────────────────────────────────────────
        # HTTP Client Patterns
        # ─────────────────────────────────────────
        
        http_patterns = [
            # fetch API (multiple variations)
            (r'fetch\s*\(\s*[`"\']([^`"\']+)[`"\']', "fetch"),
            (r'fetch\s*\(\s*`([^`]+)`', "fetch-template"),
            (r'fetch\s*\(\s*([A-Z_]+)\s*[,\)]', "fetch-env"),
            
            # axios (all methods)
            (r'axios\s*\.\s*(get|post|put|delete|patch|head|options)\s*\(\s*[`"\']([^`"\']+)', "axios"),
            (r'axios\s*\(\s*\{[^}]*url\s*:\s*[`"\']([^`"\']+)', "axios-config"),
            (r'axios\.create\s*\(\s*\{[^}]*baseURL\s*:\s*[`"\']([^`"\']+)', "axios-instance"),
            
            # got (Node.js HTTP client)
            (r'got\s*\.\s*(get|post|put|delete|patch)\s*\(\s*[`"\']([^`"\']+)', "got"),
            (r'got\s*\(\s*[`"\']([^`"\']+)', "got"),
            
            # ky (modern fetch wrapper)
            (r'ky\s*\.\s*(get|post|put|delete|patch)\s*\(\s*[`"\']([^`"\']+)', "ky"),
            
            # node-fetch
            (r'import.*from\s*["\']node-fetch["\']', "node-fetch-import"),
            
            # superagent
            (r'superagent\s*\.\s*(get|post|put|delete|patch)\s*\(\s*[`"\']([^`"\']+)', "superagent"),
            
            # request (deprecated but still used)
            (r'request\s*\(\s*[`"\']([^`"\']+)', "request"),
            
            # undici (Node.js)
            (r'undici\s*\.\s*(request|fetch)\s*\(\s*[`"\']([^`"\']+)', "undici"),
        ]
        
        # ─────────────────────────────────────────
        # Next.js Patterns
        # ─────────────────────────────────────────
        
        nextjs_patterns = [
            # API routes (pages/api and app/api)
            (r'export\s+(?:async\s+)?function\s+(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s*\(', "nextjs-route-handler"),
            (r'export\s+default\s+(?:async\s+)?function\s+handler\s*\(', "nextjs-api-route"),
            
            # Server actions
            (r'["\']use server["\']', "nextjs-server-action"),
            
            # getServerSideProps, getStaticProps
            (r'export\s+(?:async\s+)?function\s+getServerSideProps', "nextjs-gsp"),
            (r'export\s+(?:async\s+)?function\s+getStaticProps', "nextjs-gssp"),
            
            # Next.js fetch extensions
            (r'fetch\s*\([^)]*,\s*\{[^}]*next\s*:', "nextjs-fetch"),
            (r'revalidatePath|revalidateTag', "nextjs-revalidate"),
        ]
        
        # ─────────────────────────────────────────
        # NestJS Patterns
        # ─────────────────────────────────────────
        
        nestjs_patterns = [
            # Controllers and routes
            (r'@Controller\s*\(\s*[`"\']([^`"\']*)[`"\']?\s*\)', "nestjs-controller"),
            (r'@(Get|Post|Put|Delete|Patch|Head|Options|All)\s*\(\s*[`"\']?([^`"\')\s]*)', "nestjs-route"),
            
            # Injectable services
            (r'@Injectable\s*\(\s*\)', "nestjs-service"),
            
            # Event patterns
            (r'@EventPattern\s*\(\s*[`"\']([^`"\']+)', "nestjs-event-pattern"),
            (r'@MessagePattern\s*\(\s*[`"\']([^`"\']+)', "nestjs-message-pattern"),
            
            # Microservices
            (r'@Client\s*\(\s*\{', "nestjs-client"),
            (r'ClientProxy', "nestjs-client-proxy"),
            (r'@GrpcMethod\s*\(\s*[`"\']([^`"\']+)', "nestjs-grpc"),
            
            # WebSocket
            (r'@WebSocketGateway', "nestjs-websocket"),
            (r'@SubscribeMessage\s*\(\s*[`"\']([^`"\']+)', "nestjs-ws-message"),
        ]
        
        # ─────────────────────────────────────────
        # tRPC Patterns
        # ─────────────────────────────────────────
        
        trpc_patterns = [
            (r'\.query\s*\(\s*[`"\']([^`"\']+)', "trpc-query"),
            (r'\.mutation\s*\(\s*[`"\']([^`"\']+)', "trpc-mutation"),
            (r'\.subscription\s*\(\s*[`"\']([^`"\']+)', "trpc-subscription"),
            (r'createTRPCRouter|initTRPC', "trpc-router"),
            (r't\.router\s*\(\s*\{', "trpc-router-v10"),
            (r'trpc\.createClient', "trpc-client"),
        ]
        
        # ─────────────────────────────────────────
        # GraphQL Patterns
        # ─────────────────────────────────────────
        
        graphql_patterns = [
            # Apollo Client
            (r'useQuery\s*\(\s*([A-Z_]+)', "apollo-usequery"),
            (r'useMutation\s*\(\s*([A-Z_]+)', "apollo-usemutation"),
            (r'useLazyQuery\s*\(\s*([A-Z_]+)', "apollo-uselazyquery"),
            (r'useSubscription\s*\(\s*([A-Z_]+)', "apollo-usesubscription"),
            (r'ApolloClient\s*\(\s*\{[^}]*uri\s*:\s*[`"\']([^`"\']+)', "apollo-client"),
            (r'new\s+ApolloClient', "apollo-client-new"),
            
            # urql
            (r'createClient\s*\(\s*\{[^}]*url\s*:\s*[`"\']([^`"\']+)', "urql-client"),
            
            # graphql-request
            (r'new\s+GraphQLClient\s*\(\s*[`"\']([^`"\']+)', "graphql-request"),
            (r'request\s*\(\s*[`"\']([^`"\']+)[`"\'],\s*[`"\']', "graphql-request-simple"),
            
            # gql tag
            (r'gql`[^`]*(?:query|mutation|subscription)\s+(\w+)', "graphql-operation"),
        ]
        
        # ─────────────────────────────────────────
        # Database ORM Patterns
        # ─────────────────────────────────────────
        
        database_patterns = [
            # Prisma
            (r'@prisma/client', "prisma-client"),
            (r'new\s+PrismaClient', "prisma-instance"),
            (r'prisma\.\w+\.(findMany|findUnique|findFirst|create|update|delete|upsert)', "prisma-query"),
            (r'\$queryRaw|\$executeRaw', "prisma-raw"),
            
            # TypeORM
            (r'@Entity\s*\(', "typeorm-entity"),
            (r'@Column|@PrimaryGeneratedColumn|@ManyToOne|@OneToMany|@ManyToMany', "typeorm-column"),
            (r'getRepository|createConnection|DataSource', "typeorm-connection"),
            (r'\.createQueryBuilder\s*\(', "typeorm-querybuilder"),
            
            # Drizzle
            (r'drizzle\s*\(', "drizzle-instance"),
            (r'import.*from\s*["\']drizzle-orm', "drizzle-import"),
            (r'pgTable|mysqlTable|sqliteTable', "drizzle-schema"),
            
            # Mongoose
            (r'mongoose\.connect\s*\(\s*[`"\']([^`"\']+)', "mongoose-connect"),
            (r'new\s+Schema\s*\(|mongoose\.Schema', "mongoose-schema"),
            (r'mongoose\.model\s*\(', "mongoose-model"),
            
            # Kysely
            (r'import.*from\s*["\']kysely', "kysely-import"),
            (r'new\s+Kysely', "kysely-instance"),
            
            # Sequelize
            (r'new\s+Sequelize\s*\(', "sequelize-instance"),
            (r'sequelize\.define', "sequelize-model"),
            
            # Knex
            (r'knex\s*\(\s*[`"\'](\w+)[`"\']', "knex-query"),
            (r'import.*from\s*["\']knex', "knex-import"),
            
            # Raw database drivers
            (r'pg\.Pool|new\s+Pool\s*\(', "pg-pool"),
            (r'mysql\.createConnection|mysql2', "mysql-driver"),
            (r'MongoClient\.connect', "mongodb-native"),
            (r'import.*from\s*["\']redis["\']|createClient.*redis', "redis-driver"),
            (r'import.*from\s*["\']ioredis["\']|new\s+Redis\s*\(', "ioredis"),
        ]
        
        # ─────────────────────────────────────────
        # Message Queue Patterns
        # ─────────────────────────────────────────
        
        mq_patterns = [
            # Kafka
            (r'kafkajs|KafkaJS|new\s+Kafka\s*\(', "kafka"),
            (r'\.producer\s*\(\s*\)|\.consumer\s*\(\s*\{', "kafka-client"),
            
            # RabbitMQ / AMQP
            (r'amqplib|amqp\.connect', "rabbitmq"),
            
            # Bull / BullMQ
            (r'new\s+Queue\s*\(\s*[`"\']([^`"\']+)', "bull-queue"),
            (r'import.*from\s*["\']bullmq["\']', "bullmq"),
            (r'@Process\s*\(|@Processor\s*\(', "bull-processor"),
            
            # AWS SQS
            (r'SQSClient|@aws-sdk/client-sqs', "aws-sqs"),
            (r'\.sendMessage\s*\(|\.receiveMessage\s*\(', "sqs-operation"),
            
            # Google Pub/Sub
            (r'@google-cloud/pubsub|PubSub\s*\(', "gcp-pubsub"),
            
            # Azure Service Bus
            (r'@azure/service-bus|ServiceBusClient', "azure-servicebus"),
        ]
        
        # ─────────────────────────────────────────
        # WebSocket Patterns
        # ─────────────────────────────────────────
        
        websocket_patterns = [
            (r'new\s+WebSocket\s*\(\s*[`"\']([^`"\']+)', "websocket"),
            (r'socket\.io|io\s*\(\s*[`"\']([^`"\']+)', "socketio"),
            (r'import.*from\s*["\']ws["\']', "ws-library"),
            (r'new\s+Server\s*\([^)]*WebSocket', "ws-server"),
        ]
        
        # ─────────────────────────────────────────
        # Third-Party SDK Patterns
        # ─────────────────────────────────────────
        
        sdk_patterns = [
            # Payment providers
            (r'stripe|Stripe\s*\(', "Stripe"),
            (r'@paypal|paypal\.Buttons', "PayPal"),
            (r'braintree', "Braintree"),
            (r'square|Square\s*\(', "Square"),
            
            # Auth providers
            (r'@auth0|Auth0Client|createAuth0Client', "Auth0"),
            (r'@clerk|ClerkProvider|useClerk', "Clerk"),
            (r'next-auth|NextAuth|getServerSession', "NextAuth"),
            (r'@supabase|createClient.*supabase', "Supabase"),
            (r'firebase|Firebase|initializeApp', "Firebase"),
            (r'@aws-amplify|Amplify\.configure', "AWS Amplify"),
            
            # Communication
            (r'twilio|Twilio\s*\(', "Twilio"),
            (r'@sendgrid|sendgrid', "SendGrid"),
            (r'nodemailer|createTransport', "Nodemailer"),
            (r'@mailchimp|mailchimp', "Mailchimp"),
            (r'postmark', "Postmark"),
            (r'resend|Resend\s*\(', "Resend"),
            
            # Cloud storage
            (r'@aws-sdk/client-s3|S3Client', "AWS S3"),
            (r'@google-cloud/storage', "GCP Storage"),
            (r'@azure/storage-blob', "Azure Blob"),
            (r'cloudinary', "Cloudinary"),
            (r'uploadthing', "UploadThing"),
            
            # Analytics & Monitoring
            (r'@sentry|Sentry\.init', "Sentry"),
            (r'@segment|Analytics\s*\(', "Segment"),
            (r'mixpanel', "Mixpanel"),
            (r'@datadog|datadogRum', "Datadog"),
            (r'posthog|PostHog', "PostHog"),
            (r'@vercel/analytics', "Vercel Analytics"),
            
            # Search
            (r'algolia|algoliasearch', "Algolia"),
            (r'@elastic/elasticsearch|ElasticSearch', "Elasticsearch"),
            (r'meilisearch', "Meilisearch"),
            (r'typesense', "Typesense"),
            
            # CMS
            (r'@sanity|createClient.*sanity', "Sanity"),
            (r'contentful', "Contentful"),
            (r'@strapi', "Strapi"),
            (r'@prismic', "Prismic"),
            
            # AI/ML
            (r'openai|OpenAI\s*\(', "OpenAI"),
            (r'@anthropic|Anthropic\s*\(', "Anthropic"),
            (r'@huggingface|HfInference', "Hugging Face"),
            (r'replicate', "Replicate"),
            (r'@langchain', "LangChain"),
            (r'@vercel/ai|useChat|useCompletion', "Vercel AI"),
            
            # Feature flags
            (r'@vercel/flags|flags\s*\(', "Vercel Flags"),
            (r'launchdarkly|LDClient', "LaunchDarkly"),
            (r'flagsmith', "Flagsmith"),
            (r'@growthbook', "GrowthBook"),
        ]
        
        # ─────────────────────────────────────────
        # Environment Variable Patterns (service URLs)
        # ─────────────────────────────────────────
        
        env_patterns = [
            (r'process\.env\.([A-Z][A-Z0-9_]*(?:URL|URI|HOST|ENDPOINT|API|SERVICE)[A-Z0-9_]*)', "env-service-url"),
            (r'process\.env\.([A-Z][A-Z0-9_]*(?:DATABASE|DB|REDIS|MONGO|POSTGRES|MYSQL)[A-Z0-9_]*)', "env-database"),
            (r'process\.env\.([A-Z][A-Z0-9_]*(?:QUEUE|KAFKA|RABBIT|SQS|PUBSUB)[A-Z0-9_]*)', "env-queue"),
        ]
        
        # ─────────────────────────────────────────
        # TypeScript-specific patterns
        # ─────────────────────────────────────────
        
        typescript_type_patterns = [
            # Exported interfaces and types (for exposes.types)
            (r'export\s+(?:interface|type)\s+(\w+)', "ts-export-type"),
            
            # Zod schemas
            (r'z\.object\s*\(\s*\{|z\.enum\s*\(|export\s+const\s+(\w+Schema)\s*=\s*z\.', "zod-schema"),
            
            # io-ts
            (r't\.type\s*\(\s*\{|t\.interface\s*\(', "io-ts-type"),
        ]
        
        # ─────────────────────────────────────────
        # Process Files
        # ─────────────────────────────────────────
        
        file_patterns = ["*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs", "*.cjs"]
        
        exposed_routes = []
        exposed_events = []
        exposed_types = []
        
        for pattern in file_patterns:
            for js_file in self.root.rglob(pattern):
                if should_skip_path(js_file):
                    continue
                
                content = safe_read_text(js_file)
                if not content:
                    continue
                
                rel_path = str(js_file.relative_to(self.root))
                
                # ─────────────────────────────────────────
                # Detect HTTP calls
                # ─────────────────────────────────────────
                for http_pattern, pattern_type in http_patterns:
                    for match in re.finditer(http_pattern, content, re.MULTILINE):
                        groups = match.groups()
                        
                        if len(groups) >= 2:
                            method = groups[0].upper() if groups[0] in ["get", "post", "put", "delete", "patch", "head", "options"] else "GET"
                            url = groups[1]
                        elif len(groups) == 1:
                            url = groups[0]
                            method = "GET"
                        else:
                            continue
                        
                        # Skip template literals with complex expressions
                        if "${" in url and "}" in url:
                            # Try to extract base URL
                            base_match = re.match(r'^([^$]+)', url)
                            if base_match:
                                url = base_match.group(1).rstrip("/")
                            else:
                                continue
                        
                        # External API call
                        if url.startswith("http://") or url.startswith("https://"):
                            deps["depends_on"]["apis_consumed"].append(f"{method} {url}")
                            
                            # Extract service/domain
                            service_match = re.search(r'https?://([^/:]+)', url)
                            if service_match:
                                service = service_match.group(1)
                                if service not in ["localhost", "127.0.0.1", "0.0.0.0"]:
                                    deps["depends_on"]["services"].add(service)
                        
                        # Internal API route reference
                        elif url.startswith("/api/") or url.startswith("/v1/") or url.startswith("/v2/"):
                            exposed_routes.append(f"{method} {url}")
                
                # ─────────────────────────────────────────
                # Detect Next.js patterns
                # ─────────────────────────────────────────
                for nextjs_pattern, pattern_type in nextjs_patterns:
                    for match in re.finditer(nextjs_pattern, content):
                        if pattern_type == "nextjs-route-handler":
                            method = match.group(1)
                            # Infer route from file path
                            route = self._infer_nextjs_route(js_file)
                            if route:
                                exposed_routes.append(f"{method} {route}")
                        elif pattern_type == "nextjs-api-route":
                            route = self._infer_nextjs_route(js_file)
                            if route:
                                exposed_routes.append(f"* {route}")
                
                # ─────────────────────────────────────────
                # Detect NestJS patterns
                # ─────────────────────────────────────────
                current_controller_path = ""
                for nestjs_pattern, pattern_type in nestjs_patterns:
                    for match in re.finditer(nestjs_pattern, content):
                        if pattern_type == "nestjs-controller":
                            current_controller_path = match.group(1) if match.group(1) else ""
                        elif pattern_type == "nestjs-route":
                            method = match.group(1).upper()
                            route_path = match.group(2) if len(match.groups()) > 1 else ""
                            full_route = f"/{current_controller_path}/{route_path}".replace("//", "/").rstrip("/")
                            exposed_routes.append(f"{method} {full_route}")
                        elif pattern_type in ["nestjs-event-pattern", "nestjs-message-pattern"]:
                            event_name = match.group(1)
                            exposed_events.append(event_name)
                        elif pattern_type == "nestjs-ws-message":
                            event_name = match.group(1)
                            exposed_events.append(f"ws:{event_name}")
                
                # ─────────────────────────────────────────
                # Detect tRPC patterns
                # ─────────────────────────────────────────
                for trpc_pattern, pattern_type in trpc_patterns:
                    for match in re.finditer(trpc_pattern, content):
                        if pattern_type in ["trpc-query", "trpc-mutation", "trpc-subscription"]:
                            procedure_name = match.group(1)
                            exposed_routes.append(f"tRPC:{pattern_type.split('-')[1]}:{procedure_name}")
                        elif "router" in pattern_type:
                            if "trpc" not in [t.lower() for t in deps["tags"]]:
                                deps["tags"].append("trpc")
                
                # ─────────────────────────────────────────
                # Detect GraphQL patterns
                # ─────────────────────────────────────────
                for gql_pattern, pattern_type in graphql_patterns:
                    for match in re.finditer(gql_pattern, content):
                        if pattern_type == "apollo-client" or pattern_type == "urql-client":
                            url = match.group(1)
                            deps["depends_on"]["apis_consumed"].append(f"GraphQL {url}")
                            
                            service_match = re.search(r'https?://([^/:]+)', url)
                            if service_match:
                                deps["depends_on"]["services"].add(service_match.group(1))
                        elif pattern_type == "graphql-operation":
                            operation_name = match.group(1)
                            exposed_routes.append(f"GraphQL:{operation_name}")
                        
                        if "graphql" not in [t.lower() for t in deps["tags"]]:
                            deps["tags"].append("graphql")
                
                # ─────────────────────────────────────────
                # Detect database usage
                # ─────────────────────────────────────────
                for db_pattern, pattern_type in database_patterns:
                    if re.search(db_pattern, content, re.IGNORECASE):
                        db_name = self._get_db_name_from_pattern(pattern_type)
                        if db_name and db_name not in deps["depends_on"]["databases"]:
                            deps["depends_on"]["databases"].append(db_name)
                
                # ─────────────────────────────────────────
                # Detect message queues
                # ─────────────────────────────────────────
                for mq_pattern, pattern_type in mq_patterns:
                    for match in re.finditer(mq_pattern, content):
                        mq_name = self._get_mq_name_from_pattern(pattern_type)
                        if mq_name and mq_name not in deps["depends_on"]["message_queues"]:
                            deps["depends_on"]["message_queues"].append(mq_name)
                        
                        # Extract queue names
                        if pattern_type == "bull-queue":
                            queue_name = match.group(1)
                            exposed_events.append(f"queue:{queue_name}")
                
                # ─────────────────────────────────────────
                # Detect WebSocket usage
                # ─────────────────────────────────────────
                for ws_pattern, pattern_type in websocket_patterns:
                    for match in re.finditer(ws_pattern, content):
                        if "WebSocket" not in deps["depends_on"]["message_queues"]:
                            deps["depends_on"]["message_queues"].append("WebSocket")
                        
                        if len(match.groups()) > 0:
                            ws_url = match.group(1)
                            if ws_url.startswith("ws://") or ws_url.startswith("wss://"):
                                deps["depends_on"]["apis_consumed"].append(f"WS {ws_url}")
                        
                        if "realtime" not in deps["tags"]:
                            deps["tags"].append("realtime")
                
                # ─────────────────────────────────────────
                # Detect third-party SDKs
                # ─────────────────────────────────────────
                for sdk_pattern, sdk_name in sdk_patterns:
                    if re.search(sdk_pattern, content, re.IGNORECASE):
                        if sdk_name not in deps["depends_on"]["external_apis"]:
                            deps["depends_on"]["external_apis"].append(sdk_name)
                
                # ─────────────────────────────────────────
                # Detect environment variable service references
                # ─────────────────────────────────────────
                for env_pattern, pattern_type in env_patterns:
                    for match in re.finditer(env_pattern, content):
                        env_var = match.group(1)
                        if pattern_type == "env-service-url":
                            deps["depends_on"]["services"].add(f"${{{env_var}}}")
                        elif pattern_type == "env-database":
                            if env_var not in str(deps["depends_on"]["databases"]):
                                deps["depends_on"]["databases"].append(f"${{{env_var}}}")
                
                # ─────────────────────────────────────────
                # Detect exported types
                # ─────────────────────────────────────────
                for type_pattern, pattern_type in typescript_type_patterns:
                    for match in re.finditer(type_pattern, content):
                        if pattern_type == "ts-export-type" and len(match.groups()) > 0:
                            type_name = match.group(1)
                            # Filter common types
                            if type_name not in ["Props", "State", "Context", "Config", "Options"]:
                                exposed_types.append(type_name)
                        elif pattern_type == "zod-schema" and len(match.groups()) > 0:
                            schema_name = match.group(1)
                            if schema_name:
                                exposed_types.append(schema_name)
        
        # ─────────────────────────────────────────
        # Update dependencies
        # ─────────────────────────────────────────
        deps["exposes"]["api"].extend(exposed_routes)
        deps["exposes"]["events"].extend(exposed_events)
        deps["exposes"]["types"].extend(exposed_types)
    
    def _detect_rust_dependencies(self, deps: dict) -> None:
        """Detect Rust external dependencies."""
        
        cargo_toml = self.root / "Cargo.toml"
        if not cargo_toml.exists():
            return
        
        content = safe_read_text(cargo_toml)
        if not content:
            return
        
        # Detect HTTP clients
        if re.search(r'reqwest\s*=', content):
            deps["depends_on"]["services"].add("http-client")
        
        # Detect databases
        if re.search(r'sqlx\s*=', content):
            deps["depends_on"]["databases"].append("Database (SQLx)")
        if re.search(r'diesel\s*=', content):
            deps["depends_on"]["databases"].append("Database (Diesel)")
        if re.search(r'redis\s*=', content):
            deps["depends_on"]["databases"].append("Redis")
        
        # Detect gRPC
        if re.search(r'tonic\s*=', content):
            deps["depends_on"]["services"].add("grpc")
    
    def _detect_go_dependencies(self, deps: dict) -> None:
        """Detect Go external dependencies."""
        
        go_mod = self.root / "go.mod"
        if not go_mod.exists():
            return
        
        content = safe_read_text(go_mod)
        if not content:
            return
        
        # Detect HTTP clients
        if "net/http" in content or "github.com/go-resty" in content:
            deps["depends_on"]["services"].add("http-client")
        
        # Detect databases
        if "gorm.io" in content or "database/sql" in content:
            deps["depends_on"]["databases"].append("Database")
        if "github.com/go-redis" in content:
            deps["depends_on"]["databases"].append("Redis")
        if "go.mongodb.org" in content:
            deps["depends_on"]["databases"].append("MongoDB")
        
        # Detect gRPC
        if "google.golang.org/grpc" in content:
            deps["depends_on"]["services"].add("grpc")

    def _infer_nextjs_route(self, filepath: Path) -> Optional[str]:
        """Infer Next.js API route from file path."""
        path_str = str(filepath)
        
        # App Router: app/api/*/route.ts -> /api/*
        if "/app/api/" in path_str and "route." in filepath.name:
            match = re.search(r'/app(/api/[^/]+(?:/[^/]+)*)/route\.\w+$', path_str)
            if match:
                route = match.group(1)
                # Convert [param] to {param}
                route = re.sub(r'\[(\w+)\]', r'{\1}', route)
                return route
        
        # Pages Router: pages/api/*.ts -> /api/*
        if "/pages/api/" in path_str:
            match = re.search(r'/pages(/api/[^.]+)\.\w+$', path_str)
            if match:
                route = match.group(1)
                route = re.sub(r'\[(\w+)\]', r'{\1}', route)
                return route
        
        return None
    
    def _get_db_name_from_pattern(self, pattern_type: str) -> Optional[str]:
        """Get database name from pattern type."""
        mapping = {
            "prisma-client": "Database (Prisma)",
            "prisma-instance": "Database (Prisma)",
            "prisma-query": "Database (Prisma)",
            "prisma-raw": "Database (Prisma)",
            "typeorm-entity": "Database (TypeORM)",
            "typeorm-column": "Database (TypeORM)",
            "typeorm-connection": "Database (TypeORM)",
            "typeorm-querybuilder": "Database (TypeORM)",
            "drizzle-instance": "Database (Drizzle)",
            "drizzle-import": "Database (Drizzle)",
            "drizzle-schema": "Database (Drizzle)",
            "mongoose-connect": "MongoDB",
            "mongoose-schema": "MongoDB",
            "mongoose-model": "MongoDB",
            "kysely-import": "Database (Kysely)",
            "kysely-instance": "Database (Kysely)",
            "sequelize-instance": "Database (Sequelize)",
            "sequelize-model": "Database (Sequelize)",
            "knex-query": "Database (Knex)",
            "knex-import": "Database (Knex)",
            "pg-pool": "PostgreSQL",
            "mysql-driver": "MySQL",
            "mongodb-native": "MongoDB",
            "redis-driver": "Redis",
            "ioredis": "Redis",
        }
        return mapping.get(pattern_type)
    
    def _get_mq_name_from_pattern(self, pattern_type: str) -> Optional[str]:
        """Get message queue name from pattern type."""
        mapping = {
            "kafka": "Kafka",
            "kafka-client": "Kafka",
            "rabbitmq": "RabbitMQ",
            "bull-queue": "Bull/Redis Queue",
            "bullmq": "BullMQ/Redis Queue",
            "bull-processor": "Bull/Redis Queue",
            "aws-sqs": "AWS SQS",
            "sqs-operation": "AWS SQS",
            "gcp-pubsub": "Google Pub/Sub",
            "azure-servicebus": "Azure Service Bus",
        }
        return mapping.get(pattern_type)

class LLMContextGenerator:
    """Main orchestrator."""
    
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
        """Generate all context files."""
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
        print(f"  LLM Context Generator v{VERSION}")
        print(f"  Project: {self.root}")
        print(f"  Mode: {mode}")
        print(f"  Security: {self.security.mode}")
        print("=" * 60)
        print("")
        
        print("-> Detecting project type...")
        detector = ProjectDetector(self.root)
        project = detector.detect()
        
        print(f"  Name: {project.name}")
        print(f"  Languages: {', '.join(project.languages) or 'unknown'}")
        print(f"  Framework: {project.framework}")
        
        if self.updater.old_manifest:
            print(f"  Last generated: {self.updater.old_manifest.generated_at}")
        print("")
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        gen = self.config["generate"]
        
        if self.quick_mode:
            skip_keys = ["module_summaries", "db_schema"]
            gen = {k: v for k, v in gen.items() if k not in skip_keys}
        
        if gen.get("tree"):
            self._generate_tree()
        
        if gen.get("schemas"):
            self._generate_schemas(project)
        
        if gen.get("routes"):
            self._generate_routes(project)
        
        if gen.get("public_api"):
            self._generate_public_api(project)
        
        if gen.get("dependencies"):
            self._generate_dependencies(project, gen)
        
        if gen.get("symbol_index"):
            self._generate_symbol_index(project)
        
        if gen.get("entry_points"):
            self._generate_entry_points(project)
        
        if gen.get("db_schema"):
            self._generate_db_schema()
        
        if gen.get("api_contract"):
            self._generate_api_contract()
        
        if gen.get("env_shape"):
            self._generate_env_shape()
        
        self._copy_dependency_files()
        
        if gen.get("recent_activity"):
            self._generate_recent_activity()
        
        if gen.get("claude_md_scaffold"):
            self._generate_claude_md(project)
        
        if gen.get("architecture_md_scaffold"):
            self._generate_architecture_md(project)
        
        if gen.get("module_summaries") and not self.quick_mode:
            self._generate_module_summaries(project)
        # ─────────────────────────────────────────
        # External dependencies detection
        # ─────────────────────────────────────────
        if gen.get("external_dependencies", True):
            self._generate_external_dependencies(project)
            
        self.updater.new_manifest.save(self.root)
        
        self.security.log_audit("generate", {"mode": mode})
        
        print("")
        print("=" * 60)
        print(f"  Context generated in {self.output_dir}")
        self.updater.print_summary()
        
        if self.updater.stats["regenerated"] > 0 or self.updater.stats["new"] > 0:
            print("Updated/new files:")
            for f in sorted(self.output_dir.rglob("*")):
                if f.is_file():
                    rel = f.relative_to(self.output_dir)
                    size = human_readable_size(f.stat().st_size)
                    entry = self.updater.new_manifest.get_entry(str(rel))
                    if entry:
                        if entry.generated_at == self.updater.new_manifest.generated_at:
                            print(f"  - {rel} ({size})")
    
    def _write(self, filename: str, content: str) -> None:
        """Write file to output directory."""
        if filename.startswith("../"):
            path = (self.output_dir / filename).resolve()
        else:
            path = self.output_dir / filename
        safe_write_text(path, content)
    
    def _generate_tree(self) -> None:
        """Generate file tree."""
        should_regen, reason = self.updater.should_regenerate("tree.txt")
        if should_regen:
            print(f"-> Generating file tree... ({reason})")
            tree, sources = TreeGenerator(self.root, self.config).generate()
            self._write("tree.txt", tree)
            self.updater.mark_generated("tree.txt", tree, sources)
        else:
            print(f"  tree.txt ({reason})")
            self.updater.mark_skipped("tree.txt")
    
    def _generate_schemas(self, project: ProjectInfo) -> None:
        """Generate schema extractions."""
        print("-> Checking schemas/types...")
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
                print(f"  {filename} ({reason})")
                self.updater.mark_skipped(filename)
    
    def _generate_routes(self, project: ProjectInfo) -> None:
        """Generate routes file."""
        api = APIExtractor(self.root, project.languages, project.framework)
        routes, sources = api.extract_routes()
        
        if routes:
            should_regen, reason = self.updater.should_regenerate("routes.txt", sources)
            if should_regen:
                print(f"-> Extracting routes... ({reason})")
                self._write("routes.txt", routes)
                self.updater.mark_generated("routes.txt", routes, sources)
            else:
                print(f"  routes.txt ({reason})")
                self.updater.mark_skipped("routes.txt")
    
    def _generate_public_api(self, project: ProjectInfo) -> None:
        """Generate public API file."""
        api = APIExtractor(self.root, project.languages, project.framework)
        public_api, sources = api.extract_public_api()
        
        if public_api:
            should_regen, reason = self.updater.should_regenerate("public-api.txt", sources)
            if should_regen:
                print(f"-> Extracting public API... ({reason})")
                self._write("public-api.txt", public_api)
                self.updater.mark_generated("public-api.txt", public_api, sources)
            else:
                print(f"  public-api.txt ({reason})")
                self.updater.mark_skipped("public-api.txt")
   def _generate_external_dependencies(self, project: ProjectInfo) -> None:
        """Generate external-dependencies.json."""
        detector = ExternalDependencyDetector(
            self.root,
            project.languages,
            project.framework
        )
        
        should_regen, reason = self.updater.should_regenerate("external-dependencies.json")
        
        if should_regen:
            print(f"-> Detecting external dependencies... ({reason})")
            dependencies = detector.detect()
            content = json.dumps(dependencies, indent=2)
            self._write("external-dependencies.json", content)
            self.updater.mark_generated("external-dependencies.json", content, [])
        else:
            print(f"  external-dependencies.json ({reason})")
            self.updater.mark_skipped("external-dependencies.json")    
            
    def _generate_dependencies(self, project: ProjectInfo, gen: dict) -> None:
        """Generate dependency analysis."""
        analyzer = DependencyAnalyzer(self.root, project.languages)
        deps, sources = analyzer.analyze()
        
        if deps:
            should_regen, reason = self.updater.should_regenerate(
                "dependency-graph.txt", sources
            )
            if should_regen:
                print(f"-> Analyzing dependencies... ({reason})")
                self._write("dependency-graph.txt", deps)
                self.updater.mark_generated("dependency-graph.txt", deps, sources)
                
                if gen.get("dependency_graph_mermaid"):
                    visualizer = DependencyGraphVisualizer()
                    mermaid = visualizer.generate_mermaid(deps)
                    self._write("dependency-graph.md", mermaid)
                    self.updater.mark_generated("dependency-graph.md", mermaid, sources)
            else:
                print(f"  dependency-graph.txt ({reason})")
                self.updater.mark_skipped("dependency-graph.txt")
                if gen.get("dependency_graph_mermaid"):
                    self.updater.mark_skipped("dependency-graph.md")
    
    def _generate_symbol_index(self, project: ProjectInfo) -> None:
        """Generate symbol index."""
        indexer = SymbolIndexGenerator(self.root, project.languages)
        symbols, sources = indexer.generate()
        
        should_regen, reason = self.updater.should_regenerate(
            "symbol-index.json", sources
        )
        if should_regen:
            print(f"-> Generating symbol index... ({reason})")
            self._write("symbol-index.json", symbols)
            self.updater.mark_generated("symbol-index.json", symbols, sources)
        else:
            print(f"  symbol-index.json ({reason})")
            self.updater.mark_skipped("symbol-index.json")
    
    def _generate_entry_points(self, project: ProjectInfo) -> None:
        """Generate entry points file."""
        detector = EntryPointDetector(self.root, project.languages)
        entry_points, sources = detector.detect()
        
        should_regen, reason = self.updater.should_regenerate(
            "entry-points.json", sources
        )
        if should_regen:
            print(f"-> Detecting entry points... ({reason})")
            self._write("entry-points.json", entry_points)
            self.updater.mark_generated("entry-points.json", entry_points, sources)
        else:
            print(f"  entry-points.json ({reason})")
            self.updater.mark_skipped("entry-points.json")
    
    def _generate_db_schema(self) -> None:
        """Generate database schema."""
        extractor = DatabaseSchemaExtractor(self.root)
        result = extractor.extract()
        
        if result:
            schema, sources = result
            should_regen, reason = self.updater.should_regenerate(
                "db-schema.txt", sources
            )
            if should_regen:
                print(f"-> Extracting database schema... ({reason})")
                self._write("db-schema.txt", schema)
                self.updater.mark_generated("db-schema.txt", schema, sources)
            else:
                print(f"  db-schema.txt ({reason})")
                self.updater.mark_skipped("db-schema.txt")
    
    def _generate_api_contract(self) -> None:
        """Generate API contract."""
        extractor = APIContractExtractor(self.root)
        result = extractor.extract()
        
        if result:
            content, sources = result
            should_regen, reason = self.updater.should_regenerate(
                "api-contract.md", sources
            )
            if should_regen:
                print(f"-> Extracting API contract... ({reason})")
                self._write("api-contract.md", content)
                self.updater.mark_generated("api-contract.md", content, sources)
            else:
                print(f"  api-contract.md ({reason})")
                self.updater.mark_skipped("api-contract.md")
    
    def _generate_env_shape(self) -> None:
        """Generate environment shape."""
        env_files = [".env.example", ".env.template", ".env.sample"]
        for env_file in env_files:
            env_path = self.root / env_file
            if env_path.exists():
                should_regen, reason = self.updater.should_regenerate(
                    "env-shape.txt", [env_path]
                )
                if should_regen:
                    print(f"-> Copying {env_file}... ({reason})")
                    content = safe_read_text(env_path) or ""
                    content = self.security.redact_content(content)
                    self._write("env-shape.txt", content)
                    self.updater.mark_generated("env-shape.txt", content, [env_path])
                else:
                    print(f"  env-shape.txt ({reason})")
                    self.updater.mark_skipped("env-shape.txt")
                break
    
    def _copy_dependency_files(self) -> None:
        """Copy dependency files."""
        dep_files = [
            "requirements.txt",
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
            "go.mod",
            "Gemfile",
        ]
        for dep_file in dep_files:
            dep_path = self.root / dep_file
            if dep_path.exists():
                should_regen, reason = self.updater.should_regenerate(
                    dep_file, [dep_path]
                )
                if should_regen:
                    print(f"-> Copying {dep_file}... ({reason})")
                    content = safe_read_text(dep_path) or ""
                    self._write(dep_file, content)
                    self.updater.mark_generated(dep_file, content, [dep_path])
                else:
                    print(f"  {dep_file} ({reason})")
                    self.updater.mark_skipped(dep_file)
    
    def _generate_recent_activity(self) -> None:
        """Generate recent git activity."""
        print("-> Capturing recent git activity...")
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-20"],
                capture_output=True,
                text=True,
                cwd=self.root,
            )
            if result.returncode == 0:
                self._write("recent-commits.txt", result.stdout)
                self.updater.mark_generated("recent-commits.txt", result.stdout)
            
            result = subprocess.run(
                ["git", "diff", "--stat", "HEAD~5"],
                capture_output=True,
                text=True,
                cwd=self.root,
            )
            if result.returncode == 0:
                self._write("recent-changes.txt", result.stdout)
                self.updater.mark_generated("recent-changes.txt", result.stdout)
        except Exception:
            pass
    
    def _generate_claude_md(self, project: ProjectInfo) -> None:
        """Generate LLM.md scaffold."""
        claude_path = self.root / "LLM.md"
        should_regen, reason = self.updater.should_regenerate("../LLM.md")
        
        if should_regen:
            print(f"-> Generating LLM.md scaffold... ({reason})")
            scaffold = ScaffoldGenerator(project)
            content = scaffold.generate_claude_md()
            safe_write_text(claude_path, content)
            self.updater.mark_generated("../LLM.md", content, is_new=True)
        else:
            print(f"  LLM.md ({reason})")
            self.updater.mark_skipped("../LLM.md")
    
    def _generate_architecture_md(self, project: ProjectInfo) -> None:
        """Generate ARCHITECTURE.md scaffold."""
        arch_path = self.root / "ARCHITECTURE.md"
        should_regen, reason = self.updater.should_regenerate("../ARCHITECTURE.md")
        
        if should_regen:
            print(f"-> Generating ARCHITECTURE.md scaffold... ({reason})")
            scaffold = ScaffoldGenerator(project)
            content = scaffold.generate_architecture_md()
            safe_write_text(arch_path, content)
            self.updater.mark_generated("../ARCHITECTURE.md", content, is_new=True)
        else:
            print(f"  ARCHITECTURE.md ({reason})")
            self.updater.mark_skipped("../ARCHITECTURE.md")
    
    def _generate_module_summaries(self, project: ProjectInfo) -> None:
        """Generate LLM module summaries."""
        if not self.security.is_ai_enabled():
            print("-> Skipping module summaries (AI disabled in offline mode)")
            return
        
        print("-> Generating LLM-powered module summaries...")
        
        summary_gen = ModuleSummaryGenerator(self.root, self.config)
        summaries = summary_gen.generate(project.languages)
        
        modules_dir = self.output_dir / "modules"
        modules_dir.mkdir(exist_ok=True)
        
        for filename, (content, sources) in summaries.items():
            module_path = f"modules/{filename}"
            safe_write_text(modules_dir / filename, content)
            self.updater.mark_generated(module_path, content, sources)
        
        if summaries:
            index_lines = ["# Module Summaries Index", ""]
            for f in sorted(summaries.keys()):
                index_lines.append(f"- [{f}](modules/{f})")
            index = "\n".join(index_lines)
            self._write("module-index.md", index)
            self.updater.mark_generated("module-index.md", index)


def watch_mode(root: Path, config: dict) -> None:
    """Watch for file changes and auto-update."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("Watch mode requires: pip install watchdog")
        sys.exit(1)
    
    class UpdateHandler(FileSystemEventHandler):
        def __init__(self):
            self.last_update = time.time()
            self.pending = set()
            self.timer = None
        
        def on_any_event(self, event):
            if event.is_directory:
                return
            
            path = Path(event.src_path)
            
            if ".llm-context" in path.parts:
                return
            if should_skip_path(path):
                return
            
            source_exts = {".py", ".ts", ".js", ".rs", ".go", ".cs", ".rb", ".java"}
            if path.suffix not in source_exts:
                return
            
            if not path.exists():
                return
            
            self.pending.add(path)
            
            if self.timer:
                self.timer.cancel()
            
            self.timer = threading.Timer(2.0, self.process_changes)
            self.timer.start()
        
        def process_changes(self):
            if not self.pending:
                return
            
            changes = self.pending.copy()
            self.pending.clear()
            
            print("")
            print("-" * 60)
            print(f"  Detected {len(changes)} file change(s)")
            
            for p in sorted(list(changes)[:10]):
                try:
                    rel_path = p.relative_to(root)
                    print(f"    - {rel_path}")
                except ValueError:
                    print(f"    - {p.name}")
            
            if len(changes) > 10:
                print(f"    ... and {len(changes) - 10} more")
            
            print("-" * 60)
            print("")
            
            try:
                generator = LLMContextGenerator(root, config, quick_mode=True)
                generator.generate()
            except Exception as e:
                print(f"  Error during update: {e}")
            
            self.last_update = time.time()
    
    handler = UpdateHandler()
    observer = Observer()
    observer.schedule(handler, str(root), recursive=True)
    observer.start()
    
    print(f"Watching {root} for changes...")
    print("Press Ctrl+C to stop")
    print("")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("")
        print("Stopping watch mode...")
        if handler.timer:
            handler.timer.cancel()
        observer.stop()
    
    observer.join()

# ──────────────────────────────────────────────
# Workspace Mode (Phase 3)
# ──────────────────────────────────────────────

@dataclass
class ServiceConfig:
    """Configuration for a service in the workspace."""
    name: str
    path: Path
    service_type: str
    tags: List[str]
    depends_on: List[str]
    description: str
    
    def exists(self) -> bool:
        """Check if service path exists."""
        return self.path.exists()


@dataclass
class WorkspaceManifest:
    """Parsed workspace configuration."""
    name: str
    version: str
    root: Path
    services: Dict[str, ServiceConfig]
    
    @classmethod
    def load(cls, workspace_file: Path) -> "WorkspaceManifest":
        """Load and parse workspace manifest."""
        try:
            import yaml
            content = safe_read_text(workspace_file)
            if not content:
                raise ValueError(f"Could not read {workspace_file}")
            data = yaml.safe_load(content)
        except ImportError:
            # Try JSON fallback
            content = safe_read_text(workspace_file)
            if not content:
                raise ValueError(f"Could not read {workspace_file}")
            if workspace_file.suffix in [".yml", ".yaml"]:
                raise ImportError("PyYAML required for workspace manifests: pip install pyyaml")
            data = json.loads(content)
        
        services = {}
        for name, config in data.get("services", {}).items():
            path_str = config.get("path", f"./{name}")
            path = (workspace_file.parent / path_str).resolve()
            
            services[name] = ServiceConfig(
                name=name,
                path=path,
                service_type=config.get("type", "unknown"),
                tags=config.get("tags", []),
                depends_on=config.get("depends_on", []),
                description=config.get("description", ""),
            )
        
        return cls(
            name=data.get("name", "workspace"),
            version=str(data.get("version", "1")),
            root=workspace_file.parent.resolve(),
            services=services,
        )
    
    def query_by_tags(self, tags: List[str]) -> List[ServiceConfig]:
        """Find services matching any of the given tags."""
        if not tags:
            return list(self.services.values())
        
        results = []
        for service in self.services.values():
            if any(tag.lower() in [t.lower() for t in service.tags] for tag in tags):
                results.append(service)
        return results
    
    def query_by_service(self, service_name: str) -> Optional[ServiceConfig]:
        """Get a specific service by name."""
        return self.services.get(service_name)
    
    def get_dependents(self, service_name: str) -> List[ServiceConfig]:
        """Get services that depend on the given service."""
        dependents = []
        for service in self.services.values():
            if service_name in service.depends_on:
                dependents.append(service)
        return dependents
    
    def get_dependencies(self, service_name: str) -> List[ServiceConfig]:
        """Get services that the given service depends on."""
        service = self.services.get(service_name)
        if not service:
            return []
        
        dependencies = []
        for dep_name in service.depends_on:
            if dep_name in self.services:
                dependencies.append(self.services[dep_name])
        return dependencies
    
    def get_dependency_order(self, services: List[ServiceConfig] = None) -> List[ServiceConfig]:
        """
        Order services by dependencies (topological sort).
        Services with no dependencies come first.
        """
        if services is None:
            services = list(self.services.values())
        
        service_names = {s.name for s in services}
        
        # Build adjacency list
        graph = {s.name: [] for s in services}
        in_degree = {s.name: 0 for s in services}
        
        for service in services:
            for dep in service.depends_on:
                if dep in service_names:
                    graph[dep].append(service.name)
                    in_degree[service.name] += 1
        
        # Kahn's algorithm
        queue = [name for name, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            node = queue.pop(0)
            result.append(self.services[node])
            
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # If we couldn't process all nodes, there's a cycle
        if len(result) != len(services):
            # Return original order with warning
            print("  Warning: Circular dependency detected")
            return services
        
        return result
    
    def validate(self) -> List[str]:
        """Validate workspace configuration and return list of issues."""
        issues = []
        
        for name, service in self.services.items():
            # Check if path exists
            if not service.path.exists():
                issues.append(f"Service '{name}': path does not exist: {service.path}")
            
            # Check dependencies exist
            for dep in service.depends_on:
                if dep not in self.services:
                    issues.append(f"Service '{name}': unknown dependency '{dep}'")
        
        return issues


class WorkspaceQuery:
    """Query workspace for services and dependencies."""
    
    def __init__(self, manifest: WorkspaceManifest):
        self.manifest = manifest
    
    def query_tags(self, tags: List[str], generate_context: bool = False) -> None:
        """Query services by tags and print results."""
        services = self.manifest.query_by_tags(tags)
        
        if not services:
            print(f"\n  No services found with tags: {', '.join(tags)}")
            print(f"\n  Available tags:")
            all_tags = set()
            for s in self.manifest.services.values():
                all_tags.update(s.tags)
            for tag in sorted(all_tags):
                print(f"    - {tag}")
            return
        
        print(f"\n{'='*60}")
        print(f"  Workspace: {self.manifest.name}")
        print(f"  Query: tags={tags}")
        print(f"{'='*60}")
        print(f"\n  Found {len(services)} service(s):\n")
        
        for service in services:
            deps = ", ".join(service.depends_on) if service.depends_on else "none"
            status = "✓" if service.exists() else "✗"
            print(f"  {status} {service.name:20s} [{service.service_type:12s}]")
            print(f"      Path: {service.path}")
            print(f"      Tags: {', '.join(service.tags)}")
            print(f"      Depends on: {deps}")
            if service.description:
                print(f"      Description: {service.description}")
            print()
        
        # Show dependency order
        ordered = self.manifest.get_dependency_order(services)
        print(f"  Suggested change sequence (from dependency graph):\n")
        for i, service in enumerate(ordered, 1):
            hint = self._get_change_hint(service)
            print(f"    {i}. {service.name:20s} <- {hint}")
        
        print()
        
        if generate_context:
            self._generate_workspace_context(services)
    
    def query_service(
        self,
        service_name: str,
        what: str = "info"
    ) -> None:
        """Query information about a specific service."""
        service = self.manifest.query_by_service(service_name)
        
        if not service:
            print(f"\n  Service '{service_name}' not found.")
            print(f"\n  Available services:")
            for name in sorted(self.manifest.services.keys()):
                print(f"    - {name}")
            return
        
        print(f"\n{'='*60}")
        print(f"  Service: {service.name}")
        print(f"{'='*60}\n")
        
        if what == "info" or what == "all":
            print(f"  Type: {service.service_type}")
            print(f"  Path: {service.path}")
            print(f"  Tags: {', '.join(service.tags)}")
            print(f"  Description: {service.description or 'N/A'}")
            print()
        
        if what == "depends-on" or what == "all":
            print(f"  Dependencies (services this depends on):")
            deps = self.manifest.get_dependencies(service_name)
            if deps:
                for dep in deps:
                    print(f"    -> {dep.name} [{dep.service_type}]")
            else:
                print(f"    (none)")
            print()
        
        if what == "dependents" or what == "all":
            print(f"  Dependents (services that depend on this):")
            dependents = self.manifest.get_dependents(service_name)
            if dependents:
                for dep in dependents:
                    print(f"    <- {dep.name} [{dep.service_type}]")
            else:
                print(f"    (none)")
            print()
        
        if what == "external" or what == "all":
            self._show_external_dependencies(service)
    
    def list_services(self) -> None:
        """List all services in the workspace."""
        print(f"\n{'='*60}")
        print(f"  Workspace: {self.manifest.name} (v{self.manifest.version})")
        print(f"  Root: {self.manifest.root}")
        print(f"{'='*60}\n")
        
        print(f"  Services ({len(self.manifest.services)}):\n")
        
        for name, service in sorted(self.manifest.services.items()):
            status = "✓" if service.exists() else "✗"
            tags_str = ", ".join(service.tags[:3])
            if len(service.tags) > 3:
                tags_str += f" +{len(service.tags) - 3} more"
            
            print(f"  {status} {name:20s} [{service.service_type:12s}] tags: {tags_str}")
        
        print()
        
        # Show all available tags
        all_tags = set()
        for s in self.manifest.services.values():
            all_tags.update(s.tags)
        
        print(f"  Available tags: {', '.join(sorted(all_tags))}")
        print()
    
    def validate_workspace(self) -> None:
        """Validate workspace configuration."""
        print(f"\n{'='*60}")
        print(f"  Workspace Validation: {self.manifest.name}")
        print(f"{'='*60}\n")
        
        issues = self.manifest.validate()
        
        if issues:
            print(f"  Found {len(issues)} issue(s):\n")
            for issue in issues:
                print(f"  ✗ {issue}")
        else:
            print(f"  ✓ All {len(self.manifest.services)} services validated successfully")
        
        # Check for context files
        print(f"\n  Context file status:\n")
        for name, service in sorted(self.manifest.services.items()):
            context_dir = service.path / ".llm-context"
            ext_deps = context_dir / "external-dependencies.json"
            
            if not service.exists():
                print(f"  ✗ {name:20s} - service path missing")
            elif not context_dir.exists():
                print(f"  ⚠ {name:20s} - no .llm-context/ (run: ccc generate)")
            elif not ext_deps.exists():
                print(f"  ⚠ {name:20s} - no external-dependencies.json")
            else:
                print(f"  ✓ {name:20s} - ready")
        
        print()
    
    def _get_change_hint(self, service: ServiceConfig) -> str:
        """Get a hint about what to change in this service."""
        hints = {
            "data": "update schema/config first",
            "database": "update schema/config first",
            "backend-api": "implement business logic",
            "api": "implement endpoints",
            "frontend": "update UI components",
            "library": "update shared types/utilities",
            "gateway": "update routing configuration",
        }
        return hints.get(service.service_type, "review and update")
    
    def _show_external_dependencies(self, service: ServiceConfig) -> None:
        """Show external dependencies from generated context."""
        ext_deps_file = service.path / ".llm-context" / "external-dependencies.json"
        
        if not ext_deps_file.exists():
            print(f"  External dependencies: (not generated)")
            print(f"    Run: cd {service.path} && ccc generate")
            return
        
        try:
            content = safe_read_text(ext_deps_file)
            if not content:
                return
            
            deps = json.loads(content)
            
            print(f"  External Dependencies (from code analysis):\n")
            
            if deps.get("exposes", {}).get("api"):
                print(f"    Exposes APIs:")
                for api in deps["exposes"]["api"][:10]:
                    print(f"      {api}")
                if len(deps["exposes"]["api"]) > 10:
                    print(f"      ... and {len(deps['exposes']['api']) - 10} more")
            
            if deps.get("depends_on", {}).get("services"):
                print(f"\n    Depends on services:")
                for svc in deps["depends_on"]["services"]:
                    print(f"      -> {svc}")
            
            if deps.get("depends_on", {}).get("databases"):
                print(f"\n    Databases:")
                for db in deps["depends_on"]["databases"]:
                    print(f"      - {db}")
            
            if deps.get("depends_on", {}).get("external_apis"):
                print(f"\n    Third-party APIs:")
                for api in deps["depends_on"]["external_apis"]:
                    print(f"      - {api}")
            
            print()
            
        except Exception as e:
            print(f"  Error reading external dependencies: {e}")
    
    def _generate_workspace_context(self, services: List[ServiceConfig]) -> None:
        """Generate cross-repo workspace context."""
        print(f"  Generating workspace context...")
        
        output_dir = self.manifest.root / "workspace-context"
        output_dir.mkdir(exist_ok=True)
        
        # Collect external dependencies from all services
        all_deps = {}
        for service in services:
            ext_deps_file = service.path / ".llm-context" / "external-dependencies.json"
            if ext_deps_file.exists():
                content = safe_read_text(ext_deps_file)
                if content:
                    all_deps[service.name] = json.loads(content)
        
        # Generate WORKSPACE.md
        self._generate_workspace_md(services, all_deps, output_dir)
        
        # Generate cross-repo API map
        self._generate_cross_repo_api(services, all_deps, output_dir)
        
        # Generate change sequence
        self._generate_change_sequence(services, output_dir)
        
        # Generate dependency graph (Mermaid)
        self._generate_dependency_graph(services, all_deps, output_dir)
        
        print(f"\n  Generated workspace context in: {output_dir}")
        print(f"    - WORKSPACE.md")
        print(f"    - cross-repo-api.txt")
        print(f"    - change-sequence.md")
        print(f"    - dependency-graph.md")
        print()
    
    def _generate_workspace_md(
        self,
        services: List[ServiceConfig],
        all_deps: Dict,
        output_dir: Path
    ) -> None:
        """Generate WORKSPACE.md overview."""
        lines = [
            f"# {self.manifest.name} — Workspace Context",
            "",
            f"Generated: {get_timestamp()}",
            "",
            "## Services in This Workspace",
            "",
            "| Service | Type | Tags | Dependencies |",
            "|---------|------|------|--------------|",
        ]
        
        for service in services:
            tags = ", ".join(service.tags[:3])
            deps = ", ".join(service.depends_on) if service.depends_on else "-"
            lines.append(f"| {service.name} | {service.service_type} | {tags} | {deps} |")
        
        lines.extend([
            "",
            "## How They Connect",
            "",
        ])
        
        # Show API connections
        connections = []
        for service in services:
            if service.name in all_deps:
                deps = all_deps[service.name]
                for consumed in deps.get("depends_on", {}).get("apis_consumed", []):
                    # Try to match to a service
                    for other in services:
                        if other.name in consumed or other.name.replace("-", "") in consumed:
                            connections.append(f"{service.name} -> {other.name}")
                            break
        
        if connections:
            lines.append("```")
            for conn in sorted(set(connections)):
                lines.append(conn)
            lines.append("```")
        else:
            lines.append("(No direct API connections detected)")
        
        lines.extend([
            "",
            "## Service Details",
            "",
        ])
        
        for service in services:
            lines.append(f"### {service.name}")
            lines.append("")
            lines.append(f"- **Type**: {service.service_type}")
            lines.append(f"- **Path**: `{service.path}`")
            lines.append(f"- **Tags**: {', '.join(service.tags)}")
            if service.description:
                lines.append(f"- **Description**: {service.description}")
            
            if service.name in all_deps:
                deps = all_deps[service.name]
                
                if deps.get("exposes", {}).get("api"):
                    lines.append("")
                    lines.append("**Exposes:**")
                    for api in deps["exposes"]["api"][:5]:
                        lines.append(f"- `{api}`")
                    if len(deps["exposes"]["api"]) > 5:
                        lines.append(f"- ... and {len(deps['exposes']['api']) - 5} more")
                
                if deps.get("depends_on", {}).get("databases"):
                    lines.append("")
                    lines.append("**Databases:**")
                    for db in deps["depends_on"]["databases"]:
                        lines.append(f"- {db}")
            
            lines.append("")
        
        content = "\n".join(lines)
        safe_write_text(output_dir / "WORKSPACE.md", content)
    
    def _generate_cross_repo_api(
        self,
        services: List[ServiceConfig],
        all_deps: Dict,
        output_dir: Path
    ) -> None:
        """Generate cross-repo API call map."""
        lines = [
            "# Cross-Repository API Calls",
            f"# Generated: {get_timestamp()}",
            "",
        ]
        
        for service in services:
            if service.name not in all_deps:
                continue
            
            deps = all_deps[service.name]
            consumed = deps.get("depends_on", {}).get("apis_consumed", [])
            
            if consumed:
                lines.append(f"## {service.name}")
                lines.append("")
                for api in consumed:
                    lines.append(f"  -> {api}")
                lines.append("")
        
        content = "\n".join(lines)
        safe_write_text(output_dir / "cross-repo-api.txt", content)
    
    def _generate_change_sequence(
        self,
        services: List[ServiceConfig],
        output_dir: Path
    ) -> None:
        """Generate change sequence based on dependencies."""
        ordered = self.manifest.get_dependency_order(services)
        
        lines = [
            "# Change Sequence",
            "",
            f"Generated: {get_timestamp()}",
            "",
            "Recommended order for implementing changes across services:",
            "",
        ]
        
        for i, service in enumerate(ordered, 1):
            lines.append(f"## {i}. {service.name}")
            lines.append("")
            lines.append(f"- **Type**: {service.service_type}")
            lines.append(f"- **Path**: `{service.path}`")
            
            if service.depends_on:
                lines.append(f"- **Depends on**: {', '.join(service.depends_on)}")
                lines.append("")
                lines.append("*Ensure the above services are updated first.*")
            else:
                lines.append("")
                lines.append("*No dependencies - can be updated first.*")
            
            lines.append("")
        
        content = "\n".join(lines)
        safe_write_text(output_dir / "change-sequence.md", content)
    
    def _generate_dependency_graph(
        self,
        services: List[ServiceConfig],
        all_deps: Dict,
        output_dir: Path
    ) -> None:
        """Generate Mermaid dependency graph."""
        lines = [
            "# Dependency Graph",
            "",
            "```mermaid",
            "graph TD",
        ]
        
        # Add service nodes
        for service in services:
            node_id = service.name.replace("-", "_")
            lines.append(f"  {node_id}[{service.name}]")
        
        lines.append("")
        
        # Add dependency edges
        edges_added = set()
        for service in services:
            node_id = service.name.replace("-", "_")
            
            # From workspace manifest dependencies
            for dep in service.depends_on:
                dep_id = dep.replace("-", "_")
                edge = f"{node_id} --> {dep_id}"
                if edge not in edges_added:
                    lines.append(f"  {edge}")
                    edges_added.add(edge)
            
            # From code-detected dependencies
            if service.name in all_deps:
                for svc in all_deps[service.name].get("depends_on", {}).get("services", []):
                    # Try to match to workspace services
                    for other in services:
                        if other.name in svc or svc in other.name:
                            other_id = other.name.replace("-", "_")
                            edge = f"{node_id} -.-> {other_id}"
                            if edge not in edges_added and node_id != other_id:
                                lines.append(f"  {edge}")
                                edges_added.add(edge)
        
        lines.extend([
            "```",
            "",
            "**Legend:**",
            "- Solid arrows (`-->`) = declared dependencies in workspace manifest",
            "- Dashed arrows (`-.->`) = detected from code analysis",
        ])
        
        content = "\n".join(lines)
        safe_write_text(output_dir / "dependency-graph.md", content)


def workspace_command(args) -> int:
    """Handle workspace subcommands."""
    workspace_file = Path(args.workspace) if hasattr(args, 'workspace') and args.workspace else None
    
    # Find workspace file
    if not workspace_file:
        for filename in ["ccc-workspace.yml", "ccc-workspace.yaml", "ccc-workspace.json"]:
            if Path(filename).exists():
                workspace_file = Path(filename)
                break
    
    if not workspace_file or not workspace_file.exists():
        print("\n  Error: No workspace file found.")
        print("\n  Create a ccc-workspace.yml file with your service configuration.")
        print("\n  Example:")
        print("    name: my-platform")
        print("    version: 1")
        print("    services:")
        print("      my-service:")
        print("        path: ./my-service")
        print("        type: backend-api")
        print("        tags: [api, core]")
        print()
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
    
    workspace_cmd = getattr(args, 'workspace_command', None)
    
    if workspace_cmd == "list":
        query.list_services()
    
    elif workspace_cmd == "query":
        tags = getattr(args, 'tags', None)
        service = getattr(args, 'service', None)
        what = getattr(args, 'what', 'all')
        generate = getattr(args, 'generate', False)
        
        if tags:
            query.query_tags(tags, generate_context=generate)
        elif service:
            query.query_service(service, what=what)
        else:
            print("\n  Error: Specify --tags or --service")
            return 1
    
    elif workspace_cmd == "validate":
        query.validate_workspace()
    
    elif workspace_cmd == "generate":
        tags = getattr(args, 'tags', None)
        services = manifest.query_by_tags(tags) if tags else list(manifest.services.values())
        query._generate_workspace_context(services)
    
    elif workspace_cmd == "conflicts" or workspace_cmd == "doctor":
        # Conflict detection
        tags = getattr(args, 'tags', None)
        output = getattr(args, 'output', None)
        
        services = manifest.query_by_tags(tags) if tags else list(manifest.services.values())
        
        detector = ConflictDetector(manifest)
        conflicts = detector.analyze(services)
        
        detector.print_summary()
        
        # Generate report
        output_dir = Path(output) if output else manifest.root / "workspace-context"
        report = detector.generate_report(output_dir)
        
        print(f"  Report saved to: {output_dir / 'conflicts-report.md'}")
        
        # Return error code if errors found
        errors = [c for c in conflicts if c.severity == "error"]
        if errors:
            return 1
    
    else:
        print("\n  Error: Unknown workspace command")
        print("\n  Available commands:")
        print("    workspace list              - List all services")
        print("    workspace query --tags X    - Find services by tags")
        print("    workspace query --service X - Get service details")
        print("    workspace validate          - Validate workspace")
        print("    workspace generate          - Generate workspace context")
        print("    workspace conflicts         - Detect cross-repo conflicts")
        return 1
    
    return 0
def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="LLM Context Generator - Generate context files for LLMs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single repository mode
  python llm-context-setup.py                    # Full generation
  python llm-context-setup.py --quick-update     # Fast incremental update
  python llm-context-setup.py --force            # Force full regeneration
  python llm-context-setup.py --watch            # Watch mode
  python llm-context-setup.py --doctor           # Run diagnostics

  # Workspace mode (multi-repo)
  python llm-context-setup.py workspace list
  python llm-context-setup.py workspace query --tags api
  python llm-context-setup.py workspace query --service auth-service --what all
  python llm-context-setup.py workspace validate
  python llm-context-setup.py workspace generate
        """,
    )
    
    subparsers = parser.add_subparsers(dest="command")
    
    # ─────────────────────────────────────────
    # Workspace subcommand
    # ─────────────────────────────────────────
    workspace_parser = subparsers.add_parser(
        "workspace",
        help="Multi-repository workspace commands"
    )
    workspace_parser.add_argument(
        "--workspace", "-w",
        help="Path to ccc-workspace.yml file"
    )
    
    workspace_subparsers = workspace_parser.add_subparsers(dest="workspace_command")
    
    # workspace list
    workspace_subparsers.add_parser("list", help="List all services in workspace")
    
    # workspace query
    query_parser = workspace_subparsers.add_parser("query", help="Query services")
    query_parser.add_argument("--tags", "-t", nargs="+", help="Filter by tags")
    query_parser.add_argument("--service", "-s", help="Query specific service")
    query_parser.add_argument(
        "--what",
        choices=["info", "depends-on", "dependents", "external", "all"],
        default="all",
        help="What information to show"
    )
    query_parser.add_argument(
        "--generate", "-g",
        action="store_true",
        help="Generate workspace context for matched services"
    )
    
    # workspace validate
    workspace_subparsers.add_parser("validate", help="Validate workspace configuration")
    
    # workspace generate
    gen_parser = workspace_subparsers.add_parser("generate", help="Generate workspace context")
    gen_parser.add_argument("--tags", "-t", nargs="+", help="Filter services by tags")
    
    # workspace conflicts (NEW)
    conflicts_parser = workspace_subparsers.add_parser(
        "conflicts",
        help="Detect cross-repo conflicts and inconsistencies"
    )
    conflicts_parser.add_argument("--tags", "-t", nargs="+", help="Filter services by tags")
    conflicts_parser.add_argument("--output", "-o", help="Output directory for report")
    
    # workspace doctor (alias for conflicts)
    doctor_ws_parser = workspace_subparsers.add_parser(
        "doctor",
        help="Check workspace health (alias for conflicts)"
    )
    doctor_ws_parser.add_argument("--tags", "-t", nargs="+", help="Filter services by tags")
    doctor_ws_parser.add_argument("--output", "-o", help="Output directory for report")
    
    # ─────────────────────────────────────────
    # Single-repo arguments (default command)
    # ─────────────────────────────────────────
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to project root (default: current directory)"
    )
    parser.add_argument(
        "--quick-update", "-q",
        action="store_true",
        help="Fast incremental update"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force full regeneration"
    )
    parser.add_argument(
        "--watch", "-w",
        action="store_true",
        help="Watch for file changes and auto-update"
    )
    parser.add_argument(
        "--with-summaries",
        action="store_true",
        help="Generate LLM-powered module summaries"
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run diagnostics"
    )
    parser.add_argument(
        "--security-status",
        action="store_true",
        help="Show security configuration"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output directory"
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to config file"
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"llm-context-setup {VERSION}"
    )
    
    args = parser.parse_args()
    
    # ─────────────────────────────────────────
    # Handle workspace command
    # ─────────────────────────────────────────
    if args.command == "workspace":
        sys.exit(workspace_command(args))
    
    # ─────────────────────────────────────────
    # Handle single-repo commands
    # ─────────────────────────────────────────
    root = Path(args.path).resolve()
    
    if args.doctor:
        tool = DiagnosticTool(root)
        tool.run()
        return
    
    if args.config:
        config_path = Path(args.config)
        if config_path.suffix in (".yml", ".yaml"):
            try:
                import yaml
                content = safe_read_text(config_path)
                if content:
                    config = get_default_config()
                    user_config = yaml.safe_load(content)
                    deep_merge(config, user_config)
                else:
                    config = get_default_config()
            except ImportError:
                print("  YAML config requires: pip install pyyaml")
                sys.exit(1)
        else:
            content = safe_read_text(config_path)
            if content:
                config = get_default_config()
                user_config = json.loads(content)
                deep_merge(config, user_config)
            else:
                config = get_default_config()
    else:
        config = load_config(root)
    
    if args.output:
        config["output_dir"] = args.output
    
    if args.with_summaries:
        config["generate"]["module_summaries"] = True
        if config.get("security", {}).get("mode") == "offline":
            config["security"]["mode"] = "public-ai"
    
    if args.security_status:
        security = SecurityManager(root, config)
        security.print_status()
        return
    
    if args.watch:
        watch_mode(root, config)
        return
    
    generator = LLMContextGenerator(
        root=root,
        config=config,
        quick_mode=args.quick_update,
        force=args.force,
    )
    generator.generate()

# ──────────────────────────────────────────────
# Cross-Repo Conflict Detection (Phase 4)
# ──────────────────────────────────────────────

@dataclass
class Conflict:
    """Represents an inconsistency between services."""
    conflict_type: str
    severity: str  # "error", "warning", "info"
    symbol: str
    services: List[str]
    details: str
    locations: List[str] = field(default_factory=list)
    suggestion: str = ""


@dataclass
class TypeDefinition:
    """Represents an extracted type definition."""
    name: str
    kind: str  # "enum", "interface", "type", "class", "constant"
    service: str
    file: str
    fields: List[str] = field(default_factory=list)
    values: List[str] = field(default_factory=list)
    raw_source: str = ""


class ConflictDetector:
    """Detect inconsistencies across multiple services."""
    
    def __init__(self, manifest: WorkspaceManifest):
        self.manifest = manifest
        self.type_definitions: Dict[str, List[TypeDefinition]] = {}
        self.api_contracts: Dict[str, Dict] = {}
        self.conflicts: List[Conflict] = []
    
    def analyze(self, services: List[ServiceConfig] = None) -> List[Conflict]:
        """
        Analyze services for conflicts.
        
        Returns list of detected conflicts.
        """
        if services is None:
            services = list(self.manifest.services.values())
        
        self.conflicts = []
        self.type_definitions = {}
        self.api_contracts = {}
        
        print(f"\n  Analyzing {len(services)} services for conflicts...")
        
        # Step 1: Extract type definitions from all services
        for service in services:
            print(f"    Scanning {service.name}...")
            self._extract_types_from_service(service)
            self._load_external_deps(service)
        
        # Step 2: Detect various conflict types
        print(f"\n  Checking for conflicts...")
        
        self._detect_enum_conflicts()
        self._detect_interface_conflicts()
        self._detect_constant_conflicts()
        self._detect_api_contract_mismatches(services)
        self._detect_event_mismatches(services)
        self._detect_naming_inconsistencies()
        
        # Sort by severity
        severity_order = {"error": 0, "warning": 1, "info": 2}
        self.conflicts.sort(key=lambda c: severity_order.get(c.severity, 99))
        
        return self.conflicts
    
    def _extract_types_from_service(self, service: ServiceConfig) -> None:
        """Extract type definitions from a service's source code."""
        if not service.exists():
            return
        
        # Extract from TypeScript files
        self._extract_typescript_types(service)
        
        # Extract from Python files
        self._extract_python_types(service)
    
    def _extract_typescript_types(self, service: ServiceConfig) -> None:
        """Extract TypeScript type definitions."""
        
        # Patterns for different type definitions
        enum_pattern = re.compile(
            r'(?:export\s+)?enum\s+(\w+)\s*\{([^}]+)\}',
            re.MULTILINE | re.DOTALL
        )
        
        interface_pattern = re.compile(
            r'(?:export\s+)?interface\s+(\w+)(?:\s+extends\s+[\w,\s]+)?\s*\{([^}]+)\}',
            re.MULTILINE | re.DOTALL
        )
        
        type_pattern = re.compile(
            r'(?:export\s+)?type\s+(\w+)\s*=\s*(\{[^}]+\}|[^;]+);',
            re.MULTILINE
        )
        
        const_pattern = re.compile(
            r'(?:export\s+)?const\s+([A-Z][A-Z0-9_]+)\s*(?::\s*\w+)?\s*=\s*([^;]+);',
            re.MULTILINE
        )
        
        for ts_file in service.path.rglob("*.ts"):
            if should_skip_path(ts_file):
                continue
            
            content = safe_read_text(ts_file)
            if not content:
                continue
            
            rel_path = str(ts_file.relative_to(service.path))
            
            # Extract enums
            for match in enum_pattern.finditer(content):
                name = match.group(1)
                body = match.group(2)
                
                # Parse enum values
                values = []
                for line in body.split('\n'):
                    line = line.strip().rstrip(',')
                    if line and not line.startswith('//'):
                        # Handle both `VALUE = "value"` and `VALUE`
                        value_match = re.match(r'(\w+)(?:\s*=\s*["\']?([^"\']+)["\']?)?', line)
                        if value_match:
                            values.append(value_match.group(1))
                
                type_def = TypeDefinition(
                    name=name,
                    kind="enum",
                    service=service.name,
                    file=rel_path,
                    values=values,
                    raw_source=match.group(0)[:200]
                )
                
                self._add_type_definition(name, type_def)
            
            # Extract interfaces
            for match in interface_pattern.finditer(content):
                name = match.group(1)
                body = match.group(2)
                
                # Parse fields
                fields = []
                for line in body.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('//'):
                        # Extract field name
                        field_match = re.match(r'(\w+)\??:', line)
                        if field_match:
                            fields.append(field_match.group(1))
                
                type_def = TypeDefinition(
                    name=name,
                    kind="interface",
                    service=service.name,
                    file=rel_path,
                    fields=sorted(fields),
                    raw_source=match.group(0)[:300]
                )
                
                self._add_type_definition(name, type_def)
            
            # Extract type aliases
            for match in type_pattern.finditer(content):
                name = match.group(1)
                body = match.group(2)
                
                # Skip simple aliases
                if '{' in body:
                    fields = []
                    for field_match in re.finditer(r'(\w+)\??:', body):
                        fields.append(field_match.group(1))
                    
                    type_def = TypeDefinition(
                        name=name,
                        kind="type",
                        service=service.name,
                        file=rel_path,
                        fields=sorted(fields),
                        raw_source=match.group(0)[:200]
                    )
                    
                    self._add_type_definition(name, type_def)
            
            # Extract constants
            for match in const_pattern.finditer(content):
                name = match.group(1)
                value = match.group(2).strip().strip('"').strip("'")
                
                type_def = TypeDefinition(
                    name=name,
                    kind="constant",
                    service=service.name,
                    file=rel_path,
                    values=[value],
                    raw_source=f"const {name} = {value}"
                )
                
                self._add_type_definition(name, type_def)
    
    def _extract_python_types(self, service: ServiceConfig) -> None:
        """Extract Python type definitions."""
        
        for py_file in service.path.rglob("*.py"):
            if should_skip_path(py_file):
                continue
            
            content = safe_read_text(py_file)
            if not content:
                continue
            
            rel_path = str(py_file.relative_to(service.path))
            
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Check if it's an Enum
                    base_names = []
                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            base_names.append(base.id)
                        elif isinstance(base, ast.Attribute):
                            base_names.append(base.attr)
                    
                    if 'Enum' in base_names or 'IntEnum' in base_names or 'StrEnum' in base_names:
                        # Extract enum values
                        values = []
                        for item in node.body:
                            if isinstance(item, ast.Assign):
                                for target in item.targets:
                                    if isinstance(target, ast.Name):
                                        values.append(target.id)
                        
                        type_def = TypeDefinition(
                            name=node.name,
                            kind="enum",
                            service=service.name,
                            file=rel_path,
                            values=values
                        )
                        self._add_type_definition(node.name, type_def)
                    
                    elif 'BaseModel' in base_names or 'TypedDict' in base_names:
                        # Extract fields from Pydantic model or TypedDict
                        fields = []
                        for item in node.body:
                            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                                fields.append(item.target.id)
                        
                        type_def = TypeDefinition(
                            name=node.name,
                            kind="interface",
                            service=service.name,
                            file=rel_path,
                            fields=sorted(fields)
                        )
                        self._add_type_definition(node.name, type_def)
                
                # Extract module-level constants
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id.isupper():
                            # It's a constant (all uppercase)
                            try:
                                value = ast.literal_eval(node.value)
                                if isinstance(value, (str, int, float, bool)):
                                    type_def = TypeDefinition(
                                        name=target.id,
                                        kind="constant",
                                        service=service.name,
                                        file=rel_path,
                                        values=[str(value)]
                                    )
                                    self._add_type_definition(target.id, type_def)
                            except (ValueError, TypeError):
                                pass
    
    def _add_type_definition(self, name: str, type_def: TypeDefinition) -> None:
        """Add a type definition to the registry."""
        if name not in self.type_definitions:
            self.type_definitions[name] = []
        self.type_definitions[name].append(type_def)
    
    def _load_external_deps(self, service: ServiceConfig) -> None:
        """Load external dependencies from generated context."""
        ext_deps_file = service.path / ".llm-context" / "external-dependencies.json"
        
        if ext_deps_file.exists():
            content = safe_read_text(ext_deps_file)
            if content:
                try:
                    self.api_contracts[service.name] = json.loads(content)
                except json.JSONDecodeError:
                    pass
    
    def _detect_enum_conflicts(self) -> None:
        """Detect enum definitions with mismatched values."""
        for name, definitions in self.type_definitions.items():
            enums = [d for d in definitions if d.kind == "enum"]
            
            if len(enums) < 2:
                continue
            
            # Check if all enums have the same values
            value_sets = [frozenset(e.values) for e in enums]
            unique_value_sets = set(value_sets)
            
            if len(unique_value_sets) > 1:
                # Conflict found!
                services = [e.service for e in enums]
                locations = [f"{e.service}:{e.file}" for e in enums]
                
                # Build detailed message
                details_parts = []
                for enum in enums:
                    values_str = ", ".join(enum.values[:5])
                    if len(enum.values) > 5:
                        values_str += f" +{len(enum.values) - 5} more"
                    details_parts.append(f"{enum.service}: [{values_str}]")
                
                details = "\n      ".join(details_parts)
                
                # Find missing values
                all_values = set()
                for e in enums:
                    all_values.update(e.values)
                
                suggestions = []
                for enum in enums:
                    missing = all_values - set(enum.values)
                    if missing:
                        suggestions.append(f"Add {missing} to {enum.service}")
                
                conflict = Conflict(
                    conflict_type="enum_mismatch",
                    severity="error",
                    symbol=name,
                    services=services,
                    details=f"Enum '{name}' has different values:\n      {details}",
                    locations=locations,
                    suggestion="; ".join(suggestions) if suggestions else "Synchronize enum values across services"
                )
                self.conflicts.append(conflict)
    
    def _detect_interface_conflicts(self) -> None:
        """Detect interface/type definitions with mismatched fields."""
        for name, definitions in self.type_definitions.items():
            interfaces = [d for d in definitions if d.kind in ["interface", "type"]]
            
            if len(interfaces) < 2:
                continue
            
            # Skip common generic names
            if name in ["Props", "State", "Config", "Options", "Context", "Request", "Response"]:
                continue
            
            # Check if all interfaces have the same fields
            field_sets = [frozenset(i.fields) for i in interfaces]
            unique_field_sets = set(field_sets)
            
            if len(unique_field_sets) > 1:
                services = [i.service for i in interfaces]
                locations = [f"{i.service}:{i.file}" for i in interfaces]
                
                # Build detailed message
                details_parts = []
                for interface in interfaces:
                    fields_str = ", ".join(interface.fields[:5])
                    if len(interface.fields) > 5:
                        fields_str += f" +{len(interface.fields) - 5} more"
                    details_parts.append(f"{interface.service}: [{fields_str}]")
                
                details = "\n      ".join(details_parts)
                
                # Find field differences
                all_fields = set()
                for i in interfaces:
                    all_fields.update(i.fields)
                
                common_fields = set.intersection(*[set(i.fields) for i in interfaces])
                different_fields = all_fields - common_fields
                
                conflict = Conflict(
                    conflict_type="interface_mismatch",
                    severity="warning",
                    symbol=name,
                    services=services,
                    details=f"Type '{name}' has different fields:\n      {details}",
                    locations=locations,
                    suggestion=f"Inconsistent fields: {different_fields}. Consider creating a shared types package."
                )
                self.conflicts.append(conflict)
    
    def _detect_constant_conflicts(self) -> None:
        """Detect constants with mismatched values."""
        for name, definitions in self.type_definitions.items():
            constants = [d for d in definitions if d.kind == "constant"]
            
            if len(constants) < 2:
                continue
            
            # Check if all constants have the same value
            values = [c.values[0] if c.values else "" for c in constants]
            unique_values = set(values)
            
            if len(unique_values) > 1:
                services = [c.service for c in constants]
                locations = [f"{c.service}:{c.file}" for c in constants]
                
                details_parts = [f"{c.service}: {c.values[0] if c.values else 'undefined'}" for c in constants]
                details = "\n      ".join(details_parts)
                
                conflict = Conflict(
                    conflict_type="constant_mismatch",
                    severity="warning",
                    symbol=name,
                    services=services,
                    details=f"Constant '{name}' has different values:\n      {details}",
                    locations=locations,
                    suggestion="Centralize this constant in a shared configuration or types package"
                )
                self.conflicts.append(conflict)
    
    def _detect_api_contract_mismatches(self, services: List[ServiceConfig]) -> None:
        """Detect API contract mismatches between services."""
        # Build map of exposed APIs
        exposed_apis: Dict[str, List[Tuple[str, str]]] = {}  # route -> [(service, method)]
        
        # Build map of consumed APIs
        consumed_apis: Dict[str, List[Tuple[str, str]]] = {}  # service -> [apis]
        
        for service in services:
            if service.name not in self.api_contracts:
                continue
            
            contract = self.api_contracts[service.name]
            
            # Collect exposed APIs
            for api in contract.get("exposes", {}).get("api", []):
                # Normalize route
                parts = api.split(" ", 1)
                if len(parts) == 2:
                    method, route = parts
                else:
                    method, route = "GET", parts[0]
                
                # Normalize route (remove path params formatting differences)
                normalized = self._normalize_route(route)
                
                if normalized not in exposed_apis:
                    exposed_apis[normalized] = []
                exposed_apis[normalized].append((service.name, method))
            
            # Collect consumed APIs
            consumed_apis[service.name] = []
            for api in contract.get("depends_on", {}).get("apis_consumed", []):
                consumed_apis[service.name].append(api)
        
        # Check for mismatches
        for consumer, apis in consumed_apis.items():
            for api in apis:
                # Parse consumed API
                parts = api.split(" ", 1)
                if len(parts) == 2:
                    method, url = parts
                else:
                    continue
                
                # Extract route from URL
                route_match = re.search(r'https?://[^/]+(/[^\s?#]*)', url)
                if not route_match:
                    continue
                
                route = route_match.group(1)
                normalized = self._normalize_route(route)
                
                # Check if any service exposes this
                if normalized not in exposed_apis:
                    # Check for similar routes
                    similar = self._find_similar_routes(normalized, exposed_apis.keys())
                    
                    if similar:
                        conflict = Conflict(
                            conflict_type="api_route_mismatch",
                            severity="warning",
                            symbol=route,
                            services=[consumer],
                            details=f"Service '{consumer}' calls '{api}' but route not found.\n      Similar routes: {similar}",
                            suggestion=f"Check if the route should be '{similar[0]}' instead"
                        )
                        self.conflicts.append(conflict)
    
    def _detect_event_mismatches(self, services: List[ServiceConfig]) -> None:
        """Detect event naming mismatches."""
        # Collect all events
        published_events: Dict[str, str] = {}  # event -> service
        subscribed_events: Dict[str, str] = {}  # event -> service
        
        for service in services:
            if service.name not in self.api_contracts:
                continue
            
            contract = self.api_contracts[service.name]
            
            # Published events
            for event in contract.get("exposes", {}).get("events", []):
                published_events[event] = service.name
            
            # Subscribed events (from external dependencies)
            # This would need more sophisticated detection
        
        # Check for naming convention mismatches
        event_patterns = {}
        for event in published_events.keys():
            # Detect pattern: dot.notation vs camelCase vs snake_case
            if '.' in event:
                pattern = "dot.notation"
            elif '_' in event:
                pattern = "snake_case"
            elif event[0].islower() and any(c.isupper() for c in event):
                pattern = "camelCase"
            else:
                pattern = "other"
            
            if pattern not in event_patterns:
                event_patterns[pattern] = []
            event_patterns[pattern].append((event, published_events[event]))
        
        # If multiple patterns detected, warn
        if len(event_patterns) > 1:
            details_parts = []
            for pattern, events in event_patterns.items():
                event_names = [e[0] for e in events[:3]]
                details_parts.append(f"{pattern}: {event_names}")
            
            details = "\n      ".join(details_parts)
            
            conflict = Conflict(
                conflict_type="event_naming_inconsistency",
                severity="info",
                symbol="event_naming",
                services=list(published_events.values()),
                details=f"Inconsistent event naming conventions:\n      {details}",
                suggestion="Consider standardizing on one event naming convention (e.g., dot.notation like 'user.created')"
            )
            self.conflicts.append(conflict)
    
    def _detect_naming_inconsistencies(self) -> None:
        """Detect similar names that might be the same thing."""
        # Group by lowercase name
        name_groups: Dict[str, List[TypeDefinition]] = {}
        
        for name, definitions in self.type_definitions.items():
            lower_name = name.lower()
            if lower_name not in name_groups:
                name_groups[lower_name] = []
            name_groups[lower_name].extend(definitions)
        
        # Find groups with different casing
        for lower_name, definitions in name_groups.items():
            unique_names = set(d.name for d in definitions)
            
            if len(unique_names) > 1:
                services = list(set(d.service for d in definitions))
                
                conflict = Conflict(
                    conflict_type="naming_inconsistency",
                    severity="info",
                    symbol=lower_name,
                    services=services,
                    details=f"Inconsistent casing for '{lower_name}': {unique_names}",
                    suggestion="Standardize naming across services"
                )
                self.conflicts.append(conflict)
    
    def _normalize_route(self, route: str) -> str:
        """Normalize a route for comparison."""
        # Remove trailing slashes
        route = route.rstrip('/')
        
        # Normalize path parameters
        # Convert {param}, :param, [param] all to {param}
        route = re.sub(r':(\w+)', r'{\1}', route)
        route = re.sub(r'\[(\w+)\]', r'{\1}', route)
        
        return route.lower()
    
    def _find_similar_routes(self, route: str, existing_routes: List[str]) -> List[str]:
        """Find routes similar to the given route."""
        similar = []
        
        route_parts = route.split('/')
        
        for existing in existing_routes:
            existing_parts = existing.split('/')
            
            # Same number of segments
            if len(route_parts) != len(existing_parts):
                continue
            
            # Count matching segments
            matches = 0
            for a, b in zip(route_parts, existing_parts):
                if a == b or '{' in a or '{' in b:
                    matches += 1
            
            # If most segments match, consider it similar
            if matches >= len(route_parts) - 1:
                similar.append(existing)
        
        return similar
    
    def generate_report(self, output_dir: Path = None) -> str:
        """Generate a conflicts report."""
        lines = [
            "# Cross-Repository Conflict Report",
            "",
            f"Generated: {get_timestamp()}",
            f"Services analyzed: {len(self.manifest.services)}",
            f"Conflicts found: {len(self.conflicts)}",
            "",
        ]
        
        if not self.conflicts:
            lines.extend([
                "## ✅ No Conflicts Detected",
                "",
                "All analyzed services appear to be consistent.",
            ])
        else:
            # Group by severity
            errors = [c for c in self.conflicts if c.severity == "error"]
            warnings = [c for c in self.conflicts if c.severity == "warning"]
            infos = [c for c in self.conflicts if c.severity == "info"]
            
            lines.extend([
                "## Summary",
                "",
                f"- 🔴 Errors: {len(errors)}",
                f"- 🟡 Warnings: {len(warnings)}",
                f"- 🔵 Info: {len(infos)}",
                "",
            ])
            
            if errors:
                lines.extend([
                    "## 🔴 Errors",
                    "",
                    "These conflicts should be fixed before deploying:",
                    "",
                ])
                for conflict in errors:
                    lines.extend(self._format_conflict(conflict))
            
            if warnings:
                lines.extend([
                    "## 🟡 Warnings",
                    "",
                    "These inconsistencies may cause issues:",
                    "",
                ])
                for conflict in warnings:
                    lines.extend(self._format_conflict(conflict))
            
            if infos:
                lines.extend([
                    "## 🔵 Info",
                    "",
                    "Potential improvements:",
                    "",
                ])
                for conflict in infos:
                    lines.extend(self._format_conflict(conflict))
        
        content = "\n".join(lines)
        
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            safe_write_text(output_dir / "conflicts-report.md", content)
        
        return content
    
    def _format_conflict(self, conflict: Conflict) -> List[str]:
        """Format a single conflict for the report."""
        lines = [
            f"### {conflict.conflict_type}: `{conflict.symbol}`",
            "",
            f"**Services:** {', '.join(conflict.services)}",
            "",
            f"**Details:**",
            f"```",
            conflict.details,
            f"```",
            "",
        ]
        
        if conflict.locations:
            lines.append(f"**Locations:** {', '.join(conflict.locations)}")
            lines.append("")
        
        if conflict.suggestion:
            lines.append(f"**Suggestion:** {conflict.suggestion}")
            lines.append("")
        
        lines.append("---")
        lines.append("")
        
        return lines
    
    def print_summary(self) -> None:
        """Print a summary of detected conflicts."""
        print(f"\n{'='*60}")
        print(f"  Conflict Detection Results")
        print(f"{'='*60}")
        
        if not self.conflicts:
            print(f"\n  ✅ No conflicts detected!")
            print(f"\n  All {len(self.manifest.services)} services appear to be consistent.")
        else:
            errors = [c for c in self.conflicts if c.severity == "error"]
            warnings = [c for c in self.conflicts if c.severity == "warning"]
            infos = [c for c in self.conflicts if c.severity == "info"]
            
            print(f"\n  Found {len(self.conflicts)} issue(s):")
            print(f"    🔴 Errors: {len(errors)}")
            print(f"    🟡 Warnings: {len(warnings)}")
            print(f"    🔵 Info: {len(infos)}")
            
            if errors:
                print(f"\n  Errors (fix these first):")
                for conflict in errors[:5]:
                    print(f"    • {conflict.conflict_type}: {conflict.symbol}")
                    print(f"      Services: {', '.join(conflict.services)}")
                if len(errors) > 5:
                    print(f"    ... and {len(errors) - 5} more")
            
            if warnings:
                print(f"\n  Warnings:")
                for conflict in warnings[:5]:
                    print(f"    • {conflict.conflict_type}: {conflict.symbol}")
                if len(warnings) > 5:
                    print(f"    ... and {len(warnings) - 5} more")
        
        print(f"\n{'='*60}\n")

if __name__ == "__main__":
    main()
