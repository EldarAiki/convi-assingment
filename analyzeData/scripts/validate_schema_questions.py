import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
db = MongoClient(os.getenv("MONGODB_URL"))["convi-assessment"]

out = Path(__file__).resolve().parents[1] / "output" / "schema_validation.json"
result = {}

# messages -> conversations linkage
result["messages_total"] = db["messages"].count_documents({})
result["messages_with_sessionId"] = db["messages"].count_documents(
    {"sessionId": {"$exists": True, "$ne": None}}
)
result["conversations_total"] = db["conversations"].count_documents({})
result["communications_total"] = db["communications"].count_documents({})

result["conversation_fields_sample"] = db["conversations"].find_one(
    {}, {"sessionId": 1, "caseId": 1, "messageCount": 1, "userId": 1, "clerkUserId": 1}
)

# do messages.sessionId match conversations.sessionId?
msg_sessions = set(
    db["messages"].distinct("sessionId")
)
conv_sessions = set(
    db["conversations"].distinct("sessionId")
)
result["message_sessions"] = len(msg_sessions)
result["conversation_sessions"] = len(conv_sessions)
result["sessions_in_both"] = len(msg_sessions & conv_sessions)
result["sessions_only_in_messages"] = len(msg_sessions - conv_sessions)

# communications vs conversations overlap
result["comm_types"] = list(
    db["communications"].aggregate(
        [
            {"$group": {"_id": "$type", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
        ]
    )
)

# activity log categories/actions related to injury/accident
result["activity_categories"] = list(
    db["case_activity_log"].aggregate(
        [
            {"$group": {"_id": {"category": "$category", "action": "$action"}, "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
            {"$limit": 25},
        ]
    )
)

# case stages and statuses
result["case_status"] = list(
    db["cases"].aggregate(
        [
            {"$group": {"_id": {"status": "$status", "stage": "$stage"}, "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
        ]
    )
)

result["contact_types"] = list(
    db["contacts"].aggregate(
        [
            {"$group": {"_id": "$contactType", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
        ]
    )
)

# cases injury/accident related fields
sample_case = db["cases"].find_one(
    {},
    {
        "caseType": 1,
        "eventDate": 1,
        "eventDescription": 1,
        "damageDescription": 1,
        "medicalInfo": 1,
        "stage": 1,
        "status": 1,
    },
)
result["sample_case_fields"] = sample_case

result["case_types"] = list(
    db["cases"].aggregate(
        [{"$group": {"_id": "$caseType", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}]
    )
)

# communications have sessionId?
result["comm_with_sessionId"] = db["communications"].count_documents(
    {"metadata.sessionId": {"$exists": True, "$ne": None}}
)

out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
print(out)
