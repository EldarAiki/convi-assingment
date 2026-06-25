# Thought process documentation

Design rationale for the Convi assignment project — written to explain **why** decisions were made, not only **what** was built.

| Document | Topic |
|----------|--------|
| [graph-schema-design.md](graph-schema-design.md) | Neo4j nodes vs edges, properties, ingest rules, pros/cons |
| [agent-architecture.md](agent-architecture.md) | LangGraph agent, LangChain role, tools, limits, reasoning loop |
| [project-journey-and-tradeoffs.md](project-journey-and-tradeoffs.md) | End-to-end pipeline, MongoDB analysis, outcomes, portability, v2 roadmap |

**Related technical references**

- Schema source of truth: [`analyzeData/graph_schema.yaml`](../analyzeData/graph_schema.yaml)
- Operational setup: [`SETUP.md`](../SETUP.md)
