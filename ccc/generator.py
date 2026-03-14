"""
Main context generator orchestrator.

Coordinates all extractors and generators to produce the full
.llm-context/ output for a single repository.
"""

import json
import subprocess
from pathlib import Path
from typing import Optional

from .config import load_config
from .manifest import SmartUpdater
from .models import ProjectInfo
from .security.manager import SecurityManager
from .generators.tree import TreeGenerator
from .generators.schemas import SchemaGenerator
from .generators.api import APIGenerator
from .generators.dependencies import DependencyGenerator
from .utils.files import safe_read_text, safe_write_text, should_skip_path, EXCLUDE_DIRS
from .utils.formatting import human_readable_size

try:
    from . import VERSION
except ImportError:
    VERSION = "0.1.0"


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
        info = ProjectInfo(root=self.root)
        info.name = self.root.name
        info.languages = self._detect_languages()
        self._detect_from_configs(info)
        info.framework = self._detect_framework()
        info.has_docker = self._has_docker()
        info.has_ci = self._has_ci()
        info.has_tests = self._has_tests()
        return info

    def _detect_languages(self):
        import os

        extensions = {}

        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]

            for filename in filenames:
                filepath = Path(dirpath) / filename

                if not should_skip_path(filepath):
                    ext = filepath.suffix.lower()
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

        for ext, count in sorted(extensions.items(), key=lambda x: -x[1]):
            if ext in lang_map and count >= 2:
                lang = lang_map[ext]

                if lang not in langs:
                    langs.append(lang)

        return langs[:5]

    def _detect_from_configs(self, info: ProjectInfo) -> None:
        import re

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
        import os

        content_sample = ""
        count = 0

        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]

            for filename in filenames:
                if count >= 50:
                    break

                filepath = Path(dirpath) / filename

                if should_skip_path(filepath):
                    continue

                try:
                    if filepath.stat().st_size < 50000:
                        text = safe_read_text(filepath)

                        if text:
                            content_sample += text
                            count += 1

                except Exception:
                    continue

        for dep_file in [
            "requirements.txt",
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
            "go.mod",
        ]:
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