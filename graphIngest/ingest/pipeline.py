"""MongoDB → Neo4j ingestion pipeline (schema v1.2, edge-centric)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from pymongo import MongoClient

from config import BATCH_SIZE, MONGODB_URL, get_database_name
from ingest.mappers import (
    map_activity_edge,
    map_case,
    map_client_party,
    map_communicated_edge,
    map_contact_party,
    map_expert_party,
    map_file,
    map_organization_party,
    map_projection,
    map_received_document_edge,
)
from ingest.neo4j_client import Neo4jClient
from ingest.utils import get_nested, stringify_id

EXCLUDED_ACTIVITY = {"communication", "conversation"}


@dataclass
class IngestStats:
    nodes: Counter = field(default_factory=Counter)
    relationships: Counter = field(default_factory=Counter)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": dict(self.nodes),
            "relationships": dict(self.relationships),
        }


class IngestionPipeline:
    def __init__(self, neo4j: Neo4jClient | None = None, dry_run: bool = False):
        self.neo4j = neo4j
        self.dry_run = dry_run
        self.stats = IngestStats()
        self.client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=20000)
        self.db = self.client[get_database_name()]

        self.projections_by_case: dict[str, dict[str, Any]] = {}
        self.client_party_by_case: dict[str, str] = {}
        self.party_ids: set[str] = set()
        self.file_ids: set[str] = set()
        self.projection_ids: set[str] = set()
        self.outcome_benchmarks: dict[str, dict[str, float]] = {}

    def close(self) -> None:
        self.client.close()

    def run(self, clear: bool = False) -> IngestStats:
        self._load_reference_data()

        if self.neo4j and not self.dry_run:
            if clear:
                self.neo4j.clear_graph()
            self.neo4j.setup_schema()

        self._ingest_cases()
        self._ingest_parties()
        self._ingest_projections()
        self._ingest_files()
        self._ingest_projection_links()
        self._ingest_received_documents()
        self._ingest_communications()
        self._ingest_activities()
        return self.stats

    def _load_reference_data(self) -> None:
        from ingest.outcomes import build_benchmarks

        current_projections = list(self.db["case_financial_projections"].find({"status": "current"}))
        self.outcome_benchmarks = build_benchmarks(current_projections)
        for doc in current_projections:
            case_id = doc.get("caseId")
            if case_id:
                self.projections_by_case[case_id] = doc

    def _batch_merge_nodes(self, label: str, id_field: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        self.stats.nodes[label] += len(rows)
        if self.dry_run or not self.neo4j:
            return
        for index in range(0, len(rows), BATCH_SIZE):
            self.neo4j.merge_nodes(label, id_field, rows[index : index + BATCH_SIZE])

    def _batch_merge_rels(
        self,
        rel_type: str,
        from_label: str,
        from_id_field: str,
        to_label: str,
        to_id_field: str,
        rows: list[dict[str, Any]],
        rel_props: list[str] | None = None,
        merge_key: str | None = None,
    ) -> None:
        if not rows:
            return
        self.stats.relationships[rel_type] += len(rows)
        if self.dry_run or not self.neo4j:
            return
        for index in range(0, len(rows), BATCH_SIZE):
            self.neo4j.merge_relationships(
                rel_type,
                from_label,
                from_id_field,
                to_label,
                to_id_field,
                rows[index : index + BATCH_SIZE],
                rel_props,
                merge_key,
            )

    def _resolve_party_for_case(self, case_id: str, user_id: str | None) -> str | None:
        if user_id and user_id in self.party_ids:
            return user_id
        return self.client_party_by_case.get(case_id)

    def _ingest_cases(self) -> None:
        rows = []
        for doc in self.db["cases"].find({}):
            case_id = doc.get("caseId")
            if not case_id:
                continue
            rows.append(map_case(doc, self.projections_by_case.get(case_id)))
        self._batch_merge_nodes("Case", "caseId", rows)

    def _ingest_parties(self) -> None:
        parties: dict[str, dict[str, Any]] = {}
        has_party_rows: list[dict[str, Any]] = []

        for doc in self.db["cases"].find({}):
            case_id = doc.get("caseId")
            party = map_client_party(doc)
            if not case_id or not party:
                continue
            parties[party["partyId"]] = party
            self.client_party_by_case[case_id] = party["partyId"]
            has_party_rows.append(
                {"fromId": case_id, "toId": party["partyId"], "role": "client", "source": "cases"}
            )

        for doc in self.db["contacts"].find({}):
            party = map_contact_party(doc)
            parties[party["partyId"]] = party
            for case_id in doc.get("caseIds") or []:
                has_party_rows.append(
                    {
                        "fromId": case_id,
                        "toId": party["partyId"],
                        "role": party.get("roleType") or "contact",
                        "source": "contacts",
                    }
                )

        self.party_ids = set(parties.keys())
        self._batch_merge_nodes("Party", "partyId", list(parties.values()))
        self._batch_merge_rels(
            "HAS_PARTY", "Case", "caseId", "Party", "partyId", has_party_rows, ["role", "source"]
        )

    def _ingest_projections(self) -> None:
        rows = []
        rel_rows = []
        for doc in self.db["case_financial_projections"].find({"status": "current"}):
            mapped = map_projection(doc, self.outcome_benchmarks)
            projection_id = mapped.get("projectionId")
            case_id = mapped.get("caseId")
            if not projection_id or not case_id:
                continue
            rows.append(mapped)
            self.projection_ids.add(projection_id)
            rel_rows.append({"fromId": case_id, "toId": projection_id, "isCurrent": True})

        self._batch_merge_nodes("FinancialProjection", "projectionId", rows)
        self._batch_merge_rels(
            "HAS_PROJECTION",
            "Case",
            "caseId",
            "FinancialProjection",
            "projectionId",
            rel_rows,
            ["isCurrent"],
        )

    def _ingest_files(self) -> None:
        rows = []
        for doc in self.db["files"].find({}):
            mapped = map_file(doc)
            file_id = mapped.get("fileId")
            if not file_id:
                continue
            rows.append(mapped)
            self.file_ids.add(file_id)
        self._batch_merge_nodes("File", "fileId", rows)

    def _ingest_projection_links(self) -> None:
        extra_parties: dict[str, dict[str, Any]] = {}
        insurer_rows: list[dict[str, Any]] = []
        expert_rows: list[dict[str, Any]] = []
        track_rows: list[dict[str, Any]] = []
        subject_rows: list[dict[str, Any]] = []

        for doc in self.db["case_financial_projections"].find({"status": "current"}):
            projection_id = stringify_id(doc.get("_id"))
            case_id = doc.get("caseId")
            if not projection_id or not case_id:
                continue

            projection = doc.get("projection") or {}
            case_data = projection.get("caseData") or {}

            insurer_name = case_data.get("insuranceCompany")
            if insurer_name:
                party = map_organization_party(str(insurer_name), "insurer")
                extra_parties[party["partyId"]] = party
                insurer_rows.append(
                    {
                        "fromId": party["partyId"],
                        "toId": projection_id,
                        "claimNumber": case_data.get("claimNumber"),
                        "source": "projection",
                    }
                )

            experts = case_data.get("experts") or {}
            for side in ("ours", "court"):
                for expert in experts.get(side) or []:
                    if not isinstance(expert, dict):
                        continue
                    name = expert.get("name")
                    if not name:
                        continue
                    party = map_expert_party(str(name), expert.get("field"))
                    extra_parties[party["partyId"]] = party
                    expert_rows.append(
                        {
                            "fromId": party["partyId"],
                            "toId": projection_id,
                            "field": expert.get("field"),
                            "disability": expert.get("disability"),
                            "side": side,
                            "source": "projection",
                        }
                    )

            for track in (projection.get("caseStage") or {}).get("parallelTracks") or []:
                if not isinstance(track, dict):
                    continue
                track_type = track.get("trackType")
                if not track_type:
                    continue
                track_name = "המוסד לביטוח לאומי" if "ב\"ל" in str(track_type) or "ביטוח" in str(track_type) else str(track_type)
                party = map_organization_party(track_name, "insurer")
                extra_parties[party["partyId"]] = party
                track_rows.append(
                    {
                        "fromId": party["partyId"],
                        "toId": projection_id,
                        "trackType": track_type,
                        "currentStage": track.get("currentStage"),
                        "currentStageHebrew": track.get("currentStageHebrew"),
                        "stageNumber": track.get("stageNumber"),
                        "slaStatus": track.get("slaStatus"),
                    }
                )

            client_party_id = self.client_party_by_case.get(case_id)
            if client_party_id:
                subject_rows.append(
                    {"fromId": client_party_id, "toId": projection_id, "source": "projection"}
                )

        self.party_ids.update(extra_parties.keys())
        self._batch_merge_nodes("Party", "partyId", list(extra_parties.values()))
        self._batch_merge_rels(
            "INSURER_IN",
            "Party",
            "partyId",
            "FinancialProjection",
            "projectionId",
            insurer_rows,
            ["claimNumber", "source"],
        )
        self._batch_merge_rels(
            "EXPERT_IN",
            "Party",
            "partyId",
            "FinancialProjection",
            "projectionId",
            expert_rows,
            ["field", "disability", "side", "source"],
        )
        self._batch_merge_rels(
            "LEGAL_TRACK",
            "Party",
            "partyId",
            "FinancialProjection",
            "projectionId",
            track_rows,
            ["trackType", "currentStage", "currentStageHebrew", "stageNumber", "slaStatus"],
        )
        self._batch_merge_rels(
            "SUBJECT_OF",
            "Party",
            "partyId",
            "FinancialProjection",
            "projectionId",
            subject_rows,
            ["source"],
        )

    def _ingest_received_documents(self) -> None:
        rows = []
        for doc in self.db["case_activity_log"].find({"category": "document"}):
            file_id = stringify_id(get_nested(doc, "details.fileId"))
            if not file_id or file_id not in self.file_ids:
                continue
            edge = map_received_document_edge(doc, file_id)
            if edge:
                rows.append(edge)

            if len(rows) >= BATCH_SIZE:
                self._batch_merge_rels(
                    "RECEIVED_DOCUMENT",
                    "Case",
                    "caseId",
                    "File",
                    "fileId",
                    rows,
                    ["activityId", "action", "summary", "timestamp", "userId", "userName", "source"],
                    merge_key="activityId",
                )
                rows = []

        if rows:
            self._batch_merge_rels(
                "RECEIVED_DOCUMENT",
                "Case",
                "caseId",
                "File",
                "fileId",
                rows,
                ["activityId", "action", "summary", "timestamp", "userId", "userName", "source"],
                merge_key="activityId",
            )

    def _ingest_communications(self) -> None:
        rows = []
        for doc in self.db["communications"].find({}):
            case_id = doc.get("caseId")
            if not case_id:
                continue
            party_id = self._resolve_party_for_case(case_id, doc.get("userId"))
            if not party_id:
                continue
            edge = map_communicated_edge(doc, party_id)
            if edge:
                rows.append(edge)

            if len(rows) >= BATCH_SIZE:
                self._batch_merge_rels(
                    "COMMUNICATED",
                    "Case",
                    "caseId",
                    "Party",
                    "partyId",
                    rows,
                    ["communicationId", "mongoId", "type", "direction", "bodyPreview", "status", "sentAt", "fromName", "fromPhone"],
                    merge_key="communicationId",
                )
                rows = []

        if rows:
            self._batch_merge_rels(
                "COMMUNICATED",
                "Case",
                "caseId",
                "Party",
                "partyId",
                rows,
                ["communicationId", "mongoId", "type", "direction", "bodyPreview", "status", "sentAt", "fromName", "fromPhone"],
                merge_key="communicationId",
            )

    def _ingest_activities(self) -> None:
        rows = []
        for doc in self.db["case_activity_log"].find({"category": {"$nin": list(EXCLUDED_ACTIVITY | {"document"})}}):
            case_id = doc.get("caseId")
            if not case_id:
                continue
            party_id = self._resolve_party_for_case(case_id, doc.get("userId"))
            if not party_id:
                continue
            edge = map_activity_edge(doc, party_id)
            if edge:
                rows.append(edge)

            if len(rows) >= BATCH_SIZE:
                self._batch_merge_rels(
                    "ACTIVITY",
                    "Case",
                    "caseId",
                    "Party",
                    "partyId",
                    rows,
                    ["activityId", "category", "action", "summary", "timestamp", "userId", "userName", "source"],
                    merge_key="activityId",
                )
                rows = []

        if rows:
            self._batch_merge_rels(
                "ACTIVITY",
                "Case",
                "caseId",
                "Party",
                "partyId",
                rows,
                ["activityId", "category", "action", "summary", "timestamp", "userId", "userName", "source"],
                merge_key="activityId",
            )
