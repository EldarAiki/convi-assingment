"""Deterministic case outcome classification from projection data."""

from __future__ import annotations

from typing import Any

TERMINAL_STAGES = frozenset(
    {
        "settlement",
        "case_closed",
        "payment",
        "payment_received",
        "closed",
        "fast_track_closure",
    }
)

DELAY_SLA_STATUSES = frozenset({"overdue", "at_risk"})


def compensation_max(projection: dict[str, Any]) -> float:
    financials = projection.get("financials") or {}
    estimated = financials.get("estimatedCompensation")
    if isinstance(estimated, dict):
        value = estimated.get("max")
        if value is None:
            value = estimated.get("min")
        return float(value or 0)
    if isinstance(estimated, (int, float)):
        return float(estimated)
    return 0.0


def stage_progress(projection: dict[str, Any]) -> float | None:
    case_stage = projection.get("caseStage") or {}
    stage_number = case_stage.get("stageNumber")
    total_stages = case_stage.get("totalStages")
    if isinstance(stage_number, int) and isinstance(total_stages, int) and total_stages > 0:
        return round(stage_number / total_stages, 3)
    return None


def is_terminal_stage(projection: dict[str, Any]) -> bool:
    case_stage = projection.get("caseStage") or {}
    current_stage = case_stage.get("currentStage")
    if current_stage in TERMINAL_STAGES:
        return True
    for track in case_stage.get("parallelTracks") or []:
        if isinstance(track, dict) and track.get("currentStage") in TERMINAL_STAGES:
            return True
    return False


def build_benchmarks(projections: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Build compensation percentile benchmarks per classifiedCaseType."""
    by_type: dict[str, list[float]] = {}
    all_values: list[float] = []

    for doc in projections:
        projection = doc.get("projection") or {}
        case_type = (projection.get("classification") or {}).get("classifiedCaseType") or "_all"
        value = compensation_max(projection)
        by_type.setdefault(case_type, []).append(value)
        all_values.append(value)

    benchmarks: dict[str, dict[str, float]] = {}

    def percentiles(values: list[float]) -> dict[str, float]:
        if not values:
            return {"p40": 0.0, "p75": 0.0, "median": 0.0}
        ordered = sorted(values)
        mid = len(ordered) // 2
        median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
        p40_index = max(0, int(len(ordered) * 0.4) - 1)
        p75_index = max(0, int(len(ordered) * 0.75) - 1)
        return {
            "p40": float(ordered[p40_index]),
            "p75": float(ordered[p75_index]),
            "median": float(median),
        }

    benchmarks["_all"] = percentiles(all_values)
    for case_type, values in by_type.items():
        benchmarks[case_type] = percentiles(values)
    return benchmarks


def classify_projection_outcome(
    doc: dict[str, Any],
    benchmarks: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    projection = doc.get("projection") or {}
    case_stage = projection.get("caseStage") or {}
    timing = projection.get("timing") or {}
    case_type = (projection.get("classification") or {}).get("classifiedCaseType") or "_all"

    bench = (benchmarks or {}).get(case_type) or (benchmarks or {}).get("_all") or {}
    success_threshold = bench.get("p75", 500_000.0)
    partial_threshold = bench.get("p40", 50_000.0)

    comp = compensation_max(projection)
    progress = stage_progress(projection)
    terminal = is_terminal_stage(projection)
    sla_status = case_stage.get("slaStatus")
    timing_overdue = bool(timing.get("isOverdue"))
    reasons: list[str] = []

    if terminal and comp >= success_threshold:
        band = "success"
        reasons.append("terminal_stage_high_compensation")
    elif terminal and comp > 0:
        band = "partial_success" if comp < success_threshold else "success"
        reasons.append("terminal_stage_moderate_compensation")
    elif terminal and comp <= 0:
        band = "failed"
        reasons.append("terminal_stage_no_compensation")
    elif sla_status in DELAY_SLA_STATUSES:
        band = "partial_success" if comp >= partial_threshold else "incomplete"
        reasons.append(f"sla_{sla_status}")
    elif timing_overdue:
        band = "partial_success" if comp >= partial_threshold else "incomplete"
        reasons.append("timing_overdue")
    elif progress is not None and progress < 0.5 and timing_overdue:
        band = "partial_success"
        reasons.append("slow_progress")
    else:
        band = "incomplete"
        reasons.append("active_case")

    return {
        "outcomeBand": band,
        "compensationMax": comp,
        "stageProgress": progress,
        "isTerminalStage": terminal,
        "timingOverdue": timing_overdue,
        "outcomeReasons": reasons,
        "successThresholdUsed": success_threshold,
        "partialThresholdUsed": partial_threshold,
    }
