"""
Rust language extractor.

Extracts from Rust source using regex (no external parser required):
  - Public function signatures (pub fn)
  - Public struct, enum, and trait definitions
  - HTTP route macros for actix-web and axum
  - Cargo.toml crate name and direct dependencies

Design: Rust's `pub` keyword is a reliable visibility marker. We extract
pub items only — implementation details stay private. Route macros
(#[get("/path")]) are highly regular and parse cleanly with regex.
"""

import re
import tomllib
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .base import BaseExtractor, ExtractionResult, ExtractedSymbol
from ..utils.files import safe_read_text, should_skip_path


# ── Patterns ──────────────────────────────────────────────────────────────────

# pub fn function_name<T>(args) -> ReturnType
_PUB_FN = re.compile(
    r"^(?:pub(?:\s*\([^)]*\))?\s+)?(?:async\s+)?pub(?:\s*\([^)]*\))?\s+fn\s+(\w+)\s*"
    r"(?:<[^>]*>)?\s*\(([^)]*)\)\s*(?:->\s*([^\n{;]+))?",
    re.MULTILINE,
)

# Simpler fallback for pub fn
_PUB_FN_SIMPLE = re.compile(
    r"^\s*pub(?:\s*\(\w+\))?\s+(?:async\s+)?fn\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*([^{;\n]+))?",
    re.MULTILINE,
)

# pub struct / pub enum / pub trait
_PUB_STRUCT = re.compile(r"^\s*pub(?:\s*\(\w+\))?\s+struct\s+(\w+)", re.MULTILINE)
_PUB_ENUM   = re.compile(r"^\s*pub(?:\s*\(\w+\))?\s+enum\s+(\w+)",   re.MULTILINE)
_PUB_TRAIT  = re.compile(r"^\s*pub(?:\s*\(\w+\))?\s+trait\s+(\w+)",  re.MULTILINE)

# impl blocks — for associating methods with types
_IMPL_BLOCK = re.compile(r"^\s*impl(?:<[^>]*>)?\s+(\w+)", re.MULTILINE)

# actix-web route macros: #[get("/path")]  #[post("/path")]
_ACTIX_ROUTE = re.compile(
    r'#\[\s*(get|post|put|delete|patch|options|head)\s*\(\s*"(/[^"]*)"\s*\)\s*\]',
    re.MULTILINE | re.IGNORECASE,
)

# axum route registration: .route("/path", get(handler))  or  Router::new().route(...)
_AXUM_ROUTE = re.compile(
    r'\.route\s*\(\s*"(/[^"]*)"\s*,\s*(get|post|put|delete|patch)\s*\(',
    re.MULTILINE | re.IGNORECASE,
)

# use statements for external crates
_USE_EXTERN = re.compile(r"^use\s+([\w:]+)", re.MULTILINE)


class RustExtractor(BaseExtractor):
    """Extract symbols, routes, types, and dependencies from Rust source files."""

    @property
    def file_patterns(self) -> List[str]:
        return ["*.rs"]

    @property
    def language_name(self) -> str:
        return "rust"

    def extract(self) -> ExtractionResult:
        result = ExtractionResult()

        for rs_file in self.root.rglob("*.rs"):
            if should_skip_path(rs_file):
                continue
            # Skip test modules (files named test.rs or tests/ dir)
            if rs_file.name == "test.rs" or "tests" in rs_file.parts:
                continue
            content = safe_read_text(rs_file)
            if not content:
                continue
            result.source_files.append(rs_file)
            self._extract_from_file(rs_file, content, result)

        # Parse Cargo.toml
        self._parse_cargo_toml(result)

        return result

    def _extract_from_file(
        self, filepath: Path, content: str, result: ExtractionResult
    ) -> None:
        rel = str(filepath.relative_to(self.root))

        # ── Pub functions ──────────────────────────────────────────────────────
        seen_fns: Set[str] = set()
        for m in _PUB_FN_SIMPLE.finditer(content):
            name = m.group(1)
            if name in seen_fns:
                continue
            seen_fns.add(name)

            params = (m.group(2) or "").strip()
            returns = (m.group(3) or "").strip()
            sig = f"pub fn {name}({params})"
            if returns:
                sig += f" -> {returns}"

            line = content[: m.start()].count("\n") + 1
            result.symbols.append(ExtractedSymbol(
                name=name,
                kind="function",
                file=rel,
                line=line,
                signature=sig,
            ))

        # ── Structs ────────────────────────────────────────────────────────────
        for m in _PUB_STRUCT.finditer(content):
            name = m.group(1)
            line = content[: m.start()].count("\n") + 1
            result.symbols.append(ExtractedSymbol(
                name=name, kind="struct", file=rel, line=line,
            ))
            result.types.append({"name": name, "file": rel, "line": line, "kind": "struct"})

        # ── Enums ─────────────────────────────────────────────────────────────
        for m in _PUB_ENUM.finditer(content):
            name = m.group(1)
            line = content[: m.start()].count("\n") + 1
            result.symbols.append(ExtractedSymbol(
                name=name, kind="enum", file=rel, line=line,
            ))
            result.types.append({"name": name, "file": rel, "line": line, "kind": "enum"})

        # ── Traits ────────────────────────────────────────────────────────────
        for m in _PUB_TRAIT.finditer(content):
            name = m.group(1)
            line = content[: m.start()].count("\n") + 1
            result.symbols.append(ExtractedSymbol(
                name=name, kind="trait", file=rel, line=line,
            ))

        # ── Routes — actix-web ─────────────────────────────────────────────────
        lines = content.splitlines()
        for i, line_text in enumerate(lines):
            m = _ACTIX_ROUTE.search(line_text)
            if m:
                method = m.group(1).upper()
                path = m.group(2)
                # Handler name is on the next non-empty line (the fn declaration)
                result.routes.append({
                    "method": method,
                    "path": path,
                    "file": rel,
                    "line": i + 1,
                    "framework": "actix-web",
                })

        # ── Routes — axum ─────────────────────────────────────────────────────
        for m in _AXUM_ROUTE.finditer(content):
            path = m.group(1)
            method = m.group(2).upper()
            line = content[: m.start()].count("\n") + 1
            result.routes.append({
                "method": method,
                "path": path,
                "file": rel,
                "line": line,
                "framework": "axum",
            })

        # ── Imports (external crates only) ─────────────────────────────────────
        ext_crates: Set[str] = set()
        for m in _USE_EXTERN.finditer(content):
            root_crate = m.group(1).split("::")[0]
            # Skip Rust std, self, crate, super
            if root_crate not in {"std", "core", "alloc", "self", "crate", "super"}:
                ext_crates.add(root_crate)
        if ext_crates:
            result.imports[rel] = sorted(ext_crates)

    def _parse_cargo_toml(self, result: ExtractionResult) -> None:
        """Parse Cargo.toml to extract crate name and direct dependencies."""
        cargo_toml = self.root / "Cargo.toml"
        if not cargo_toml.exists():
            return

        content = safe_read_text(cargo_toml)
        if not content:
            return

        try:
            data = tomllib.loads(content)
        except Exception:
            # Fall back to regex if tomllib can't parse it
            self._parse_cargo_toml_regex(content, result)
            return

        # Crate name
        pkg = data.get("package", {})
        if pkg.get("name"):
            result.external_calls.append(f"rust-crate: {pkg['name']}")

        # Direct dependencies
        for section in ("dependencies", "dev-dependencies"):
            for dep_name in data.get(section, {}):
                result.external_calls.append(f"rust-dep: {dep_name}")

    def _parse_cargo_toml_regex(self, content: str, result: ExtractionResult) -> None:
        """Regex fallback for Cargo.toml parsing."""
        m = re.search(r'^\s*name\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if m:
            result.external_calls.append(f"rust-crate: {m.group(1)}")

        in_deps = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped in ("[dependencies]", "[dev-dependencies]"):
                in_deps = True
                continue
            if stripped.startswith("[") and stripped != "[dependencies]":
                in_deps = False
            if in_deps and "=" in stripped and not stripped.startswith("#"):
                dep = stripped.split("=")[0].strip()
                if dep:
                    result.external_calls.append(f"rust-dep: {dep}")
