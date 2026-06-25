"""Map MongoDB documents to Neo4j node and relationship payloads."""

from __future__ import annotations

from typing import Any

from ingest.utils import (
    build_injury_search_text,
    build_search_digest,
    clean_props,
    get_nested,
    normalize_body_parts,
    normalize_party_name,
    party_id_from_name,
    stringify_id,
    to_iso,
    truncate,
)

EXCLUDED_ACTIVITY_CATEGORIES = {"communication", "conversation"}


def map_case(doc: dict[str, Any], projection: dict[str, Any] | None) -> dict[str, Any]:
    projection_summary = get_nested(projection or {}, "projection.caseSummary")
    accident_date = get_nested(projection or {}, "projection.keyDates.accidentDate")
    main_injury = get_nested(projection or {}, "projection.caseData.mainInjury")
    body_parts = normalize_body_parts(get_nested(doc, "medicalInfo.injuredBodyParts"))
    event_description = doc.get("eventDescription")
    damage_description = doc.get("damageDescription")

    return clean_props(
        {
            "caseId": doc.get("caseId"),
            "mongoId": stringify_id(doc.get("_id")),
            "caseType": doc.get("caseType"),
            "caseName": doc.get("caseName"),
            "appStatus": doc.get("status"),
            "appStage": doc.get("stage"),
            "eventDate": to_iso(doc.get("eventDate")),
            "injuredBodyParts": body_parts,
            "mainInjury": main_injury,
            "injurySearchText": build_injury_search_text(
                main_injury,
                body_parts,
                event_description,
                damage_description,
                projection_summary,
            ),
            "hmo": get_nested(doc, "medicalInfo.hmo"),
            "eventDescription": event_description,
            "damageDescription": damage_description,
            "fileCount": doc.get("documentCount"),
            "searchDigest": build_search_digest(doc.get("caseType"), projection_summary, accident_date),
        }
    )


def map_client_party(doc: dict[str, Any]) -> dict[str, Any] | None:
    client_id = doc.get("clientId")
    client_info = doc.get("clientInfo") or {}
    if not client_id and not client_info.get("name"):
        return None

    party_id = client_id or f"client:{doc.get('caseId')}"
    return clean_props(
        {
            "partyId": party_id,
            "partyKind": "person",
            "roleType": "client",
            "name": client_info.get("name"),
            "firstName": client_info.get("firstName"),
            "lastName": client_info.get("lastName"),
            "phone": client_info.get("phone"),
            "email": client_info.get("email"),
            "idNumber": client_info.get("idNumber"),
        }
    )


def map_contact_party(doc: dict[str, Any]) -> dict[str, Any]:
    party_id = doc.get("userId") or stringify_id(doc.get("_id"))
    organization_name = doc.get("organizationName")
    return clean_props(
        {
            "partyId": party_id,
            "partyKind": "organization" if organization_name else "person",
            "roleType": doc.get("contactType") or "contact",
            "name": doc.get("name"),
            "firstName": doc.get("firstName"),
            "lastName": doc.get("lastName"),
            "phone": doc.get("phone") or doc.get("phoneFormatted"),
            "email": doc.get("email"),
            "idNumber": doc.get("idNumber"),
            "organizationName": organization_name,
            "contactType": doc.get("contactType"),
            "mongoContactId": stringify_id(doc.get("_id")),
        }
    )


def map_organization_party(name: str, role_type: str = "insurer") -> dict[str, Any]:
    return clean_props(
        {
            "partyId": party_id_from_name(name, role_type),
            "partyKind": "organization",
            "roleType": role_type,
            "name": name.strip(),
            "normalizedName": normalize_party_name(name),
        }
    )


def map_expert_party(name: str, field: str | None = None) -> dict[str, Any]:
    return clean_props(
        {
            "partyId": party_id_from_name(name, "expert"),
            "partyKind": "person",
            "roleType": "expert",
            "name": name.strip(),
            "expertField": field,
            "normalizedName": normalize_party_name(name),
        }
    )


def map_file(doc: dict[str, Any]) -> dict[str, Any]:
    summary = get_nested(doc, "processedData.ocr_metadata.summary")
    extracted = doc.get("extractedText")
    text_length = len(extracted) if isinstance(extracted, str) else len(summary or "")

    return clean_props(
        {
            "fileId": stringify_id(doc.get("_id")),
            "caseId": doc.get("caseId"),
            "fileName": doc.get("fileName"),
            "fileType": doc.get("fileType"),
            "documentType": get_nested(doc, "processedData.document_type"),
            "documentCategory": get_nested(doc, "processedData.document_category"),
            "documentDate": get_nested(doc, "processedData.document_date"),
            "summaryShort": summary,
            "processingStatus": doc.get("processingStatus"),
            "gcsPath": doc.get("gcsPath"),
            "textLength": text_length,
        }
    )


def map_projection(
    doc: dict[str, Any],
    outcome_benchmarks: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    from ingest.outcomes import classify_projection_outcome

    outcome = classify_projection_outcome(doc, outcome_benchmarks)
    return clean_props(
        {
            "projectionId": stringify_id(doc.get("_id")),
            "caseId": doc.get("caseId"),
            "version": doc.get("version"),
            "status": doc.get("status"),
            "caseSummary": get_nested(doc, "projection.caseSummary"),
            "analysisDate": get_nested(doc, "projection.analysisDate"),
            "legalStage": get_nested(doc, "projection.caseStage.currentStage"),
            "legalStageHebrew": get_nested(doc, "projection.caseStage.currentStageHebrew"),
            "stageNumber": get_nested(doc, "projection.caseStage.stageNumber"),
            "daysInCurrentStage": get_nested(doc, "projection.caseStage.daysInCurrentStage"),
            "slaStatus": get_nested(doc, "projection.caseStage.slaStatus"),
            "classificationCategory": get_nested(doc, "projection.classification.category"),
            "classifiedCaseType": get_nested(doc, "projection.classification.classifiedCaseType"),
            "classificationConfidence": get_nested(doc, "projection.classification.confidence"),
            "accidentDate": get_nested(doc, "projection.keyDates.accidentDate"),
            "disabilityDeterminationDate": get_nested(doc, "projection.keyDates.disabilityDetermination"),
            "caseOpenedDate": get_nested(doc, "projection.keyDates.caseOpened"),
            "firstInsuranceContactDate": get_nested(doc, "projection.keyDates.firstInsuranceContact"),
            "estimatedCompensation": get_nested(doc, "projection.financials.estimatedCompensation"),
            "compensationMax": outcome.get("compensationMax"),
            "stageProgress": outcome.get("stageProgress"),
            "isTerminalStage": outcome.get("isTerminalStage"),
            "timingOverdue": outcome.get("timingOverdue"),
            "outcomeBand": outcome.get("outcomeBand"),
            "outcomeReasons": outcome.get("outcomeReasons"),
            "feePercentage": get_nested(doc, "projection.financials.feePercentage"),
            "mainInjury": get_nested(doc, "projection.caseData.mainInjury"),
            "occupation": get_nested(doc, "projection.caseData.occupation"),
            "claimNumber": get_nested(doc, "projection.caseData.claimNumber"),
            "clientName": get_nested(doc, "projection.clientName"),
            "generatedAt": to_iso(get_nested(doc, "metadata.generatedAt")),
        }
    )


def map_received_document_edge(doc: dict[str, Any], file_id: str) -> dict[str, Any] | None:
    case_id = doc.get("caseId")
    if not case_id or not file_id:
        return None
    return clean_props(
        {
            "fromId": case_id,
            "toId": file_id,
            "activityId": stringify_id(doc.get("_id")),
            "action": doc.get("action"),
            "summary": doc.get("summary"),
            "timestamp": to_iso(doc.get("timestamp")),
            "userId": doc.get("userId"),
            "userName": doc.get("userName"),
            "source": doc.get("source"),
        }
    )


def map_communicated_edge(doc: dict[str, Any], party_id: str) -> dict[str, Any] | None:
    case_id = doc.get("caseId")
    if not case_id or not party_id:
        return None
    return clean_props(
        {
            "fromId": case_id,
            "toId": party_id,
            "communicationId": doc.get("communicationId") or stringify_id(doc.get("_id")),
            "mongoId": stringify_id(doc.get("_id")),
            "type": doc.get("type"),
            "direction": doc.get("direction"),
            "bodyPreview": truncate(doc.get("bodyText"), 500),
            "status": doc.get("status"),
            "sentAt": to_iso(doc.get("sentAt") or doc.get("createdAt")),
            "fromName": get_nested(doc, "from.name"),
            "fromPhone": get_nested(doc, "from.phone"),
        }
    )


def map_activity_edge(doc: dict[str, Any], party_id: str) -> dict[str, Any] | None:
    case_id = doc.get("caseId")
    category = doc.get("category")
    if not case_id or not party_id or category in EXCLUDED_ACTIVITY_CATEGORIES:
        return None
    if category == "document":
        return None
    return clean_props(
        {
            "fromId": case_id,
            "toId": party_id,
            "activityId": stringify_id(doc.get("_id")),
            "category": category,
            "action": doc.get("action"),
            "summary": doc.get("summary"),
            "timestamp": to_iso(doc.get("timestamp")),
            "userId": doc.get("userId"),
            "userName": doc.get("userName"),
            "source": doc.get("source"),
        }
    )
