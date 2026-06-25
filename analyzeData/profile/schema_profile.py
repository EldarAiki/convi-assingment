"""Mechanical MongoDB schema profiling for graph design."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from pymongo import MongoClient

from config import MONGODB_URL, OUTPUT_DIR, get_database_name

REFERENCE_FIELD_PATTERN = re.compile(
    r"(^id$|Id$|Ids$|_id$|userId$|clientId$|caseId$|sessionId$|messageId$|entityId$)",
    re.IGNORECASE,
)


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        if not value:
            return "array<empty>"
        return f"array<{_type_name(value[0])}>"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _walk_fields(
    obj: Any,
    prefix: str = "",
    fields: dict[str, set[str]] | None = None,
) -> dict[str, set[str]]:
    if fields is None:
        fields = {}

    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            fields.setdefault(path, set()).add(_type_name(value))
            if isinstance(value, dict):
                _walk_fields(value, path, fields)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                _walk_fields(value[0], f"{path}[]", fields)
    return fields


def _sample_documents(collection, limit: int = 50) -> list[dict[str, Any]]:
    return list(collection.find({}, limit=limit))


def _field_stats(collection, field_path: str, sample_size: int = 200) -> dict[str, Any]:
    values: list[Any] = []
    null_count = 0

    for doc in collection.find({}, {field_path: 1}).limit(sample_size):
        parts = field_path.split(".")
        current: Any = doc
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]

        if current is None:
            null_count += 1
        elif isinstance(current, list):
            values.extend(current)
        else:
            values.append(current)

    distinct = len({json.dumps(v, default=str, sort_keys=True) for v in values if v is not None})
    return {
        "sampleSize": sample_size,
        "nonNullCount": len(values),
        "nullCount": null_count,
        "distinctCount": distinct,
        "examples": [v for v in values[:3] if v is not None],
    }


def profile_collection(collection) -> dict[str, Any]:
    estimated_count = collection.estimated_document_count()
    samples = _sample_documents(collection)
    merged_fields: dict[str, set[str]] = {}

    for sample in samples:
        for path, types in _walk_fields(sample).items():
            merged_fields.setdefault(path, set()).update(types)

    reference_fields = [
        path
        for path in merged_fields
        if REFERENCE_FIELD_PATTERN.search(path.split(".")[-1])
    ]

    key_field_stats = {
        field: _field_stats(collection, field)
        for field in reference_fields[:15]
    }

    return {
        "documentCount": estimated_count,
        "sampleCount": len(samples),
        "fields": {
            path: sorted(types)
            for path, types in sorted(merged_fields.items())
        },
        "referenceFields": reference_fields,
        "referenceFieldStats": key_field_stats,
        "sampleDocument": samples[0] if samples else None,
    }


def profile_database() -> dict[str, Any]:
    client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=20000)
    client.admin.command("ping")

    db_name = get_database_name()
    db = client[db_name]

    collections = {}
    for name in sorted(db.list_collection_names()):
        collections[name] = profile_collection(db[name])

    cross_collection_ids = _find_cross_collection_references(collections)

    return {
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "database": db_name,
        "collections": collections,
        "crossCollectionReferences": cross_collection_ids,
        "graphHints": _graph_hints(collections, cross_collection_ids),
    }


def _find_cross_collection_references(collections: dict[str, Any]) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []

    case_id_fields = []
    user_id_fields = []
    for coll_name, coll_data in collections.items():
        for field in coll_data["referenceFields"]:
            leaf = field.split(".")[-1].lower()
            if "caseid" in leaf:
                case_id_fields.append((coll_name, field))
            if "userid" in leaf or "clientid" in leaf:
                user_id_fields.append((coll_name, field))

    if case_id_fields:
        hints.append(
            {
                "hubEntity": "Case",
                "fields": [{"collection": c, "field": f} for c, f in case_id_fields],
                "note": "caseId appears across multiple collections — likely central graph node",
            }
        )

    if user_id_fields:
        hints.append(
            {
                "hubEntity": "User/Person",
                "fields": [{"collection": c, "field": f} for c, f in user_id_fields],
                "note": "userId/clientId links people to cases and activity",
            }
        )

    return hints


def _graph_hints(
    collections: dict[str, Any],
    cross_refs: list[dict[str, Any]],
) -> list[str]:
    hints = [
        "Start graph modeling from `cases` as the central Case node.",
        "Treat `contacts` and embedded `clientInfo` in cases as Person/Party nodes.",
        "Link activity streams via case_activity_log, communications, files, and messages.",
        "Use referenceFieldStats distinctCount to distinguish identifiers vs categorical fields.",
    ]

    if "cases" in collections and "contacts" in collections:
        hints.append(
            "contacts.caseIds[] suggests a many-to-many Contact–Case relationship."
        )

    if "conversations" in collections:
        hints.append(
            "conversations bridges cases and chat sessions (caseId + sessionId + userId)."
        )

    if cross_refs:
        hints.append(
            f"Detected {len(cross_refs)} cross-collection reference hub(s) — see crossCollectionReferences."
        )

    return hints


def main() -> None:
    report = profile_database()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "schema_report.json"

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, default=str)

    print(f"Wrote schema report to {output_path}")
    print(f"Collections profiled: {', '.join(report['collections'].keys())}")
    print("Graph hints:")
    for hint in report["graphHints"]:
        print(f"  - {hint}")


if __name__ == "__main__":
    main()
