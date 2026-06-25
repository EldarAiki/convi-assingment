# Project journey and tradeoffs

Broader thought process across the three phases of this assignment: **discover → ingest → reason**.

---

## Phase 1: analyzeData — understand before modeling

Before Neo4j, we spent effort on **mechanical profiling** and **LLM-assisted exploration** of MongoDB.

| Activity | Output | Why it mattered |
|----------|--------|-----------------|
| Schema profiling (`profile/schema_profile.py`) | `schema_report.json` | Field types, cardinalities, cross-collection keys — no LLM hallucination |
| LangChain MongoDB agent (`explore/run_agent.py`) | Graph-discovery Q&A | Validated entity/relationship hypotheses in natural language |
| Linkage scripts (`scripts/analyze_*`) | Activity/projection link reports | Proved **how** documents and communications actually link (e.g. `details.fileId`, not `entityId`) |

**Key insight:** The operational schema does not match intuitive ER diagrams. For example, `case_activity_log` category `communication` duplicates `communications` but with worse linkage. Design decisions came from **data evidence**, not assumptions.

**Tradeoff:** Exploration agent uses broad Mongo access — powerful for analysts, unsuitable as the production user-facing agent.

---

## Phase 2: graphIngest — deterministic ETL

Ingestion is **fully deterministic** (no LLM). It reads [`graph_schema.yaml`](../analyzeData/graph_schema.yaml) as the contract and maps MongoDB → Neo4j.

**Principles**

- MERGE for idempotent reloads (`python main.py --clear`)
- Batch writes for ~70 cases / ~2k files
- Derived fields at ingest (`outcomeBand`, `injurySearchText`, `searchDigest`) so agents query simple properties
- Single `.env` at repo root shared by all modules

**Tradeoff:** Batch ingest means the graph is a **snapshot**, not real-time with MongoDB. Acceptable for assessment scope; production would need change streams or scheduled refresh.

---

## Phase 3: graphAgent — bounded reasoning

See [agent-architecture.md](agent-architecture.md) for detail.

**Tradeoff:** We optimized for **explainability** over **autonomy**. A lawyer-facing system should show which cases and tools supported an answer, and stop when data is insufficient.

---

## MongoDB vs Neo4j — division of responsibility

| Concern | MongoDB | Neo4j |
|---------|---------|-------|
| Full OCR / email bodies | Yes | No (preview/summary only) |
| Nested projection JSON | Yes | Flattened key fields |
| Timeline traversal | Possible but awkward | Native |
| Case similarity (v1) | Ad-hoc aggregations | Structured properties + text CONTAINS |
| Source of truth | Always | Derived read model |

The graph is a **purpose-built view**, not a migration target.

---

## Hebrew and mixed-language content

Much of the domain text is Hebrew (case names, injuries, summaries).

**Implications we handled**

- UTF-8 stdout in CLI
- `--html` reports with `unicode-bidi: plaintext` for readable RTL
- Synthesis prompt avoids markdown tables for Hebrew terminal output
- Search tools use case-insensitive `CONTAINS` on Hebrew fields — works for keywords, not true semantic similarity

**Future:** Embedding-based similarity with a multilingual model would help “find cases like this injury description” beyond substring match.

---

## Outcome classification — product vs legal truth

`outcomeBand` encodes **operational assessment signals** (stage, SLA, compensation vs cohort percentiles), not a court ruling.

Most cases are `incomplete` because the caseload is active. That is correct behavior but surprises users who expect many `success` rows.

We document bands in ingest and expose them through `get_case_outcome` so the agent explains **why**, not just **what**.

---

## Portability and deployment thinking

Documented in [`SETUP.md`](../SETUP.md).

- Secrets and graph data stay **out of Git**
- Neo4j can run via **Desktop**, **Docker**, or **Aura** — Desktop is optional
- Every new environment runs **ingest** once

This matches how teams typically ship: code in repo, data plane configured per environment.

---

## Testing and validation approach

| Layer | How we validated |
|-------|------------------|
| Ingest | `--dry-run` counts vs Neo4j counts post-load |
| MERGE keys | Relationship counts should match Mongo row counts (e.g. 1,346 `COMMUNICATED`) |
| Agent | `test_anthropic.py`, manual questions, `agent_run.json` traces |
| Case type search | Discovered need for `list_case_types` + synonyms after real prompts failed |

We favored **observable runs** (JSON reports, progress logs) over heavy unit test suites for assignment scope.

---

## v2 roadmap (if continuing)

Priority order we would suggest:

1. **Semantic case similarity** — embeddings + `SIMILAR_TO` edges  
2. **Party identity resolution** — merge insurer name variants  
3. **Mongo drill-down tool** — full OCR / email when graph summary insufficient  
4. **Incremental ingest** — avoid full `--clear` on every update  
5. **COMMUNICATED party resolution** — improve outgoing comm linkage  

---

## Summary narrative for presentations

1. **Explored** messy legal-operational MongoDB with profiling + targeted analysis scripts.  
2. **Modeled** a lean graph: entities as nodes, timeline as dated edges, narratives distilled.  
3. **Ingested** deterministically with auditable derived fields (outcomes, injuries).  
4. **Queried** through a LangGraph agent with schema-aligned tools, hard limits, and cited answers.

The through-line is **trust**: legal-adjacent reasoning requires traceable data access, not an unconstrained chatbot over raw documents.
