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
