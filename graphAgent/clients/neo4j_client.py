"""Read-only Neo4j client for the case reasoning agent."""

from __future__ import annotations

from typing import Any

from neo4j import Driver, GraphDatabase


class Neo4jReadClient:
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        self.database = database
        self.driver: Driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self.driver.close()

    def verify(self) -> None:
        self.driver.verify_connectivity()

    def query(self, cypher: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self.driver.session(database=self.database) as session:
            result = session.run(cypher, parameters or {})
            return [record.data() for record in result]
