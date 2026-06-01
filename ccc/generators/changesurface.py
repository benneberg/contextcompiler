"""
Change surface generator.

Produces .llm-context/change-surface.json — a ranked list of files by
how likely they are to need editing when implementing a change.

Scoring factors (all normalised 0-1, then weighted):
  fan_in         How many other files import this file (high = central)
  recency        How recently this file was modified (recent = actively worked on)
  size           Inverse of file size (smaller files are more focused/editable)
  pattern_density Count of route/schema/handler patterns (high = business logic)

This feeds into:
  - The intent query UI (P2-08) — highlight likely change targets
  - ccc context-for <task> (P3-08) — select artifacts by relevance

Output schema:
{
  "_meta": { "generated": "...", "total_files": N, "scored_files": M },
  "files": [
    {
      "path": "src/thumbnail/processor.py",
      "score": 0.87,
      "rank": 1,
      "factors": { "fan_in": 0.9, "recency": 0.8, "pattern_density": 0.7, "size": 0.6 },
      "imported_by_count": 12,
      "days_since_modified": 2
    },
    ...
  ]
}
"""

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .base import BaseGenerator
from ..file_index import FileIndex, FileInfo
from ..utils.files import safe_read_text, should_skip_path
from ..utils.formatting import get_timestamp


# Weight of each factor in final score (must sum to 1.0)
_WEIGHTS = {
    "fan_in":          0.40,   # most important: how central is this file?
    "recency":         0.25,   # recently touched = actively relevant
    "pattern_density": 0.25,   # contains routes/handlers/schemas
    "size":            0.10,   # smaller files are more focused
}

# Patterns that indicate business-logic-heavy files
_BUSINESS_PATTERNS = [
    re.compile(r"@(?:app|router|blueprint)\.(get|post|put|delete|patch)\s*\(", re.I),
    re.compile(r"#\[(?:get|post|put|delete|patch)\s*\("),
    re.compile(r'router\.(GET|POST|PUT|DELETE|PATCH)\s*\(', re.I),
    re.compile(r"class\s+\w+(?:View|Handler|Controller|Service|Repository)"),
    re.compile(r"def\s+(?:handle|process|create|update|delete|get|list|search)_\w+"),
    re.compile(r"async\s+fn\s+\w+.*impl\s+Responder"),
    re.compile(r"Base\s*=\s*declarative_base\(\)"),
    re.compile(r"@(?:dataclass|schema|model)\b"),
    re.compile(r"interface\s+\w+(?:Service|Repository|Handler|Controller)"),
    re.compile(r"export\s+(?:default\s+)?(?:async\s+)?function\s+\w+(?:Handler|Controller)"),
]

# Extensions to score (source code only)
_SCOREABLE_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx",
    ".go", ".rs", ".cs", ".java",
}


class ChangeSurfaceGenerator(BaseGenerator):
    """Rank files by likelihood of needing changes when implementing a feature."""

    def __init__(self, root: Path, config: dict, file_index: FileIndex):
        super().__init__(root, config)
        self.index = file_index

    @property
    def output_filename(self) -> str:
        return "change-surface.json"

    def generate(self) -> Tuple[str, List[Path]]:
        source_files = [
            fi for fi in self.index.all_files()
            if fi.ext in _SCOREABLE_EXTS and not should_skip_path(fi.path)
        ]

        if not source_files:
            return json.dumps({"_meta": {"generated": get_timestamp(), "total_files": 0, "scored_files": 0}, "files": []}), []

        # Build import fan-in map
        fan_in = self._build_fan_in(source_files)

        # Get git recency (days since last commit per file)
        git_ages = self._get_git_ages([fi.path for fi in source_files])

        # Score each file
        now = time.time()
        raw_scores: List[Dict] = []

        for fi in source_files:
            content = safe_read_text(fi.path) or ""

            # Fan-in: how many files import this one
            imported_by = fan_in.get(fi.rel_path, 0)

            # Recency: days since last git commit (fallback to mtime)
            if fi.path in git_ages:
                days_old = git_ages[fi.path]
            else:
                days_old = (now - fi.mtime) / 86400

            # Pattern density: count of business logic markers
            pattern_hits = sum(
                1 for p in _BUSINESS_PATTERNS if p.search(content)
            )

            raw_scores.append({
                "path": fi.rel_path,
                "imported_by_count": imported_by,
                "days_since_modified": round(days_old, 1),
                "pattern_hits": pattern_hits,
                "size_bytes": fi.size,
                "source_path": fi.path,
            })

        # Normalise each factor across all files
        scored = self._normalise_and_score(raw_scores)

        # Sort by final score descending
        scored.sort(key=lambda x: x["score"], reverse=True)
        for i, entry in enumerate(scored):
            entry["rank"] = i + 1
            entry.pop("source_path", None)

        output = {
            "_meta": {
                "generated": get_timestamp(),
                "total_files": len(source_files),
                "scored_files": len(scored),
                "weights": _WEIGHTS,
                "note": (
                    "Files ranked by likelihood of needing edits when implementing a change. "
                    "fan_in=centrality, recency=recent activity, "
                    "pattern_density=business logic density, size=inverse file size."
                ),
            },
            "files": scored,
        }

        return json.dumps(output, indent=2), [fi.path for fi in source_files]

    # ── Fan-in map ────────────────────────────────────────────────────────────

    def _build_fan_in(self, files: List[FileInfo]) -> Dict[str, int]:
        """
        Count how many files import each file.
        Uses a fast string-matching approach: look for the stem of each
        file in the import statements of every other file.
        """
        # Build a quick lookup: stem → set of rel_paths with that stem
        stem_to_paths: Dict[str, List[str]] = {}
        for fi in files:
            stem = fi.path.stem
            stem_to_paths.setdefault(stem, []).append(fi.rel_path)

        fan_in: Dict[str, int] = {fi.rel_path: 0 for fi in files}

        # Import patterns
        import_patterns = [
            re.compile(r"from\s+['\"]([^'\"]+)['\"]"),       # JS/TS: from './module'
            re.compile(r"import\s+['\"]([^'\"]+)['\"]"),      # JS/TS: import './module'
            re.compile(r"from\s+([\w.]+)\s+import"),          # Python: from module import
            re.compile(r"^import\s+([\w.]+)", re.MULTILINE),  # Python: import module
            re.compile(r'"([\w/.-]+)"'),                       # Go imports (rough)
        ]

        for fi in files:
            content = safe_read_text(fi.path) or ""
            for pattern in import_patterns:
                for m in pattern.finditer(content):
                    ref = m.group(1)
                    # Match against stems
                    ref_stem = Path(ref).stem
                    for rel_path in stem_to_paths.get(ref_stem, []):
                        if rel_path != fi.rel_path:
                            fan_in[rel_path] = fan_in.get(rel_path, 0) + 1

        return fan_in

    # ── Git recency ───────────────────────────────────────────────────────────

    def _get_git_ages(self, paths: List[Path]) -> Dict[Path, float]:
        """
        Get days-since-last-commit for each file via git log.
        Uses a single git call for efficiency. Falls back to empty dict on error.
        """
        ages: Dict[Path, float] = {}
        now = time.time()

        try:
            # Get last commit timestamp for each tracked file in one call
            result = subprocess.run(
                ["git", "log", "--format=%ct %H", "--name-only", "--diff-filter=M", "-200"],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return ages

            current_ts: Optional[float] = None
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) == 2 and parts[0].isdigit():
                    current_ts = float(parts[0])
                elif current_ts is not None and line:
                    file_path = self.root / line
                    if file_path not in ages:
                        ages[file_path] = (now - current_ts) / 86400

        except Exception:
            pass

        return ages

    # ── Normalise and score ───────────────────────────────────────────────────

    def _normalise_and_score(self, raw: List[Dict]) -> List[Dict]:
        """Normalise each factor to [0, 1] and compute weighted final score."""
        if not raw:
            return []

        # Extract raw values for normalisation
        fan_ins       = [r["imported_by_count"] for r in raw]
        ages          = [r["days_since_modified"] for r in raw]
        patterns      = [r["pattern_hits"] for r in raw]
        sizes         = [r["size_bytes"] for r in raw]

        def _norm_hi(vals: List[float], v: float) -> float:
            """Higher raw value → higher normalised score."""
            mn, mx = min(vals), max(vals)
            return (v - mn) / (mx - mn) if mx > mn else 0.5

        def _norm_lo(vals: List[float], v: float) -> float:
            """Lower raw value → higher normalised score (recency: fewer days = better)."""
            mn, mx = min(vals), max(vals)
            return 1.0 - ((v - mn) / (mx - mn)) if mx > mn else 0.5

        scored = []
        for r in raw:
            f_fan_in   = _norm_hi(fan_ins,  r["imported_by_count"])
            f_recency  = _norm_lo(ages,     r["days_since_modified"])
            f_patterns = _norm_hi(patterns, r["pattern_hits"])
            f_size     = _norm_lo(sizes,    r["size_bytes"])  # smaller = more focused

            final = (
                _WEIGHTS["fan_in"]          * f_fan_in +
                _WEIGHTS["recency"]         * f_recency +
                _WEIGHTS["pattern_density"] * f_patterns +
                _WEIGHTS["size"]            * f_size
            )

            scored.append({
                "path":                r["path"],
                "score":               round(final, 4),
                "imported_by_count":   r["imported_by_count"],
                "days_since_modified": r["days_since_modified"],
                "pattern_hits":        r["pattern_hits"],
                "factors": {
                    "fan_in":          round(f_fan_in, 3),
                    "recency":         round(f_recency, 3),
                    "pattern_density": round(f_patterns, 3),
                    "size":            round(f_size, 3),
                },
            })

        return scored
