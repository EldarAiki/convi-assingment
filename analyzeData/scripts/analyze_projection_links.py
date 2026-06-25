"""Explore linkable fields in case_financial_projections."""

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
db = MongoClient(os.getenv("MONGODB_URL"))["convi-assessment"]
proj = db["case_financial_projections"]

EXCLUDED_PREFIXES = {"warnings", "errors"}


def walk(obj, prefix="", fields=None):
    if fields is None:
        fields = defaultdict(set)
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            if any(path.startswith(p) for p in EXCLUDED_PREFIXES):
                continue
            fields[path].add(type(value).__name__)
            if isinstance(value, dict):
                walk(value, path, fields)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                walk(value[0], f"{path}[]", fields)
    return fields


def sample_values(path: str, limit: int = 5) -> list:
    values = []
    for doc in proj.find({"status": "current"}, {f"projection.{path}": 1}).limit(50):
        parts = path.split(".")
        current = doc.get("projection") or {}
        for part in parts:
            if part.endswith("[]"):
                part = part[:-2]
                if isinstance(current, dict) and part in current:
                    current = current[part]
                    if isinstance(current, list) and current:
                        current = current[0]
                    else:
                        current = None
                else:
                    current = None
                    break
            elif isinstance(current, dict):
                current = current.get(part)
            else:
                current = None
                break
        if current is not None and current != "" and current != []:
            if isinstance(current, (str, int, float, bool)):
                values.append(current)
            elif len(values) < limit:
                values.append(str(current)[:120])
        if len(values) >= limit:
            break
    return values


# field map from projection subtree
fields = walk(proj.find_one({"status": "current"}).get("projection") or {})

# focus paths likely to link entities
candidate_paths = [
    p
    for p in sorted(fields.keys())
    if any(
        token in p.lower()
        for token in [
            "insurance",
            "company",
            "client",
            "lawyer",
            "doctor",
            "hospital",
            "hmo",
            "employer",
            "party",
            "name",
            "id",
            "case",
            "file",
            "document",
            "contact",
        ]
    )
]

candidates = {}
for path in candidate_paths:
    samples = sample_values(path.replace("[]", ""), limit=4)
    if samples:
        candidates[path] = {
            "types": sorted(fields[path]),
            "samples": samples,
        }

# specific: insuranceCompany
insurance_stats = {
    "withInsuranceCompany": proj.count_documents(
        {"status": "current", "projection.caseData.insuranceCompany": {"$exists": True, "$ne": None, "$ne": ""}}
    ),
    "totalCurrent": proj.count_documents({"status": "current"}),
}
insurance_samples = sample_values("caseData.insuranceCompany", 8)

# compare insuranceCompany to contacts/cases
insurance_names = []
for doc in proj.find({"status": "current"}, {"projection.caseData.insuranceCompany": 1, "caseId": 1}).limit(70):
    name = (doc.get("projection") or {}).get("caseData", {}).get("insuranceCompany")
    if name:
        insurance_names.append({"caseId": doc.get("caseId"), "insuranceCompany": name})

# other caseData keys
case_data_keys = Counter()
for doc in proj.find({"status": "current"}, {"projection.caseData": 1}):
    cd = (doc.get("projection") or {}).get("caseData") or {}
    if isinstance(cd, dict):
        case_data_keys.update(cd.keys())

# checklist, medicalFollowup, combinedComponents top keys
for section in ["checklist", "medicalFollowup", "combinedComponents", "timing", "quarterlyTargets"]:
    section_keys = Counter()
    for doc in proj.find({"status": "current"}, {f"projection.{section}": 1}).limit(70):
        val = (doc.get("projection") or {}).get(section)
        if isinstance(val, dict):
            section_keys.update(val.keys())
        elif isinstance(val, list) and val and isinstance(val[0], dict):
            section_keys.update(val[0].keys())
    candidates[f"_section_{section}_keys"] = {"keys": dict(section_keys.most_common(15))}

report = {
    "insuranceStats": insurance_stats,
    "insuranceSamples": insurance_samples,
    "caseDataKeys": dict(case_data_keys.most_common(30)),
    "linkableFieldCandidates": candidates,
    "insuranceByCaseSample": insurance_names[:10],
}

out = Path(__file__).resolve().parents[2] / "analyzeData" / "output" / "projection_links_report.json"
out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(out)
