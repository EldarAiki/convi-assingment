"""Analyze how case_activity_log references files and communications."""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
db = MongoClient(os.getenv("MONGODB_URL"))["convi-assessment"]

activity = db["case_activity_log"]
files = db["files"]
communications = db["communications"]

OUTPUT = Path(__file__).resolve().parents[2] / "analyzeData" / "output" / "activity_linkage_report.json"


def is_object_id(value: str) -> bool:
    return bool(re.fullmatch(r"[a-f0-9]{24}", value or ""))


def build_lookup_sets() -> dict[str, set[str]]:
    file_ids: set[str] = set()
    file_entity_ids: set[str] = set()
    comm_mongo_ids: set[str] = set()
    comm_business_ids: set[str] = set()

    for doc in files.find({}, {"_id": 1, "messageId": 1, "entityId": 1}):
        file_ids.add(str(doc["_id"]))
        if doc.get("messageId"):
            file_entity_ids.add(str(doc["messageId"]))
        if doc.get("entityId"):
            file_entity_ids.add(str(doc["entityId"]))

    for doc in communications.find({}, {"_id": 1, "communicationId": 1, "providerMetadata.messageId": 1}):
        comm_mongo_ids.add(str(doc["_id"]))
        if doc.get("communicationId"):
            comm_business_ids.add(str(doc["communicationId"]))
        msg_id = (doc.get("providerMetadata") or {}).get("messageId")
        if msg_id:
            comm_business_ids.add(str(msg_id))

    return {
        "file_mongo_id": file_ids,
        "file_related_ids": file_entity_ids,
        "communication_mongo_id": comm_mongo_ids,
        "communication_business_id": comm_business_ids,
    }


def extract_candidate_refs(doc: dict) -> dict[str, str | None]:
    details = doc.get("details") or {}
    return {
        "entityId": doc.get("entityId"),
        "details.fileId": details.get("fileId"),
        "details.communicationId": details.get("communicationId"),
        "details.messageId": details.get("messageId"),
        "details.reminderId": details.get("reminderId"),
        "details.contactId": details.get("contactId"),
    }


def classify_ref(value: str | None, lookups: dict[str, set[str]]) -> list[str]:
    if not value:
        return []
    matches = []
    if value in lookups["file_mongo_id"]:
        matches.append("files._id")
    if value in lookups["file_related_ids"]:
        matches.append("files.relatedId")
    if value in lookups["communication_mongo_id"]:
        matches.append("communications._id")
    if value in lookups["communication_business_id"]:
        matches.append("communications.communicationId")
    if is_object_id(value) and not matches:
        matches.append("looks_like_objectid_but_unmatched")
    elif not matches:
        matches.append("unmatched_non_objectid")
    return matches


def nested_detail_keys(limit: int = 500) -> Counter:
    keys = Counter()
    for doc in activity.find({}, {"details": 1}).limit(limit):
        details = doc.get("details") or {}
        for key in details.keys():
            keys[key] += 1
    return keys


def analyze() -> dict:
    lookups = build_lookup_sets()
    report: dict = {
        "lookupSizes": {k: len(v) for k, v in lookups.items()},
        "totalActivities": activity.count_documents({}),
        "activitiesWithEntityId": activity.count_documents({"entityId": {"$exists": True, "$ne": None}}),
        "entityIdMatchSummary": Counter(),
        "fieldMatchSummary": Counter(),
        "byCategoryAction": {},
        "samples": defaultdict(list),
        "detailKeys": dict(nested_detail_keys()),
    }

    category_action_stats: dict[tuple, dict] = defaultdict(
        lambda: {
            "count": 0,
            "withEntityId": 0,
            "entityIdMatches": Counter(),
            "detailsFileIdMatches": 0,
            "detailsCommunicationIdMatches": 0,
        }
    )

    for doc in activity.find({}):
        category = doc.get("category")
        action = doc.get("action")
        key = (category, action)
        stats = category_action_stats[key]
        stats["count"] += 1

        refs = extract_candidate_refs(doc)
        entity_id = refs.get("entityId")
        if entity_id:
            stats["withEntityId"] += 1
            match_types = classify_ref(str(entity_id), lookups)
            for match in match_types:
                stats["entityIdMatches"][match] += 1
                report["entityIdMatchSummary"][match] += 1
            bucket = match_types[0] if match_types else "no_entityId"
            if len(report["samples"][bucket]) < 3:
                report["samples"][bucket].append(
                    {
                        "category": category,
                        "action": action,
                        "entityId": entity_id,
                        "summary": (doc.get("summary") or "")[:120],
                        "refs": refs,
                    }
                )

        for field_name, field_value in refs.items():
            if field_name == "entityId" or not field_value:
                continue
            matches = classify_ref(str(field_value), lookups)
            for match in matches:
                report["fieldMatchSummary"][f"{field_name}->{match}"] += 1
            if field_name == "details.fileId" and "files._id" in matches:
                stats["detailsFileIdMatches"] += 1
            if field_name == "details.communicationId" and (
                "communications._id" in matches or "communications.communicationId" in matches
            ):
                stats["detailsCommunicationIdMatches"] += 1

    for (category, action), stats in sorted(
        category_action_stats.items(), key=lambda item: item[1]["count"], reverse=True
    )[:40]:
        report["byCategoryAction"][f"{category}/{action}"] = {
            "count": stats["count"],
            "withEntityId": stats["withEntityId"],
            "entityIdMatches": dict(stats["entityIdMatches"]),
            "detailsFileIdMatches": stats["detailsFileIdMatches"],
            "detailsCommunicationIdMatches": stats["detailsCommunicationIdMatches"],
        }

    # Direct entityId lookup attempts for unmatched objectIds
    unmatched_object_ids = []
    for doc in activity.find({"entityId": {"$exists": True, "$ne": None}}):
        entity_id = str(doc.get("entityId"))
        matches = classify_ref(entity_id, lookups)
        if matches == ["looks_like_objectid_but_unmatched"]:
            unmatched_object_ids.append(entity_id)
    report["unmatchedObjectIdCount"] = len(unmatched_object_ids)
    report["unmatchedObjectIdDistinct"] = len(set(unmatched_object_ids))

    # Try resolving unmatched 24-char ids against other collections
    other_collection_hits = Counter()
    sample_unmatched = list(set(unmatched_object_ids))[:30]
    collections = db.list_collection_names()
    for value in sample_unmatched:
        for coll_name in collections:
            if coll_name == "case_activity_log":
                continue
            try:
                oid = ObjectId(value)
            except Exception:
                continue
            if db[coll_name].count_documents({"_id": oid}, limit=1):
                other_collection_hits[coll_name] += 1
                break
            if db[coll_name].count_documents({"_id": value}, limit=1):
                other_collection_hits[coll_name] += 1
                break

    report["unmatchedObjectIdSampleChecked"] = len(sample_unmatched)
    report["unmatchedObjectIdFoundInOtherCollections"] = dict(other_collection_hits)

    # Compare activity communication category vs communications collection overlap by case/time
    comm_activity = activity.count_documents({"category": "communication"})
    report["communicationCategoryActivities"] = comm_activity
    report["communicationsCollectionCount"] = communications.count_documents({})

    return report


def main() -> None:
    report = analyze()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(OUTPUT)
    print("entityId matches:", report["entityIdMatchSummary"])
    print("field matches:", report["fieldMatchSummary"])
    print("unmatched objectIds:", report["unmatchedObjectIdCount"])


if __name__ == "__main__":
    main()
