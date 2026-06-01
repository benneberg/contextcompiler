"""
CCC logging — structured, level-aware, CI-friendly.

Usage:
    from ..utils.logging import get_logger
    log = get_logger(__name__)
    log.info("tree.txt (regenerated)")
    log.debug("hash cache hit: %s", filename)
    log.warning("symbol extractor: skipped binary file %s", path)
    log.error("generator failed: %s", exc)

Levels:
    --quiet    WARNING+  (errors and warnings only)
    (default)  INFO      (normal user-facing output)
    --verbose  DEBUG     (everything including cache hits, skips, internal state)

The root "ccc" logger is configured once by configure_logging().
All child loggers (ccc.generator, ccc.workspace.serve, etc.) inherit it.
"""

import logging
import sys
from typing import Optional


# ── ANSI colours for terminal output ─────────────────────────────────────────

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_RED    = "\033[31m"
_YELLOW = "\033[33m"
_CYAN   = "\033[36m"
_WHITE  = "\033[37m"


def _supports_colour(stream) -> bool:
    try:
        import os
        return hasattr(stream, "isatty") and stream.isatty() and os.environ.get("NO_COLOR") is None
    except Exception:
        return False


class _CCCFormatter(logging.Formatter):
    """
    Human-friendly formatter that preserves the existing CCC console style.

    INFO  messages: plain text (matches existing `print()` output exactly)
    DEBUG messages: dimmed, prefixed with '·'
    WARN  messages: yellow '⚠ '
    ERROR messages: bold red '✗ '
    """

    def __init__(self, use_colour: bool = True):
        super().__init__()
        self._colour = use_colour

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()

        if not self._colour:
            if record.levelno == logging.WARNING:
                return f"  ⚠  {msg}"
            if record.levelno == logging.ERROR:
                return f"  ✗  {msg}"
            if record.levelno == logging.DEBUG:
                return f"  ·  {msg}"
            return msg

        if record.levelno == logging.DEBUG:
            return f"{_DIM}  ·  {msg}{_RESET}"
        if record.levelno == logging.WARNING:
            return f"{_YELLOW}  ⚠  {msg}{_RESET}"
        if record.levelno == logging.ERROR:
            return f"{_BOLD}{_RED}  ✗  {msg}{_RESET}"
        return msg  # INFO — plain, matches old print() output


# ── Public API ────────────────────────────────────────────────────────────────

def configure_logging(
    verbose: bool = False,
    quiet: bool = False,
    log_file: Optional[str] = None,
) -> None:
    """
    Configure the root 'ccc' logger.  Call once from cli.main() before any
    other ccc code runs.

    verbose=True  → DEBUG level (all internal tracing)
    quiet=True    → WARNING level (errors/warnings only, good for CI)
    default       → INFO level (normal user output)
    """
    root = logging.getLogger("ccc")

    # Avoid duplicate handlers if called more than once (e.g. in tests)
    root.handlers.clear()

    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING
    else:
        level = logging.INFO

    root.setLevel(level)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(_CCCFormatter(use_colour=_supports_colour(sys.stdout)))
    root.addHandler(console)

    # Optional file handler (plain text, no colour)
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)  # file always gets everything
        fh.setFormatter(_CCCFormatter(use_colour=False))
        root.addHandler(fh)

    # Suppress noisy third-party loggers
    logging.getLogger("watchdog").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a child logger under the 'ccc' hierarchy.

    Usage:
        log = get_logger(__name__)
        # → logging.getLogger("ccc.generators.symbols") etc.
    """
    # Strip leading package name if present so names stay under 'ccc'
    if name.startswith("ccc."):
        child_name = name
    else:
        # e.g. __name__ = "ccc.generators.symbols"
        child_name = name

    return logging.getLogger(child_name)
