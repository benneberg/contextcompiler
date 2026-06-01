"""
ccc setup — interactive onboarding wizard.

Detects whether the current directory is a single repo or a multi-repo
workspace, guides the user through setup, and runs the full generation
pipeline in one go. No README required.

Single repo:
    - Runs `ccc` (generator) in the current directory
    - Prints what was generated and next steps

Multi-repo workspace:
    - Detects git repos in current directory
    - Prompts for workspace name
    - Creates ccc-workspace.yml via workspace init
    - Runs `ccc` (generator) in each service directory
    - Runs `ccc workspace generate`
    - Prints summary and next steps
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Optional


# ── Terminal helpers ──────────────────────────────────────────────────────────

def _print_header(text: str) -> None:
    width = 60
    print("")
    print("=" * width)
    print(f"  {text}")
    print("=" * width)


def _ask(prompt: str, default: Optional[str] = None) -> str:
    """Prompt for input with an optional default."""
    if default:
        display = f"{prompt} [{default}]: "
    else:
        display = f"{prompt}: "
    try:
        answer = input(display).strip()
        return answer if answer else (default or "")
    except (KeyboardInterrupt, EOFError):
        print("")
        sys.exit(0)


def _ask_choice(prompt: str, choices: List[str], default: str = "1") -> str:
    """Present a numbered menu and return the chosen value."""
    print(f"\n  {prompt}")
    for i, choice in enumerate(choices, 1):
        marker = " (default)" if str(i) == default else ""
        print(f"    [{i}] {choice}{marker}")
    while True:
        raw = _ask("  Choice", default=default)
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        print(f"  Please enter a number between 1 and {len(choices)}")


def _run(cmd: List[str], cwd: Path, label: str) -> bool:
    """Run a subprocess, streaming output. Returns True on success."""
    print(f"\n  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(cwd))
    if result.returncode != 0:
        print(f"  [!] {label} failed (exit {result.returncode})")
        return False
    return True


# ── Detection ─────────────────────────────────────────────────────────────────

def _find_git_repos(root: Path) -> List[Path]:
    """Find immediate subdirectories that are git repos."""
    repos = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and not child.name.startswith(".") and (child / ".git").exists():
            repos.append(child)
    return repos


def _is_single_repo(root: Path) -> bool:
    return (root / ".git").exists()


def _has_existing_workspace(root: Path) -> bool:
    for name in ["ccc-workspace.yml", "ccc-workspace.yaml", "ccc-workspace.json"]:
        if (root / name).exists():
            return True
    return False


def _has_existing_context(path: Path) -> bool:
    return (path / ".llm-context").exists()


# ── Wizard flows ──────────────────────────────────────────────────────────────

def _setup_single_repo(root: Path) -> int:
    """Setup flow for a single git repo."""
    _print_header("CCC Setup — Single Repository")
    print(f"\n  Directory: {root}")
    print(f"  Detected: git repository")

    if _has_existing_context(root):
        print(f"\n  .llm-context/ already exists.")
        choice = _ask_choice(
            "What would you like to do?",
            ["Regenerate (force refresh)", "Quick update (skip unchanged)", "Cancel"],
            default="2",
        )
        if choice == "Cancel":
            print("\n  Cancelled.")
            return 0
        force = choice.startswith("Regenerate")
    else:
        print(f"\n  No .llm-context/ found — will generate now.")
        force = False

    print("")
    cmd = [sys.executable, "-m", "ccc"]
    if force:
        cmd.append("--force")

    ok = _run(cmd, cwd=root, label="context generation")
    if not ok:
        return 1

    _print_header("Done!")
    print(f"\n  Context written to: {root / '.llm-context'}")
    print(f"\n  Next steps:")
    print(f"    ccc query \"UserService\"     # search symbols at runtime")
    print(f"    ccc align                   # check code matches your docs")
    print(f"\n  To use with Copilot / Claude:")
    print(f"    #file:{root.name}/.llm-context/LLM.md")
    print("")
    return 0


def _setup_workspace(root: Path, repos: List[Path]) -> int:
    """Setup flow for a multi-repo workspace."""
    _print_header("CCC Setup — Multi-Repo Workspace")
    print(f"\n  Directory: {root}")
    print(f"  Detected: {len(repos)} git repositories")
    for repo in repos:
        has_ctx = " (has .llm-context)" if _has_existing_context(repo) else ""
        print(f"    - {repo.name}{has_ctx}")

    # Workspace name
    default_name = root.name
    workspace_name = _ask(f"\n  Workspace name", default=default_name)

    # Repo selection
    print(f"\n  Which repos should be included?")
    all_names = [r.name for r in repos]
    choice = _ask_choice(
        "Include:",
        [f"All {len(repos)} repos", "Select manually"],
        default="1",
    )

    if choice.startswith("All"):
        selected = repos
    else:
        selected = []
        for repo in repos:
            answer = _ask(f"    Include '{repo.name}'? [Y/n]", default="Y")
            if answer.upper() != "N":
                selected.append(repo)

    if not selected:
        print("\n  No repos selected. Cancelled.")
        return 0

    print(f"\n  Selected {len(selected)} repos: {', '.join(r.name for r in selected)}")

    # Workspace init
    if _has_existing_workspace(root):
        print(f"\n  ccc-workspace.yml already exists.")
        answer = _ask("  Re-initialize? This will overwrite it [y/N]", default="N")
        do_init = answer.upper() == "Y"
    else:
        do_init = True

    if do_init:
        print(f"\n  Step 1/3  Creating ccc-workspace.yml...")
        cmd = [
            sys.executable, "-m", "ccc", "workspace", "init",
            "--name", workspace_name,
            "--force",
        ]
        ok = _run(cmd, cwd=root, label="workspace init")
        if not ok:
            return 1
    else:
        print(f"\n  Step 1/3  Using existing ccc-workspace.yml")

    # Per-service generation
    print(f"\n  Step 2/3  Generating context for each service...")
    failed = []
    for i, repo in enumerate(selected, 1):
        print(f"\n  [{i}/{len(selected)}] {repo.name}")
        cmd = [sys.executable, "-m", "ccc"]
        ok = _run(cmd, cwd=repo, label=f"ccc in {repo.name}")
        if not ok:
            failed.append(repo.name)

    if failed:
        print(f"\n  [!] Failed for: {', '.join(failed)}")
        answer = _ask("  Continue with workspace generate anyway? [Y/n]", default="Y")
        if answer.upper() == "N":
            return 1

    # Workspace generate
    print(f"\n  Step 3/3  Building workspace index...")
    cmd = [sys.executable, "-m", "ccc", "workspace", "generate"]
    ok = _run(cmd, cwd=root, label="workspace generate")
    if not ok:
        return 1

    _print_header("Done!")
    print(f"\n  Workspace: {workspace_name}")
    print(f"  Services:  {len(selected)} ({len(failed)} failed)" if failed else
          f"  Services:  {len(selected)}")
    print(f"\n  Next steps:")
    print(f"    ccc workspace serve          # browse the workspace UI")
    print(f"    ccc workspace list           # list all services")
    print(f"    ccc workspace query --tags auth   # query by tag")
    print(f"\n  To use with Copilot / Claude:")
    print(f"    Open the serve UI and use 'Copy for Copilot' on any service")
    print("")
    return 0


# ── Entry point ───────────────────────────────────────────────────────────────

def run_setup(path: Optional[str] = None) -> int:
    """
    Main entry point for `ccc setup`.

    Auto-detects the situation and routes to the appropriate flow.
    """
    root = Path(path).resolve() if path else Path.cwd()

    if not root.exists():
        print(f"  Error: directory does not exist: {root}")
        return 1

    _print_header("CCC Setup")
    print(f"\n  Scanning: {root}")

    # Detect situation
    git_repos = _find_git_repos(root)
    is_single = _is_single_repo(root)

    if is_single and not git_repos:
        # Clearly a single repo
        return _setup_single_repo(root)

    if git_repos:
        if is_single:
            # Root is also a repo — could go either way, ask
            print(f"\n  This directory is itself a git repo, and contains {len(git_repos)} sub-repos.")
            choice = _ask_choice(
                "How would you like to set up?",
                [
                    f"Workspace — manage all {len(git_repos)} sub-repos together",
                    "Single repo — just generate context for this directory",
                ],
                default="1",
            )
            if choice.startswith("Single"):
                return _setup_single_repo(root)
        return _setup_workspace(root, git_repos)

    # No git repos found at all
    print(f"\n  No git repositories found in {root}")
    print(f"  Make sure you're running `ccc setup` from your workspace root,")
    print(f"  or from inside a git repository.")
    return 1
