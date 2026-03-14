"""Database schema extractor — SQLAlchemy, Django ORM, Prisma."""
import ast
from pathlib import Path
from typing import List, Optional, Tuple

from .base import BaseGenerator
from ..file_index import FileIndex
from ..utils.files import safe_read_text


class DatabaseSchemaGenerator(BaseGenerator):
    """Extract database schema from ORM models and schema files."""

    def __init__(self, root: Path, config: dict, file_index: FileIndex):
        super().__init__(root, config)
        self.index = file_index

    @property
    def output_filename(self) -> str:
        return "db-schema.txt"

    def generate(self) -> Tuple[str, List[Path]]:
        result = self._from_prisma()
        if result:
            return result

        result = self._from_sqlalchemy()
        if result:
            return result

        result = self._from_django()
        if result:
            return result

        return "", []

    # ── Prisma ────────────────────────────────────────────────────────────────

    def _from_prisma(self) -> Optional[Tuple[str, List[Path]]]:
        prisma_schema = self.root / "prisma" / "schema.prisma"
        if not prisma_schema.exists():
            return None
        content = safe_read_text(prisma_schema)
        if not content:
            return None
        output = f"# Database Schema (Prisma)\n\n```prisma\n{content}\n```"
        return output, [prisma_schema]

    # ── SQLAlchemy ────────────────────────────────────────────────────────────

    def _from_sqlalchemy(self) -> Optional[Tuple[str, List[Path]]]:
        model_files = [
            fi for fi in self.index.by_extension(".py")
            if "model" in fi.path.name.lower()
        ]

        found = []
        for fi in model_files:
            content = safe_read_text(fi.path)
            if content and ("from sqlalchemy" in content or "declarative_base" in content):
                found.append((fi.path, content))

        if not found:
            return None

        lines = ["# Database Schema (SQLAlchemy models)", ""]
        source_files: List[Path] = []

        for model_file, content in found:
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue

                has_tablename = any(
                    isinstance(item, ast.Assign)
                    and any(
                        isinstance(t, ast.Name) and t.id == "__tablename__"
                        for t in item.targets
                    )
                    for item in node.body
                )
                has_base = any(
                    isinstance(b, ast.Name) and "Base" in b.id
                    for b in node.bases
                )

                if has_tablename or has_base:
                    source_files.append(model_file)
                    rel = model_file.relative_to(self.root)
                    lines.append(f"\n## {rel} — {node.name}")
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            try:
                                src = ast.unparse(item)
                                if "Column(" in src or "relationship(" in src:
                                    lines.append(f"  {src}")
                            except Exception:
                                pass

        if not source_files:
            return None

        return "\n".join(lines), list(set(source_files))

    # ── Django ────────────────────────────────────────────────────────────────

    def _from_django(self) -> Optional[Tuple[str, List[Path]]]:
        model_files = [
            fi for fi in self.index.by_extension(".py")
            if fi.path.name == "models.py"
        ]

        found = []
        for fi in model_files:
            content = safe_read_text(fi.path)
            if content and "models.Model" in content:
                found.append((fi.path, content))

        if not found:
            return None

        lines = ["# Database Schema (Django models)", ""]
        source_files: List[Path] = []

        for model_file, content in found:
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                is_model = any(
                    (isinstance(b, ast.Attribute) and b.attr == "Model") or
                    (isinstance(b, ast.Name) and "Model" in b.id)
                    for b in node.bases
                )
                if not is_model:
                    continue

                source_files.append(model_file)
                rel = model_file.relative_to(self.root)
                lines.append(f"\n## {rel} — {node.name}")
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        try:
                            src = ast.unparse(item)
                            if "Field(" in src:
                                lines.append(f"  {src}")
                        except Exception:
                            pass

        if not source_files:
            return None

        return "\n".join(lines), list(set(source_files))
