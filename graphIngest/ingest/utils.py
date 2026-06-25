"""Shared helpers for MongoDB → Neo4j ingestion."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any


def get_nested(data: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def stringify_id(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def to_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def truncate(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def clean_props(props: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in props.items():
        if value is None:
            continue
        if isinstance(value, list):
            normalized = [item for item in value if item is not None and str(item).strip()]
            if normalized:
                cleaned[key] = normalized
            continue
        if isinstance(value, (str, int, float, bool)):
            cleaned[key] = value
        elif isinstance(value, datetime):
            cleaned[key] = value.isoformat()
        else:
            cleaned[key] = str(value)
    return cleaned


def normalize_body_parts(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else None
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if item is not None and str(item).strip()]
        return parts or None
    text = str(value).strip()
    return [text] if text else None


def build_injury_search_text(
    main_injury: str | None,
    body_parts: list[str] | None,
    event_description: str | None = None,
    damage_description: str | None = None,
    projection_summary: str | None = None,
) -> str | None:
    segments: list[str] = []
    if main_injury:
        segments.append(str(main_injury))
    if body_parts:
        segments.extend(body_parts)
    if event_description:
        segments.append(str(event_description))
    if damage_description:
        segments.append(str(damage_description))
    if projection_summary:
        segments.append(str(projection_summary))
    if not segments:
        return None
    return truncate(" | ".join(dict.fromkeys(segments)), 800)


def build_search_digest(
    case_type: str | None,
    projection_summary: str | None,
    accident_date: str | None,
) -> str | None:
    parts = []
    if case_type:
        parts.append(f"type={case_type}")
    if accident_date:
        parts.append(f"accidentDate={accident_date}")
    if projection_summary:
        parts.append(projection_summary)
    if not parts:
        return None
    return truncate(" | ".join(parts), 500)


def normalize_party_name(name: str) -> str:
    text = name.strip().lower()
    text = text.replace('בע"מ', "").replace("בע״מ", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def party_id_from_name(name: str, role_type: str) -> str:
    normalized = normalize_party_name(name)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    prefix = {"insurer": "org", "expert": "expert"}.get(role_type, "party")
    return f"{prefix}:{digest}"
