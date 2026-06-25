"""Outcome benchmarks — reuses graphIngest classification logic."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

INGEST_ROOT = Path(__file__).resolve().parents[2] / "graphIngest"
if str(INGEST_ROOT) not in sys.path:
    sys.path.insert(0, str(INGEST_ROOT))

from ingest.outcomes import build_benchmarks, classify_projection_outcome  # noqa: E402


def load_benchmarks_from_projections(projections: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    return build_benchmarks(projections)


def explain_outcome_from_projection(doc: dict[str, Any], benchmarks: dict[str, dict[str, float]] | None = None) -> dict[str, Any]:
    return classify_projection_outcome(doc, benchmarks)
