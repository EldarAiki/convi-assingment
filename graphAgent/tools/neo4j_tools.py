"""Neo4j-backed tools for the case reasoning agent."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from clients.neo4j_client import Neo4jReadClient
from clients.mongo_client import MongoReadClient
from tools.case_types import expand_case_type_filter, normalize_token
from tools.outcomes import explain_outcome_from_projection, load_benchmarks_from_projections


class SearchCasesInput(BaseModel):
    query: str | None = Field(default=None, description="Free-text search on case name, injury, or digest")
    case_type: str | None = Field(
        default=None,
        description="Filter by caseType or classifiedCaseType (e.g. liability, medical_negligence, car_accident_serious)",
    )
    outcome_band: str | None = Field(
        default=None,
        description="success | partial_success | failed | incomplete",
    )
    sla_status: str | None = Field(default=None, description="on_track | overdue | at_risk")
    limit: int = Field(default=10, ge=1, le=25)


class CaseIdInput(BaseModel):
    case_id: str = Field(description="The caseId to look up")


class SearchInjuryCasesInput(BaseModel):
    injury_query: str | None = Field(
        default=None,
        description="Injury text to search (Hebrew or English), e.g. 'שבר בקרסול', 'back injury', 'CRPS'",
    )
    anchor_case_id: str | None = Field(
        default=None,
        description="Optional caseId to find cases with similar injuries (shared body parts or narrative overlap)",
    )
    body_part: str | None = Field(
        default=None,
        description="Optional filter on structured injuredBodyParts values",
    )
    outcome_band: str | None = Field(
        default=None,
        description="success | partial_success | failed | incomplete",
    )
    limit: int = Field(default=10, ge=1, le=25)


class CompareInjuryCasesInput(BaseModel):
    case_id_a: str = Field(description="First caseId to compare")
    case_id_b: str = Field(description="Second caseId to compare")


def build_neo4j_tools(neo4j: Neo4jReadClient, mongo: MongoReadClient | None = None) -> list[StructuredTool]:
    benchmarks_cache: dict[str, dict[str, float]] | None = None

    def _benchmarks() -> dict[str, dict[str, float]]:
        nonlocal benchmarks_cache
        if benchmarks_cache is not None:
            return benchmarks_cache
        if mongo is None:
            benchmarks_cache = {"_all": {"p40": 0.0, "p75": 0.0, "median": 0.0}}
            return benchmarks_cache
        projections = list(mongo.db["case_financial_projections"].find({"status": "current"}))
        benchmarks_cache = load_benchmarks_from_projections(projections)
        return benchmarks_cache

    def list_case_types() -> str:
        cypher = """
        MATCH (c:Case)
        OPTIONAL MATCH (c)-[:HAS_PROJECTION]->(p:FinancialProjection)
        WITH coalesce(c.caseType, p.classifiedCaseType) AS caseType,
             c.caseType AS rawCaseType,
             p.classifiedCaseType AS classifiedCaseType,
             count(DISTINCT c) AS caseCount
        WHERE caseType IS NOT NULL
        RETURN rawCaseType, classifiedCaseType, caseType, caseCount
        ORDER BY caseCount DESC, caseType
        """
        rows = neo4j.query(cypher)
        return json.dumps({"count": len(rows), "caseTypes": rows}, ensure_ascii=False)

    def search_cases(
        query: str | None = None,
        case_type: str | None = None,
        outcome_band: str | None = None,
        sla_status: str | None = None,
        limit: int = 10,
    ) -> str:
        cypher = """
        MATCH (c:Case)
        OPTIONAL MATCH (c)-[:HAS_PROJECTION]->(p:FinancialProjection)
        WHERE 1=1
        """
        params: dict[str, Any] = {"limit": limit}

        if query:
            query_norm = normalize_token(query)
            cypher += """
            AND (
                toLower(coalesce(c.caseName, '')) CONTAINS toLower($query)
                OR toLower(coalesce(c.searchDigest, '')) CONTAINS toLower($query)
                OR toLower(coalesce(p.mainInjury, '')) CONTAINS toLower($query)
                OR toLower(coalesce(c.mainInjury, '')) CONTAINS toLower($query)
                OR toLower(coalesce(c.injurySearchText, '')) CONTAINS toLower($query)
                OR ANY(part IN coalesce(c.injuredBodyParts, []) WHERE toLower(part) CONTAINS toLower($query))
                OR toLower(coalesce(p.clientName, '')) CONTAINS toLower($query)
                OR toLower(coalesce(c.caseType, '')) CONTAINS toLower($query)
                OR toLower(coalesce(p.classifiedCaseType, '')) CONTAINS toLower($query)
                OR toLower(coalesce(p.caseSummary, '')) CONTAINS toLower($query)
                OR replace(toLower(coalesce(c.caseType, '')), '_', ' ') CONTAINS toLower($query)
                OR replace(toLower(coalesce(p.classifiedCaseType, '')), '_', ' ') CONTAINS toLower($query)
                OR toLower(coalesce(c.caseType, '')) CONTAINS $queryNorm
                OR toLower(coalesce(p.classifiedCaseType, '')) CONTAINS $queryNorm
            )
            """
            params["query"] = query
            params["queryNorm"] = query_norm

        if case_type:
            expanded = expand_case_type_filter(case_type)
            params["caseTypes"] = expanded
            params["caseTypeRaw"] = case_type
            params["caseTypeNorm"] = normalize_token(case_type)
            cypher += """
            AND (
                c.caseType IN $caseTypes
                OR p.classifiedCaseType IN $caseTypes
                OR toLower(coalesce(c.caseType, '')) CONTAINS toLower($caseTypeRaw)
                OR toLower(coalesce(p.classifiedCaseType, '')) CONTAINS toLower($caseTypeRaw)
                OR toLower(coalesce(c.caseType, '')) CONTAINS $caseTypeNorm
                OR toLower(coalesce(p.classifiedCaseType, '')) CONTAINS $caseTypeNorm
                OR replace(toLower(coalesce(c.caseType, '')), '_', ' ') CONTAINS toLower($caseTypeRaw)
                OR replace(toLower(coalesce(p.classifiedCaseType, '')), '_', ' ') CONTAINS toLower($caseTypeRaw)
            )
            """

        if outcome_band:
            cypher += " AND p.outcomeBand = $outcomeBand"
            params["outcomeBand"] = outcome_band

        if sla_status:
            cypher += " AND p.slaStatus = $slaStatus"
            params["slaStatus"] = sla_status

        cypher += """
        RETURN c.caseId AS caseId,
               c.caseName AS caseName,
               c.caseType AS caseType,
               p.classifiedCaseType AS classifiedCaseType,
               p.legalStage AS legalStage,
               p.outcomeBand AS outcomeBand,
               p.compensationMax AS compensationMax,
               p.slaStatus AS slaStatus,
               coalesce(c.mainInjury, p.mainInjury) AS mainInjury,
               c.injuredBodyParts AS injuredBodyParts
        ORDER BY coalesce(p.compensationMax, 0) DESC
        LIMIT $limit
        """
        rows = neo4j.query(cypher, params)
        payload = {
            "count": len(rows),
            "filtersApplied": {
                "query": query,
                "case_type": case_type,
                "case_type_expanded": expand_case_type_filter(case_type) if case_type else [],
                "outcome_band": outcome_band,
                "sla_status": sla_status,
            },
            "cases": rows,
        }
        if case_type and not rows:
            payload["hint"] = (
                "No matches. Call list_case_types to see canonical values "
                "(e.g. medical_negligence, liability, car_accident_serious)."
            )
        return json.dumps(payload, ensure_ascii=False)

    def get_case_overview(case_id: str) -> str:
        cypher = """
        MATCH (c:Case {caseId: $caseId})
        OPTIONAL MATCH (c)-[:HAS_PROJECTION]->(p:FinancialProjection)
        OPTIONAL MATCH (c)-[:HAS_PARTY]->(party:Party)
        RETURN c.caseId AS caseId,
               c.caseName AS caseName,
               c.caseType AS caseType,
               c.appStatus AS appStatus,
               c.appStage AS appStage,
               c.eventDate AS eventDate,
               c.injuredBodyParts AS injuredBodyParts,
               c.mainInjury AS caseMainInjury,
               c.injurySearchText AS injurySearchText,
               c.searchDigest AS searchDigest,
               p.legalStage AS legalStage,
               p.legalStageHebrew AS legalStageHebrew,
               p.caseSummary AS caseSummary,
               p.classifiedCaseType AS classifiedCaseType,
               p.compensationMax AS compensationMax,
               p.stageProgress AS stageProgress,
               p.slaStatus AS slaStatus,
               p.outcomeBand AS outcomeBand,
               p.outcomeReasons AS outcomeReasons,
               p.mainInjury AS projectionMainInjury,
               p.accidentDate AS accidentDate,
               p.firstInsuranceContactDate AS firstInsuranceContactDate,
               collect(DISTINCT {
                   partyId: party.partyId,
                   name: party.name,
                   roleType: party.roleType
               }) AS parties
        """
        rows = neo4j.query(cypher, {"caseId": case_id})
        if not rows:
            return json.dumps({"found": False, "caseId": case_id}, ensure_ascii=False)
        row = rows[0]
        return json.dumps({"found": True, "case": row, "parties": row.pop("parties", [])}, ensure_ascii=False)

    def get_case_outcome(case_id: str) -> str:
        cypher = """
        MATCH (c:Case {caseId: $caseId})-[:HAS_PROJECTION]->(p:FinancialProjection)
        RETURN c.caseId AS caseId,
               c.caseName AS caseName,
               p.outcomeBand AS outcomeBand,
               p.outcomeReasons AS outcomeReasons,
               p.compensationMax AS compensationMax,
               p.stageProgress AS stageProgress,
               p.isTerminalStage AS isTerminalStage,
               p.timingOverdue AS timingOverdue,
               p.slaStatus AS slaStatus,
               p.legalStage AS legalStage,
               p.classifiedCaseType AS classifiedCaseType
        """
        rows = neo4j.query(cypher, {"caseId": case_id})
        if not rows:
            return json.dumps({"found": False, "caseId": case_id}, ensure_ascii=False)

        payload = rows[0]
        if mongo is not None:
            projection_doc = mongo.find_one(
                "case_financial_projections",
                {"caseId": case_id, "status": "current"},
            )
            if projection_doc:
                explained = explain_outcome_from_projection(projection_doc, _benchmarks())
                payload["thresholds"] = {
                    "success": explained.get("successThresholdUsed"),
                    "partial": explained.get("partialThresholdUsed"),
                }
        return json.dumps({"found": True, **payload}, ensure_ascii=False)

    def get_case_timeline(case_id: str) -> str:
        cypher = """
        MATCH (c:Case {caseId: $caseId})
        OPTIONAL MATCH (c)-[rd:RECEIVED_DOCUMENT]->(f:File)
        OPTIONAL MATCH (c)-[cm:COMMUNICATED]->(cp:Party)
        OPTIONAL MATCH (c)-[ac:ACTIVITY]->(ap:Party)
        WITH collect({
            kind: 'document',
            at: rd.timestamp,
            summary: coalesce(rd.summary, f.summaryShort),
            detail: f.fileName,
            id: rd.activityId
        }) AS docs,
        collect({
            kind: 'communication',
            at: cm.sentAt,
            summary: cm.bodyPreview,
            detail: cm.type + ' / ' + coalesce(cm.direction, ''),
            id: cm.communicationId
        }) AS comms,
        collect({
            kind: 'activity',
            at: ac.timestamp,
            summary: ac.summary,
            detail: ac.category + ' / ' + coalesce(ac.action, ''),
            id: ac.activityId
        }) AS acts
        RETURN docs + comms + acts AS events
        """
        rows = neo4j.query(cypher, {"caseId": case_id})
        if not rows:
            return json.dumps({"found": False, "caseId": case_id}, ensure_ascii=False)

        events = rows[0].get("events") or []
        events = [event for event in events if event.get("at") or event.get("summary")]
        events.sort(key=lambda item: str(item.get("at") or ""))
        return json.dumps(
            {"found": True, "caseId": case_id, "eventCount": len(events), "events": events[:100]},
            ensure_ascii=False,
        )

    def search_injury_cases(
        injury_query: str | None = None,
        anchor_case_id: str | None = None,
        body_part: str | None = None,
        outcome_band: str | None = None,
        limit: int = 10,
    ) -> str:
        if not injury_query and not anchor_case_id:
            return json.dumps(
                {
                    "count": 0,
                    "error": "Provide injury_query and/or anchor_case_id",
                },
                ensure_ascii=False,
            )

        if anchor_case_id and not injury_query:
            cypher = """
            MATCH (anchor:Case {caseId: $anchorCaseId})
            OPTIONAL MATCH (anchor)-[:HAS_PROJECTION]->(ap:FinancialProjection)
            WITH anchor, ap, coalesce(anchor.mainInjury, ap.mainInjury) AS anchorInjury
            MATCH (c:Case)
            WHERE c.caseId <> anchor.caseId
            OPTIONAL MATCH (c)-[:HAS_PROJECTION]->(p:FinancialProjection)
            WITH c, p, anchor, anchorInjury
            WHERE (
                (
                    size(coalesce(anchor.injuredBodyParts, [])) > 0
                    AND ANY(part IN coalesce(c.injuredBodyParts, []) WHERE part IN coalesce(anchor.injuredBodyParts, []))
                )
                OR (
                    anchorInjury IS NOT NULL
                    AND (
                        toLower(coalesce(c.injurySearchText, '')) CONTAINS toLower(anchorInjury)
                        OR toLower(coalesce(c.mainInjury, '')) CONTAINS toLower(anchorInjury)
                        OR toLower(coalesce(p.caseSummary, '')) CONTAINS toLower(anchorInjury)
                    )
                )
            )
            """
            params: dict[str, Any] = {"anchorCaseId": anchor_case_id, "limit": limit}
        else:
            cypher = """
            MATCH (c:Case)
            OPTIONAL MATCH (c)-[:HAS_PROJECTION]->(p:FinancialProjection)
            WITH c, p
            WHERE (
                toLower(coalesce(c.injurySearchText, '')) CONTAINS toLower($injuryQuery)
                OR toLower(coalesce(c.mainInjury, '')) CONTAINS toLower($injuryQuery)
                OR toLower(coalesce(p.mainInjury, '')) CONTAINS toLower($injuryQuery)
                OR toLower(coalesce(p.caseSummary, '')) CONTAINS toLower($injuryQuery)
                OR toLower(coalesce(c.eventDescription, '')) CONTAINS toLower($injuryQuery)
                OR toLower(coalesce(c.damageDescription, '')) CONTAINS toLower($injuryQuery)
                OR ANY(part IN coalesce(c.injuredBodyParts, []) WHERE toLower(part) CONTAINS toLower($injuryQuery))
            )
            """
            params = {"injuryQuery": injury_query, "limit": limit}

            if anchor_case_id:
                cypher = """
                MATCH (anchor:Case {caseId: $anchorCaseId})
                OPTIONAL MATCH (anchor)-[:HAS_PROJECTION]->(ap:FinancialProjection)
                WITH anchor, ap
                MATCH (c:Case)
                WHERE c.caseId <> anchor.caseId
                OPTIONAL MATCH (c)-[:HAS_PROJECTION]->(p:FinancialProjection)
                WITH c, p, anchor
                WHERE (
                    toLower(coalesce(c.injurySearchText, '')) CONTAINS toLower($injuryQuery)
                    OR toLower(coalesce(c.mainInjury, '')) CONTAINS toLower($injuryQuery)
                    OR toLower(coalesce(p.mainInjury, '')) CONTAINS toLower($injuryQuery)
                    OR toLower(coalesce(p.caseSummary, '')) CONTAINS toLower($injuryQuery)
                    OR ANY(part IN coalesce(c.injuredBodyParts, []) WHERE toLower(part) CONTAINS toLower($injuryQuery))
                    OR ANY(part IN coalesce(c.injuredBodyParts, []) WHERE part IN coalesce(anchor.injuredBodyParts, []))
                )
                """
                params["anchorCaseId"] = anchor_case_id

        if body_part:
            cypher += """
            AND ANY(part IN coalesce(c.injuredBodyParts, []) WHERE toLower(part) CONTAINS toLower($bodyPart))
            """
            params["bodyPart"] = body_part

        if outcome_band:
            cypher += " AND p.outcomeBand = $outcomeBand"
            params["outcomeBand"] = outcome_band

        cypher += """
        RETURN c.caseId AS caseId,
               c.caseName AS caseName,
               c.caseType AS caseType,
               coalesce(c.mainInjury, p.mainInjury) AS mainInjury,
               c.injuredBodyParts AS injuredBodyParts,
               p.outcomeBand AS outcomeBand,
               p.compensationMax AS compensationMax,
               p.legalStage AS legalStage,
               p.slaStatus AS slaStatus
        ORDER BY coalesce(p.compensationMax, 0) DESC
        LIMIT $limit
        """
        rows = neo4j.query(cypher, params)
        return json.dumps(
            {
                "count": len(rows),
                "filtersApplied": {
                    "injury_query": injury_query,
                    "anchor_case_id": anchor_case_id,
                    "body_part": body_part,
                    "outcome_band": outcome_band,
                },
                "cases": rows,
            },
            ensure_ascii=False,
        )

    def compare_injury_cases(case_id_a: str, case_id_b: str) -> str:
        cypher = """
        MATCH (a:Case {caseId: $caseIdA})
        MATCH (b:Case {caseId: $caseIdB})
        OPTIONAL MATCH (a)-[:HAS_PROJECTION]->(pa:FinancialProjection)
        OPTIONAL MATCH (b)-[:HAS_PROJECTION]->(pb:FinancialProjection)
        RETURN {
            caseId: a.caseId,
            caseName: a.caseName,
            caseType: a.caseType,
            mainInjury: coalesce(a.mainInjury, pa.mainInjury),
            injuredBodyParts: a.injuredBodyParts,
            injurySearchText: a.injurySearchText,
            eventDescription: a.eventDescription,
            damageDescription: a.damageDescription,
            caseSummary: pa.caseSummary,
            outcomeBand: pa.outcomeBand,
            compensationMax: pa.compensationMax,
            legalStage: pa.legalStage,
            slaStatus: pa.slaStatus
        } AS caseA,
        {
            caseId: b.caseId,
            caseName: b.caseName,
            caseType: b.caseType,
            mainInjury: coalesce(b.mainInjury, pb.mainInjury),
            injuredBodyParts: b.injuredBodyParts,
            injurySearchText: b.injurySearchText,
            eventDescription: b.eventDescription,
            damageDescription: b.damageDescription,
            caseSummary: pb.caseSummary,
            outcomeBand: pb.outcomeBand,
            compensationMax: pb.compensationMax,
            legalStage: pb.legalStage,
            slaStatus: pb.slaStatus
        } AS caseB,
        [part IN coalesce(a.injuredBodyParts, []) WHERE part IN coalesce(b.injuredBodyParts, [])] AS sharedBodyParts
        """
        rows = neo4j.query(cypher, {"caseIdA": case_id_a, "caseIdB": case_id_b})
        if not rows:
            return json.dumps({"found": False, "caseIdA": case_id_a, "caseIdB": case_id_b}, ensure_ascii=False)
        row = rows[0]
        return json.dumps({"found": True, **row}, ensure_ascii=False)

    def get_outcome_benchmarks() -> str:
        benchmarks = _benchmarks()
        return json.dumps({"benchmarks": benchmarks}, ensure_ascii=False)

    return [
        StructuredTool.from_function(
            func=list_case_types,
            name="list_case_types",
            description=(
                "List all canonical caseType / classifiedCaseType values in the graph with counts. "
                "Use before search_cases when the user asks by category name."
            ),
        ),
        StructuredTool.from_function(
            func=search_cases,
            name="search_cases",
            description=(
                "Search cases by text, case type, outcome band, or SLA status. "
                "Case types are snake_case (e.g. medical_negligence, liability). "
                "If zero results, call list_case_types and retry with a canonical value."
            ),
            args_schema=SearchCasesInput,
        ),
        StructuredTool.from_function(
            func=get_case_overview,
            name="get_case_overview",
            description="Get case header, projection snapshot, parties, and outcome band.",
            args_schema=CaseIdInput,
        ),
        StructuredTool.from_function(
            func=get_case_outcome,
            name="get_case_outcome",
            description="Explain why a case is classified as success, partial_success, failed, or incomplete.",
            args_schema=CaseIdInput,
        ),
        StructuredTool.from_function(
            func=get_case_timeline,
            name="get_case_timeline",
            description="Get chronological documents, communications, and activities for a case.",
            args_schema=CaseIdInput,
        ),
        StructuredTool.from_function(
            func=search_injury_cases,
            name="search_injury_cases",
            description=(
                "Search or compare cases by injury: mainInjury, injuredBodyParts, caseSummary, "
                "and injurySearchText on Case. Use for injury-type questions; optional anchor_case_id "
                "finds similar injury profiles."
            ),
            args_schema=SearchInjuryCasesInput,
        ),
        StructuredTool.from_function(
            func=compare_injury_cases,
            name="compare_injury_cases",
            description=(
                "Compare two cases side-by-side on injury fields, outcomes, compensation, "
                "and shared injuredBodyParts."
            ),
            args_schema=CompareInjuryCasesInput,
        ),
        StructuredTool.from_function(
            func=get_outcome_benchmarks,
            name="get_outcome_benchmarks",
            description="Return compensation percentile benchmarks per classified case type.",
        ),
    ]
