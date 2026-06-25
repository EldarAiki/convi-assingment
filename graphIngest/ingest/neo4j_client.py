"""Neo4j driver wrapper and batched Cypher helpers."""

from __future__ import annotations

from typing import Any

from neo4j import Driver, GraphDatabase


CONSTRAINTS = [
    "CREATE CONSTRAINT case_case_id IF NOT EXISTS FOR (n:Case) REQUIRE n.caseId IS UNIQUE",
    "CREATE CONSTRAINT party_party_id IF NOT EXISTS FOR (n:Party) REQUIRE n.partyId IS UNIQUE",
    "CREATE CONSTRAINT file_file_id IF NOT EXISTS FOR (n:File) REQUIRE n.fileId IS UNIQUE",
    "CREATE CONSTRAINT projection_projection_id IF NOT EXISTS FOR (n:FinancialProjection) REQUIRE n.projectionId IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX case_case_type IF NOT EXISTS FOR (n:Case) ON (n.caseType)",
    "CREATE INDEX case_main_injury IF NOT EXISTS FOR (n:Case) ON (n.mainInjury)",
    "CREATE INDEX projection_legal_stage IF NOT EXISTS FOR (n:FinancialProjection) ON (n.legalStage)",
    "CREATE INDEX projection_outcome_band IF NOT EXISTS FOR (n:FinancialProjection) ON (n.outcomeBand)",
    "CREATE INDEX party_role_type IF NOT EXISTS FOR (n:Party) ON (n.roleType)",
]


class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        self.database = database
        self.driver: Driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self.driver.close()

    def verify(self) -> None:
        self.driver.verify_connectivity()

    def run(self, query: str, parameters: dict[str, Any] | None = None) -> None:
        with self.driver.session(database=self.database) as session:
            session.run(query, parameters or {})

    def setup_schema(self) -> None:
        for statement in CONSTRAINTS + INDEXES:
            self.run(statement)

    def clear_graph(self) -> None:
        self.run("MATCH (n) DETACH DELETE n")

    def merge_nodes(self, label: str, id_field: str, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0

        query = f"""
        UNWIND $rows AS row
        MERGE (n:{label} {{{id_field}: row.{id_field}}})
        SET n += row
        """
        self.run(query, {"rows": rows})
        return len(rows)

    def merge_relationships(
        self,
        rel_type: str,
        from_label: str,
        from_id_field: str,
        to_label: str,
        to_id_field: str,
        rows: list[dict[str, Any]],
        rel_props: list[str] | None = None,
        merge_key: str | None = None,
    ) -> int:
        if not rows:
            return 0

        rel_props = rel_props or []
        set_parts = [f"r.{prop} = row.{prop}" for prop in rel_props if prop != merge_key]
        set_parts.append("r.updatedAt = datetime()")
        set_clause = f"SET {', '.join(set_parts)}"

        if merge_key:
            rel_pattern = f"[r:{rel_type} {{{merge_key}: row.{merge_key}}}]"
        else:
            rel_pattern = f"[r:{rel_type}]"

        query = f"""
        UNWIND $rows AS row
        MATCH (a:{from_label} {{{from_id_field}: row.fromId}})
        MATCH (b:{to_label} {{{to_id_field}: row.toId}})
        MERGE (a)-{rel_pattern}->(b)
        {set_clause}
        """
        self.run(query, {"rows": rows})
        return len(rows)

    def count_nodes(self) -> dict[str, int]:
        query = """
        MATCH (n)
        RETURN labels(n)[0] AS label, count(*) AS count
        ORDER BY label
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(query)
            return {record["label"]: record["count"] for record in result}

    def count_relationships(self) -> dict[str, int]:
        query = """
        MATCH ()-[r]->()
        RETURN type(r) AS relType, count(*) AS count
        ORDER BY relType
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(query)
            return {record["relType"]: record["count"] for record in result}
