# Convi assignment — injury claims graph + agent

Legal injury-claims platform prototype: profile MongoDB data, ingest a case-centric graph into Neo4j, and query it with a LangGraph agent (Anthropic).

## Modules

| Folder | Purpose |
|--------|---------|
| [`analyzeData/`](analyzeData/) | Schema profiling, graph design, optional MongoDB exploration agent |
| [`graphIngest/`](graphIngest/) | MongoDB → Neo4j ingestion (schema v1.2) |
| [`graphAgent/`](graphAgent/) | Graph-backed reasoning agent with outcome bands and injury tools |

## Quick start

**Full instructions:** [SETUP.md](SETUP.md)

```bash
cp .env.example .env          # edit with your credentials
pip install -r requirements.txt

# Neo4j: Desktop, Docker (`docker compose up -d`), or Aura — see SETUP.md

cd graphIngest && python main.py --clear
cd ../graphAgent && python main.py -q "How many liability cases are there?"
```

## Neo4j without Desktop

You do **not** need Neo4j Desktop on every machine. Alternatives:

- **Docker** — `docker compose up -d` (see [docker-compose.yml](docker-compose.yml))
- **Neo4j Aura** — cloud Bolt URI in `.env`

Desktop is optional and useful for visual graph exploration.

## Configuration

Single env file at repo root: **`.env`** (see [`.env.example`](.env.example)).

## Design documentation

Architecture rationale and thought process: [`thoughtProcessDocumentation/`](thoughtProcessDocumentation/)

- [Graph schema design](thoughtProcessDocumentation/graph-schema-design.md) — nodes vs edges, properties, tradeoffs  
- [Agent architecture](thoughtProcessDocumentation/agent-architecture.md) — LangGraph, tools, guardrails  
- [Project journey](thoughtProcessDocumentation/project-journey-and-tradeoffs.md) — pipeline phases, Mongo vs Neo4j, v2 roadmap  

## License / data

MongoDB credentials are assessment-specific and not included in this repo. Neo4j data is built locally via ingest.
