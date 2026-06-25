"""Follow-up: deep dive on activity_log reference fields."""

import json
import os
from collections import Counter
from pathlib import Path

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
db = MongoClient(os.getenv("MONGODB_URL"))["convi-assessment"]
activity = db["case_activity_log"]

# entityId format patterns
patterns = Counter()
for doc in activity.find({"entityId": {"$exists": True, "$ne": None}}, {"entityId": 1, "category": 1, "action": 1}):
    eid = str(doc["entityId"])
    if len(eid) == 24 and all(c in "0123456789abcdef" for c in eid):
        patterns[(doc.get("category"), "objectid24")] += 1
    elif eid.startswith("comm_"):
        patterns[(doc.get("category"), "comm_prefix")] += 1
    elif "_" in eid and not eid.startswith("comm_"):
        patterns[(doc.get("category"), "custom_with_underscore")] += 1
    else:
        patterns[(doc.get("category"), "other")] += 1

# For document/file_uploaded: compare entityId vs details.fileId
file_uploaded = list(activity.find({"category": "document", "action": "file_uploaded"}, {"entityId": 1, "details.fileId": 1}).limit(5))
file_uploaded_stats = {
    "count": activity.count_documents({"category": "document", "action": "file_uploaded"}),
    "hasDetailsFileId": activity.count_documents({"category": "document", "action": "file_uploaded", "details.fileId": {"$exists": True, "$ne": None}}),
    "entityIdEqualsDetailsFileId": 0,
    "entityIdDiffDetailsFileId": 0,
    "entityIdOnly": 0,
}
for doc in activity.find({"category": "document", "action": "file_uploaded"}, {"entityId": 1, "details.fileId": 1}):
    eid = doc.get("entityId")
    fid = (doc.get("details") or {}).get("fileId")
    if fid and eid == fid:
        file_uploaded_stats["entityIdEqualsDetailsFileId"] += 1
    elif fid and eid and eid != fid:
        file_uploaded_stats["entityIdDiffDetailsFileId"] += 1
    elif eid and not fid:
        file_uploaded_stats["entityIdOnly"] += 1

# communication activities: entityId to communications
comm_stats = Counter()
for doc in activity.find({"category": "communication"}, {"entityId": 1, "action": 1}):
    eid = str(doc.get("entityId") or "")
    if eid.startswith("comm_"):
        comm_stats["entityId_comm_prefix"] += 1
        found = db["communications"].count_documents({"communicationId": eid})
        comm_stats["found_by_communicationId" if found else "missing_by_communicationId"] += 1
    elif len(eid) == 24:
        comm_stats["entityId_objectid24"] += 1
        try:
            found = db["communications"].count_documents({"_id": ObjectId(eid)})
        except Exception:
            found = 0
        comm_stats["found_by_mongo_id" if found else "missing_by_mongo_id"] += 1
    else:
        comm_stats["entityId_other"] += 1

# where do unmatched 24-char entityIds live?
unmatched_collections = Counter()
checked = 0
for doc in activity.find({"entityId": {"$exists": True}}, {"entityId": 1, "category": 1, "action": 1}):
    eid = str(doc["entityId"])
    if len(eid) != 24:
        continue
    try:
        oid = ObjectId(eid)
    except Exception:
        continue
    matched = False
    for coll in db.list_collection_names():
        if coll == "case_activity_log":
            continue
        if db[coll].count_documents({"_id": oid}, limit=1):
            unmatched_collections[f"{coll}._id"] += 1
            matched = True
            break
    if not matched:
        unmatched_collections["nowhere"] += 1
    checked += 1

out = Path(__file__).resolve().parents[2] / "analyzeData" / "output" / "activity_linkage_deep_dive.json"
payload = {
    "entityIdPatternsByCategory": {f"{k[0]}::{k[1]}": v for k, v in patterns.items()},
    "fileUploadedStats": file_uploaded_stats,
    "fileUploadedSamples": file_uploaded,
    "communicationEntityIdStats": dict(comm_stats),
    "objectId24EntityIdResolution": dict(unmatched_collections),
    "objectId24Checked": checked,
}
out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
print(out)
