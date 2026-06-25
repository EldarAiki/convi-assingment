"""Console progress logging for agent runs."""

from __future__ import annotations

import sys
from datetime import UTC, datetime

_verbose = True
_step = 0


def set_verbose(enabled: bool) -> None:
    global _verbose
    _verbose = enabled


def reset_progress() -> None:
    global _step
    _step = 0


def log_progress(message: str) -> None:
    if not _verbose:
        return
    timestamp = datetime.now(UTC).strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", file=sys.stderr, flush=True)


def log_step(message: str) -> None:
    global _step
    _step += 1
    log_progress(f"[{_step}] {message}")


def log_reasoning(
    text: str,
    *,
    max_lines: int = 12,
    max_chars: int = 900,
) -> None:
    """Print model reasoning/planning text already returned in the AIMessage."""
    if not _verbose:
        return
    cleaned = (text or "").strip()
    if not cleaned:
        return
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 3].rstrip() + "..."
    lines = cleaned.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["..."]
    log_progress("  Reasoning:")
    for line in lines:
        if line.strip():
            log_progress(f"    {line.rstrip()}")
