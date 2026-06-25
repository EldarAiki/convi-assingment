import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
files = MongoClient(os.getenv("MONGODB_URL"))["convi-assessment"]["files"]
out = Path(__file__).resolve().parents[1] / "output" / "extracted_text_stats.json"

summary_stats = list(
    files.aggregate(
        [
            {
                "$match": {
                    "processedData.ocr_metadata.summary": {
                        "$exists": True,
                        "$type": "string",
                    }
                }
            },
            {
                "$project": {
                    "len": {"$strLenCP": "$processedData.ocr_metadata.summary"}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "count": {"$sum": 1},
                    "nonZero": {"$sum": {"$cond": [{"$gt": ["$len", 0]}, 1, 0]}},
                    "avgLen": {"$avg": "$len"},
                    "maxLen": {"$max": "$len"},
                }
            },
        ]
    )
)

payload = {
    "extractedText": list(
        files.aggregate(
            [
                {"$match": {"extractedText": {"$exists": True, "$type": "string"}}},
                {"$project": {"len": {"$strLenCP": "$extractedText"}}},
                {
                    "$group": {
                        "_id": None,
                        "count": {"$sum": 1},
                        "nonZero": {
                            "$sum": {"$cond": [{"$gt": ["$len", 0]}, 1, 0]}
                        },
                        "avgLen": {"$avg": "$len"},
                        "maxLen": {"$max": "$len"},
                    }
                },
            ]
        )
    ),
    "ocr_metadata_summary": summary_stats,
    "combined_text": list(
        files.aggregate(
            [
                {
                    "$match": {
                        "processedData.ocr_metadata.combined_text": {
                            "$exists": True,
                            "$type": "string",
                        }
                    }
                },
                {
                    "$project": {
                        "len": {
                            "$strLenCP": "$processedData.ocr_metadata.combined_text"
                        }
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "count": {"$sum": 1},
                        "nonZero": {
                            "$sum": {"$cond": [{"$gt": ["$len", 0]}, 1, 0]}
                        },
                        "avgLen": {"$avg": "$len"},
                        "maxLen": {"$max": "$len"},
                    }
                },
            ]
        )
    ),
    "total_files": files.count_documents({}),
}

out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(out)
