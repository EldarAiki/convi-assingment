"""Case type taxonomy helpers for search normalization and synonyms."""

from __future__ import annotations

# User-facing terms -> canonical stored values (cases.caseType / projection.classifiedCaseType)
CASE_TYPE_SYNONYMS: dict[str, list[str]] = {
    "medical_negligence": ["medical_negligence"],
    "medical negligence": ["medical_negligence"],
    "medical-negligence": ["medical_negligence"],
    "negligence": ["medical_negligence"],
    "רשלנות רפואית": ["medical_negligence"],
    "liability": ["liability"],
    "חבות": ["liability"],
    "premises liability": ["liability"],
    "car_accident_serious": ["car_accident_serious"],
    "car accident serious": ["car_accident_serious"],
    "serious car accident": ["car_accident_serious"],
    "car_accident_minor": ["car_accident_minor"],
    "car accident minor": ["car_accident_minor"],
    "minor car accident": ["car_accident_minor"],
    "car accident": ["car_accident_serious", "car_accident_minor"],
    "תאונת דרכים": ["car_accident_serious", "car_accident_minor"],
    "work_accident": ["work_accident"],
    "work accident": ["work_accident"],
    "תאונת עבודה": ["work_accident"],
    "student_accident": ["student_accident"],
    "student accident": ["student_accident"],
    "general_disability": ["general_disability"],
    "disability": ["general_disability"],
}


def normalize_token(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def expand_case_type_filter(raw: str | None) -> list[str]:
    """Map a user/LLM case type phrase to canonical stored type values."""
    if not raw or not raw.strip():
        return []

    text = raw.strip()
    lowered = text.lower()
    if lowered in CASE_TYPE_SYNONYMS:
        return list(dict.fromkeys(CASE_TYPE_SYNONYMS[lowered]))
    if text in CASE_TYPE_SYNONYMS:
        return list(dict.fromkeys(CASE_TYPE_SYNONYMS[text]))

    normalized = normalize_token(text)
    matches: list[str] = []
    if normalized in CASE_TYPE_SYNONYMS:
        matches.extend(CASE_TYPE_SYNONYMS[normalized])

    # Partial synonym keys (e.g. "medical" -> medical_negligence if key contains it)
    for key, values in CASE_TYPE_SYNONYMS.items():
        key_norm = normalize_token(key)
        if normalized in key_norm or key_norm in normalized:
            matches.extend(values)

    # Always include direct normalized token and raw substring fallback
    matches.append(normalized)
    if normalized != lowered.replace(" ", "_"):
        matches.append(lowered.replace(" ", "_"))

    return list(dict.fromkeys(matches))
