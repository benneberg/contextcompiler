"""
ccc feedback — structured post-session feedback recorder.

Records what was sufficient, missing, or unclear after an AI-assisted
coding session. Builds up organic signal in .llm-context/feedback-log.jsonl
that ccc doctor can summarise over time.

Usage:
    ccc feedback                    # interactive prompts
    ccc feedback --analyze          # summarise patterns across entries
    ccc feedback --service auth     # pre-fill service name
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


# ── Interactive prompts ───────────────────────────────────────────────────────

def _ask(prompt: str, default: str = "") -> str:
    try:
        val = input(f"  {prompt}{' [' + default + ']' if default else ''}: ").strip()
        return val if val else default
    except (KeyboardInterrupt, EOFError):
        print("")
        sys.exit(0)


def _ask_choice(prompt: str, options: List[str]) -> str:
    print(f"\n  {prompt}")
    for i, opt in enumerate(options, 1):
        print(f"    [{i}] {opt}")
    while True:
        raw = _ask("Choice", "1")
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print(f"  Please enter 1–{len(options)}")


# ── Feedback recording ────────────────────────────────────────────────────────

def run_feedback(
    root: Optional[Path] = None,
    service: Optional[str] = None,
    analyze: bool = False,
) -> int:
    """Entry point for `ccc feedback`."""
    # Auto-detect root
    if root is None:
        cwd = Path.cwd()
        root = cwd
        for parent in [cwd] + list(cwd.parents):
            if (parent / ".llm-context").exists() or (parent / "ccc-workspace.yml").exists():
                root = parent
                break

    log_path = root / ".llm-context" / "feedback-log.jsonl"

    if analyze:
        return _analyze_feedback(log_path)

    return _record_feedback(root, log_path, service)


def _record_feedback(root: Path, log_path: Path, preset_service: Optional[str]) -> int:
    """Run the interactive feedback recording flow."""
    print("\n" + "=" * 60)
    print("  CCC Feedback — Post-Session Recording")
    print("=" * 60)
    print("  Record what worked well and what was missing.")
    print("  Takes ~2 minutes. Ctrl+C to cancel.\n")

    # Task description
    task = _ask("Task description (what did you ask the AI to do?)")
    if not task:
        print("  Cancelled.")
        return 0

    # Service(s) involved
    if preset_service:
        services_raw = preset_service
    else:
        services_raw = _ask("Services involved (comma-separated, or leave blank)")
    services = [s.strip() for s in services_raw.split(",") if s.strip()]

    # Sufficiency
    sufficient = _ask_choice(
        "Was the CCC context sufficient for this task?",
        ["yes — AI had everything it needed",
         "partial — AI had some gaps but managed",
         "no — AI had to guess or ask for missing info"],
    )
    sufficient_key = sufficient.split(" ")[0]  # "yes" | "partial" | "no"

    # What was missing
    missing = _ask("What was missing or unclear? (press Enter to skip)")

    # Assumptions
    assumptions = _ask("What did the AI have to assume or guess? (press Enter to skip)")

    # Files not in context
    extra_files = _ask("Files the AI needed that weren't in LLM.md? (press Enter to skip)")

    # What worked well
    worked = _ask("What context was most useful? (press Enter to skip)")

    # Build entry
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task": task,
        "services": services,
        "sufficient": sufficient_key,
        "missing": missing or None,
        "assumptions": assumptions or None,
        "extra_files": [f.strip() for f in extra_files.split(",") if f.strip()] if extra_files else [],
        "worked_well": worked or None,
    }

    # Append to JSONL
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")

    # Also append human-readable note to ai-observations.md
    obs_path = root / ".llm-context" / "ai-observations.md"
    date_str = datetime.now().strftime("%Y-%m-%d")
    obs_lines = [
        f"\n## {date_str} — {task}\n",
        f"**Services**: {', '.join(services) if services else 'unspecified'}\n",
        f"**Context sufficient**: {sufficient_key}\n",
    ]
    if worked:
        obs_lines.append(f"**What worked**: {worked}\n")
    if missing:
        obs_lines.append(f"**Missing**: {missing}\n")
    if assumptions:
        obs_lines.append(f"**Assumptions made**: {assumptions}\n")
    if extra_files:
        obs_lines.append(f"**Files needed not in LLM.md**: {', '.join(entry['extra_files'])}\n")

    with obs_path.open("a", encoding="utf-8") as fh:
        fh.writelines(obs_lines)

    print("\n  Saved to:")
    print(f"    {log_path}")
    print(f"    {obs_path}")
    print("\n  Run `ccc feedback --analyze` to see patterns across sessions.\n")
    return 0


# ── Analysis ──────────────────────────────────────────────────────────────────

def _analyze_feedback(log_path: Path) -> int:
    """Summarise patterns across all feedback entries."""
    if not log_path.exists():
        print("\n  No feedback recorded yet.")
        print(f"  Run `ccc feedback` after an AI session to start building signal.\n")
        return 0

    entries = []
    with log_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not entries:
        print("\n  No valid entries in feedback log.\n")
        return 0

    print(f"\n{'=' * 60}")
    print(f"  Feedback Analysis — {len(entries)} session(s)")
    print(f"{'=' * 60}\n")

    # Sufficiency breakdown
    counts = {"yes": 0, "partial": 0, "no": 0}
    for e in entries:
        key = e.get("sufficient", "partial")
        counts[key] = counts.get(key, 0) + 1

    total = len(entries)
    print("  Context sufficiency:")
    for key, label in [("yes", "sufficient"), ("partial", "partial"), ("no", "insufficient")]:
        n = counts.get(key, 0)
        bar = "█" * int((n / total) * 20) if total > 0 else ""
        print(f"    {label:15s}  {n:3d} ({int(n/total*100):3d}%)  {bar}")

    # Most common missing items
    all_missing = [e["missing"] for e in entries if e.get("missing")]
    if all_missing:
        print(f"\n  What was most often missing ({len(all_missing)} entries):")
        for item in all_missing[-5:]:  # most recent 5
            print(f"    - {item[:80]}")

    # Services with most feedback
    from collections import Counter
    svc_counts: Counter = Counter()
    for e in entries:
        for svc in e.get("services", []):
            svc_counts[svc] += 1

    if svc_counts:
        print(f"\n  Most-discussed services:")
        for svc, count in svc_counts.most_common(5):
            print(f"    {svc:30s}  {count} session(s)")

    # Files frequently needed but missing from context
    all_extra: Counter = Counter()
    for e in entries:
        for f in e.get("extra_files", []):
            if f:
                all_extra[f] += 1

    if all_extra:
        print(f"\n  Files often needed but not in LLM.md:")
        for f, count in all_extra.most_common(5):
            print(f"    {f:50s}  {count}x")

    print(f"\n  Run `ccc doctor` to see actionable recommendations.\n")
    return 0
