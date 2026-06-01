"""
ccc inspect <file> — show exactly what CCC extracted from a specific file.

Answers the question: "why is my context incomplete for this file?"

Output sections:
  File info       — size, language, last modified, skip status
  Symbols         — functions/classes/types found in this file
  Routes          — HTTP routes registered in this file
  Imports         — external imports detected
  Artifact index  — which .llm-context/ artifacts reference this file
"""

import ast
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .utils.files import safe_read_text, is_binary_file, should_skip_path, EXCLUDE_DIRS


# ── Helpers ────────────────────────────────────────────────────────────────────

def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _detect_language(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript/React",
        ".js": "JavaScript", ".jsx": "JavaScript/React",
        ".go": "Go", ".rs": "Rust", ".cs": "C#", ".java": "Java",
        ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
        ".md": "Markdown", ".toml": "TOML", ".sql": "SQL",
        ".sh": "Shell", ".dockerfile": "Dockerfile",
    }.get(ext, ext.lstrip(".").upper() or "Unknown")


# ── Per-language extraction (single file) ─────────────────────────────────────

def _extract_python(content: str, path: Path):
    """Extract symbols, routes, imports from a single Python file."""
    symbols = []
    routes = []
    imports = []

    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        return symbols, routes, imports, f"SyntaxError: {e}"

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decorators = [ast.unparse(d) for d in node.decorator_list]
            # Detect routes via decorators
            for dec in decorators:
                for method in ("get", "post", "put", "delete", "patch"):
                    m = re.search(rf'\.{method}\(["\']([^"\']+)', dec)
                    if m:
                        routes.append(f"{method.upper()} {m.group(1)}  (line {node.lineno})")
            symbols.append(f"  {'async ' if isinstance(node, ast.AsyncFunctionDef) else ''}def {node.name}()  (line {node.lineno})")

        elif isinstance(node, ast.ClassDef):
            symbols.append(f"  class {node.name}  (line {node.lineno})")

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.append(f"  from {node.module} import ...")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(f"  import {alias.name}")

    return symbols, routes, list(dict.fromkeys(imports)), None  # dedupe imports


def _extract_typescript(content: str, path: Path):
    """Extract symbols, routes, imports from a single TS/JS file (regex-based)."""
    symbols = []
    routes = []
    imports = []

    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()

        # Functions / classes
        if re.match(r"(export\s+)?(async\s+)?function\s+\w+", stripped):
            name = re.search(r"function\s+(\w+)", stripped)
            if name:
                symbols.append(f"  function {name.group(1)}()  (line {i})")
        elif re.match(r"(export\s+)?(abstract\s+)?class\s+\w+", stripped):
            name = re.search(r"class\s+(\w+)", stripped)
            if name:
                symbols.append(f"  class {name.group(1)}  (line {i})")
        elif re.match(r"(export\s+)?(interface|type)\s+\w+", stripped):
            name = re.search(r"(?:interface|type)\s+(\w+)", stripped)
            if name:
                symbols.append(f"  type {name.group(1)}  (line {i})")
        elif re.match(r"(export\s+)?const\s+\w+\s*=\s*(async\s*)?\(", stripped):
            name = re.search(r"const\s+(\w+)", stripped)
            if name:
                symbols.append(f"  const {name.group(1)} = () =>  (line {i})")

        # Routes: router.get('/path', ...) or app.post('/path', ...)
        m = re.search(r"\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)", stripped)
        if m:
            routes.append(f"  {m.group(1).upper()} {m.group(2)}  (line {i})")

        # Imports
        m = re.match(r"import\s+.+from\s+['\"]([^'\"]+)['\"]", stripped)
        if m:
            imports.append(f"  from '{m.group(1)}'")

    return symbols, routes, list(dict.fromkeys(imports)), None


def _extract_generic(content: str, path: Path):
    """Minimal extraction for unsupported file types."""
    return [], [], [], None


# ── Artifact cross-reference ──────────────────────────────────────────────────

def _check_artifacts(file_path: Path, root: Path) -> List[str]:
    """
    Check which .llm-context/ artifacts reference this file.
    Returns a list of (artifact_name, status) strings.
    """
    ctx_dir = root / ".llm-context"
    if not ctx_dir.exists():
        return ["  .llm-context/ does not exist — run `ccc` first"]

    rel = _rel(file_path, root).replace("\\", "/")
    findings = []

    # symbol-index.json
    sym_path = ctx_dir / "symbol-index.json"
    if sym_path.exists():
        try:
            data = json.loads(sym_path.read_text())
            symbols_dict = data.get("symbols", {})
            # symbols is a dict of name → {file, kind, ...}
            symbols_for_file = [
                name for name, info in symbols_dict.items()
                if isinstance(info, dict) and (
                    file_path.name in info.get("file", "") or
                    rel in info.get("file", "")
                )
            ]
            if symbols_for_file:
                findings.append(f"  symbol-index.json   {len(symbols_for_file)} symbol(s) from this file: {', '.join(symbols_for_file[:5])}")
            else:
                findings.append(f"  symbol-index.json   not referenced ({len(symbols_dict)} total symbols indexed)")
        except Exception as e:
            findings.append(f"  symbol-index.json   (could not parse: {e})")
    else:
        findings.append(f"  symbol-index.json   (not generated)")

    # routes.txt — grep for file name or route patterns
    routes_path = ctx_dir / "routes.txt"
    if routes_path.exists():
        routes_content = routes_path.read_text()
        # Check if source file is mentioned, or count route lines
        if file_path.name in routes_content or rel in routes_content:
            findings.append(f"  routes.txt          referenced")
        else:
            findings.append(f"  routes.txt          not referenced")
    else:
        findings.append(f"  routes.txt          (not generated)")

    # external-dependencies.json
    ext_path = ctx_dir / "external-dependencies.json"
    if ext_path.exists():
        try:
            data = json.loads(ext_path.read_text())
            # Check if file has any external calls recorded
            findings.append(f"  external-dependencies.json  exists")
        except Exception:
            findings.append(f"  external-dependencies.json  (could not parse)")
    else:
        findings.append(f"  external-dependencies.json  (not generated)")

    # schemas
    for schema_file in ctx_dir.glob("schemas-extracted.*"):
        content = schema_file.read_text(errors="replace")
        if file_path.name in content or rel in content:
            findings.append(f"  {schema_file.name}  referenced")
        else:
            findings.append(f"  {schema_file.name}  not referenced")

    return findings


# ── Main inspect function ──────────────────────────────────────────────────────

def run_inspect(file_arg: str, root: Optional[Path] = None) -> int:
    """
    Inspect a single file and show what CCC extracted from it.

    Args:
        file_arg:  Path to file (absolute or relative to cwd)
        root:      Repo root (auto-detected if None)
    """
    file_path = Path(file_arg).resolve()

    if not file_path.exists():
        print(f"\n  Error: file not found: {file_path}")
        return 1

    if not file_path.is_file():
        print(f"\n  Error: not a file: {file_path}")
        return 1

    # Auto-detect repo root (walk up looking for .git or .llm-context)
    if root is None:
        candidate = file_path.parent
        while candidate != candidate.parent:
            if (candidate / ".git").exists() or (candidate / ".llm-context").exists():
                root = candidate
                break
            candidate = candidate.parent
        if root is None:
            root = file_path.parent

    width = 60
    print(f"\n{'=' * width}")
    print(f"  ccc inspect: {_rel(file_path, root)}")
    print(f"{'=' * width}")

    # ── File info ─────────────────────────────────────────────────────────────
    stat = file_path.stat()
    lang = _detect_language(file_path)
    mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
    binary = is_binary_file(file_path)
    excluded = should_skip_path(file_path)
    in_exclude_dir = any(part in EXCLUDE_DIRS for part in file_path.parts)

    print(f"\n  File Info")
    print(f"  {'-' * (width - 2)}")
    print(f"  Language:     {lang}")
    print(f"  Size:         {_fmt_size(stat.st_size)}")
    print(f"  Modified:     {mtime}")
    print(f"  Binary:       {'yes — skipped by CCC' if binary else 'no'}")
    print(f"  Excluded:     {'yes — matches exclude pattern' if excluded or in_exclude_dir else 'no'}")

    if binary or excluded or in_exclude_dir:
        print(f"\n  This file is excluded from CCC processing.")
        print(f"{'=' * width}\n")
        return 0

    # Read content
    content = safe_read_text(file_path) or ""
    if not content:
        print(f"\n  (empty file or unreadable)")
        print(f"{'=' * width}\n")
        return 0

    # ── Extract ───────────────────────────────────────────────────────────────
    ext = file_path.suffix.lower()
    if ext == ".py":
        symbols, routes, imports, err = _extract_python(content, file_path)
    elif ext in (".ts", ".tsx", ".js", ".jsx"):
        symbols, routes, imports, err = _extract_typescript(content, file_path)
    else:
        symbols, routes, imports, err = _extract_generic(content, file_path)

    # ── Symbols ───────────────────────────────────────────────────────────────
    print(f"\n  Symbols  ({len(symbols)} found)")
    print(f"  {'-' * (width - 2)}")
    if err:
        print(f"  Parse error: {err}")
    elif symbols:
        for s in symbols[:30]:
            print(s)
        if len(symbols) > 30:
            print(f"  ... and {len(symbols) - 30} more")
    else:
        print(f"  (none found)")

    # ── Routes ────────────────────────────────────────────────────────────────
    print(f"\n  Routes  ({len(routes)} found)")
    print(f"  {'-' * (width - 2)}")
    if routes:
        for r in routes:
            print(r)
    else:
        print(f"  (none found)")

    # ── Imports ───────────────────────────────────────────────────────────────
    print(f"\n  Imports  ({len(imports)} found)")
    print(f"  {'-' * (width - 2)}")
    if imports:
        for imp in imports[:20]:
            print(imp)
        if len(imports) > 20:
            print(f"  ... and {len(imports) - 20} more")
    else:
        print(f"  (none found)")

    # ── Artifact cross-reference ──────────────────────────────────────────────
    print(f"\n  Artifact Index  (in .llm-context/)")
    print(f"  {'-' * (width - 2)}")
    artifact_info = _check_artifacts(file_path, root)
    for line in artifact_info:
        print(line)

    print(f"\n{'=' * width}\n")
    return 0
