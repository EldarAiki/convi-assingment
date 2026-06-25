"""Resolve communication activity entityId links."""

import json
import re
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

import os

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
db = MongoClient(os.getenv("MONGODB_URL"))["convi-assessment"]
act = db["case_activity_log"]
comms = db["communications"]

prefixes = Counter()
entity_samples = []
for doc in act.find({"category": "communication", "entityId": {"$exists": True}}, {"entityId": 1, "action": 1, "details": 1}):
    eid = str(doc["entityId"])
    match = re.match(r"^([^_]+)_", eid)
    prefixes[match.group(1) if match else "none"] += 1
    if len(entity_samples) < 12:
        entity_samples.append(
            {
                "entityId": eid,
                "action": doc.get("action"),
                "matchesCommunicationId": bool(comms.find_one({"communicationId": eid})),
                "detailKeys": list((doc.get("details") or {}).keys()),
            }
        )

detail_keys = Counter()
for doc in act.find({"category": "communication"}, {"details": 1}):
    detail_keys.update((doc.get("details") or {}).keys())

match_by_action = {}
for action in ["email_sent", "email_received", "whatsapp_sent", "voice_call_completed", "email_documents_received"]:
    counts = Counter()
    for doc in act.find({"category": "communication", "action": action, "entityId": {"$exists": True}}, {"entityId": 1}):
        eid = str(doc["entityId"])
        if comms.find_one({"communicationId": eid}):
            counts["matches_communicationId"] += 1
        else:
            counts["missing"] += 1
    match_by_action[action] = dict(counts)

# Is there a details.* pointer like fileId?
candidate_fields = ["communicationId", "messageId", "draftId", "commId", "threadId"]
field_matches = Counter()
for doc in act.find({"category": "communication"}, {"details": 1, "entityId": 1}):
    details = doc.get("details") or {}
    for field in candidate_fields:
        value = details.get(field)
        if not value:
            continue
        value = str(value)
        if comms.find_one({"communicationId": value}):
            field_matches[f"details.{field}->communicationId"] += 1
        elif comms.find_one({"communicationId": doc.get("entityId")}):
            field_matches["entityId->communicationId_when_field_present"] += 1

# Compare file pattern: entityId suffix equals details.fileId?
file_pattern = Counter()
for doc in act.find({"category": "document", "action": "file_uploaded"}, {"entityId": 1, "details.fileId": 1}).limit(500):
    eid = str(doc.get("entityId") or "")
    fid = str((doc.get("details") or {}).get("fileId") or "")
    if eid == f"file_{fid}":
        file_pattern["entityId_is_file_prefix_plus_fileId"] += 1
    elif eid.endswith(fid):
        file_pattern["entityId_suffix_equals_fileId"] += 1
    else:
        file_pattern["other"] += 1

# comm pattern: entityId should equal communicationId directly?
comm_pattern = Counter()
for doc in act.find({"category": "communication", "entityId": {"$exists": True}}, {"entityId": 1}):
    eid = str(doc["entityId"])
    if eid.startswith("comm_") and comms.find_one({"communicationId": eid}):
        comm_pattern["entityId_is_communicationId"] += 1
    elif eid.startswith("comm_"):
        comm_pattern["comm_prefix_but_missing_in_communications"] += 1
    else:
        comm_pattern["non_comm_prefix"] += 1

out = {
    "entityIdPrefixes": dict(prefixes),
    "entityIdSamples": entity_samples,
    "communicationDetailKeys": dict(detail_keys),
    "matchByAction": match_by_action,
    "detailsFieldMatches": dict(field_matches),
    "fileEntityPatternSample500": dict(file_pattern),
    "communicationEntityPattern": dict(comm_pattern),
    "communicationIdFormatSamples": [
        d.get("communicationId") for d in comms.find({}, {"communicationId": 1}).limit(5)
    ],
}

output = Path(__file__).resolve().parents[2] / "analyzeData" / "output" / "communication_activity_links.json"
output.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print(output)
