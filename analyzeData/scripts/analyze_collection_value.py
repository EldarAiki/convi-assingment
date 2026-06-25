import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
db = MongoClient(os.getenv("MONGODB_URL"))["convi-assessment"]

out = Path(__file__).resolve().parents[1] / "output" / "collection_value_analysis.json"
r = {}

# --- conversations / messages ---
r["counts"] = {
    "cases": db["cases"].count_documents({}),
    "conversations": db["conversations"].count_documents({}),
    "messages": db["messages"].count_documents({}),
    "communications": db["communications"].count_documents({}),
    "activity_log": db["case_activity_log"].count_documents({}),
    "financial_projections": db["case_financial_projections"].count_documents({}),
}

r["cases_with_conversation"] = len(db["conversations"].distinct("caseId"))
r["cases_with_communication"] = len(db["communications"].distinct("caseId"))
r["cases_with_activity"] = len(db["case_activity_log"].distinct("caseId"))
r["cases_with_projection"] = len(db["case_financial_projections"].distinct("caseId"))

# message content length stats
msg_lens = list(
    db["messages"].aggregate(
        [
            {"$project": {"len": {"$strLenCP": {"$ifNull": ["$content", ""]}}, "role": 1, "sender": 1}},
            {
                "$group": {
                    "_id": "$role",
                    "n": {"$sum": 1},
                    "avgLen": {"$avg": "$len"},
                    "maxLen": {"$max": "$len"},
                }
            },
        ]
    )
)
r["message_by_role"] = msg_lens

# sample short vs long messages (metadata only, truncate content)
samples = []
for doc in db["messages"].find({}, {"content": 1, "role": 1, "sessionId": 1, "createdAt": 1}).sort("createdAt", -1).limit(8):
    c = doc.get("content") or ""
    samples.append({
        "role": doc.get("role"),
        "len": len(c),
        "preview": c[:120],
        "sessionId": doc.get("sessionId", "")[:40],
    })
r["message_samples"] = samples

# conversations: messageCount distribution
r["conversation_message_counts"] = list(
    db["conversations"].aggregate(
        [
            {"$group": {"_id": "$messageCount", "n": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
    )
)

r["conversation_status"] = list(
    db["conversations"].aggregate(
        [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
    )
)

# link conversations to cases with caseType
r["conversation_case_types"] = list(
    db["conversations"].aggregate(
        [
            {"$lookup": {"from": "cases", "localField": "caseId", "foreignField": "caseId", "as": "case"}},
            {"$unwind": {"path": "$case", "preserveNullAndEmptyArrays": True}},
            {"$group": {"_id": "$case.caseType", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
        ]
    )
)

# --- case_activity_log value ---
r["activity_by_category"] = list(
    db["case_activity_log"].aggregate(
        [{"$group": {"_id": "$category", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}]
    )
)

r["activity_cases_per_case"] = list(
    db["case_activity_log"].aggregate(
        [
            {"$group": {"_id": "$caseId", "n": {"$sum": 1}}},
            {"$group": {"_id": None, "avg": {"$avg": "$n"}, "min": {"$min": "$n"}, "max": {"$max": "$n"}, "cases": {"$sum": 1}}},
        ]
    )
)

# activity with rich details types
r["activity_with_summary"] = db["case_activity_log"].count_documents({"summary": {"$exists": True, "$ne": ""}})

# --- financial projections ---
proj = db["case_financial_projections"].find_one({"status": "current"})
if proj:
    r["projection_top_keys"] = list(proj.keys())
    r["projection_metadata"] = proj.get("metadata")
    p = proj.get("projection") or {}
    r["projection_inner_keys"] = list(p.keys())[:30]
    financials = p.get("financials") or {}
    r["projection_sample_snippets"] = {
        "caseSummary_len": len(p.get("caseSummary") or ""),
        "caseSummary_preview": (p.get("caseSummary") or "")[:250],
        "classification": p.get("classification"),
        "caseStage": p.get("caseStage"),
        "keyDates": p.get("keyDates"),
        "financials_keys": list(financials.keys())[:15] if isinstance(financials, dict) else [],
    }

r["projections_per_case"] = list(
    db["case_financial_projections"].aggregate(
        [
            {"$group": {"_id": "$caseId", "versions": {"$sum": 1}}},
            {"$group": {"_id": None, "avgVersions": {"$avg": "$versions"}, "maxVersions": {"$max": "$versions"}, "cases": {"$sum": 1}}},
        ]
    )
)

r["projection_status_counts"] = list(
    db["case_financial_projections"].aggregate(
        [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
    )
)

out.write_text(json.dumps(r, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(out)
