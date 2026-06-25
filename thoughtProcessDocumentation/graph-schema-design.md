# Graph schema design — thought process

This document explains how we designed the Neo4j graph for a legal injury-claims platform (~70 cases, ~70MB MongoDB), why we split **nodes** and **edges** the way we did, and what we traded off.

The canonical schema lives in [`analyzeData/graph_schema.yaml`](../analyzeData/graph_schema.yaml) (version **1.2**).

---

## Problem we were solving

MongoDB holds operational data across eight collections (`cases`, `files`, `communications`, `case_activity_log`, `case_financial_projections`, etc.). An LLM cannot safely or efficiently “browse” that raw store for every question.

We wanted a **case-centric graph** where an agent can:

- Reconstruct **timelines** (documents, communications, milestones)
- Read **distilled narratives** without loading full OCR blobs on every query
- Compare cases by **legal stage**, **injury**, and **outcome**
- Traverse **parties**, **insurers**, and **experts** linked to financial analysis

The graph is an **operational reasoning layer**, not a full copy of MongoDB.

---

## Core design principle: entities on nodes, events on edges

### v1.0 (rejected): event nodes

Early design modeled `Communication` and `ActivityEvent` as separate nodes, with edges like `HAS_COMMUNICATION`, `HAS_ACTIVITY`, `PERFORMED_BY`.

**Why we moved away**

| Issue | Impact |
|-------|--------|
| Duplication | Same interaction appeared in `communications` *and* `case_activity_log` (category `communication`) |
| Graph weight | ~8k extra nodes for events that are really “something happened at time T” |
| Agent complexity | Timeline queries required hopping through intermediate nodes |
| MERGE pain | Easy to create redundant paths for the same real-world event |

### v1.1+ (chosen): edge-centric model

**Nodes** = stable entities with identity  
**Edges** = dated interactions and structural links, carrying timeline narrative on the relationship itself

```
Case ──RECEIVED_DOCUMENT──► File
Case ──COMMUNICATED────────► Party
Case ──ACTIVITY────────────► Party
Case ──HAS_PROJECTION──────► FinancialProjection
Party ──INSURER_IN─────────► FinancialProjection
```

**Pros**

- One natural timeline query pattern: follow dated edges from `Case`
- Fewer nodes (~2,500 vs potentially ~10k+ with event nodes)
- Clear source-of-truth rules (e.g. communications from `communications` collection only)
- Relationship properties hold **when** + **short summary** — exactly what timeline reasoning needs

**Cons**

- Multiple events between the same pair (e.g. many emails Case→Party) require **unique merge keys** on edges (`communicationId`, `activityId`) — we learned this when MERGE collapsed edges incorrectly
- Cypher for “all communications in the firm” is less uniform than `MATCH (c:Communication)` — acceptable because queries are case-scoped
- Rich event metadata must fit on edge properties or stay in MongoDB for drill-down

---

## Node types and why each exists

### Case (hub)

Everything important connects here via `caseId`.

**Properties worth explaining**

| Property | Source | Reasoning |
|----------|--------|-----------|
| `caseType`, `appStatus`, `appStage` | `cases` | Operational workflow; distinct from legal classification on projection |
| `injuredBodyParts` | `medicalInfo.injuredBodyParts` | Structured intake array — **only ~4/70 cases populated**; still worth keeping for precision when present |
| `mainInjury` | projection (denormalized) | Primary injury narrative on **Case** so agents filter without always joining projection |
| `injurySearchText` | derived at ingest | Combined injury + event text + summary for substring search |
| `searchDigest` | derived | Short agent-facing digest (~500 chars) from type + accident date + projection summary |

**Pros of denormalizing injury onto Case**  
Agents search one node; injury questions do not always need projection context.

**Cons**  
Duplication with `FinancialProjection.mainInjury`; must re-ingest when projection changes (acceptable — ingest is batch, not real-time).

### Party

People and organizations: clients, contacts, insurers, experts.

**Design choice:** Insurers and experts are often **created from projection text** at ingest (`INSURER_IN`, `EXPERT_IN`, `LEGAL_TRACK`), not only from `contacts`. That matches how the legal analysis references them even when they are not formal contacts.

**Cons:** Name normalization is imperfect (`איילון` vs `איילון חברה לביטוח`) — v2 plans party identity resolution.

### File

Canonical document metadata + **OCR summary** (`summaryShort`), not full extracted text.

**Pros:** Agent reads narrative without multi-KB OCR per document.  
**Cons:** Deep document questions need MongoDB drill-down (future Tier-2 tool).

### FinancialProjection

Current legal/financial snapshot (`status: current` only).

Holds `caseSummary` (primary legal narrative), stage, SLA, compensation, **outcomeBand** (derived), and classification fields.

**Why a separate node instead of flattening onto Case?**

- Projection is a rich sub-document with its own versioning in MongoDB
- Keeps Case node smaller for listing/search
- Clear pattern: `(Case)-[:HAS_PROJECTION]->(FinancialProjection)` for “legal story” questions

---

## Edge types and ingest decisions

### Structural edges

| Edge | Meaning |
|------|---------|
| `HAS_PARTY` | Client or contact linked to case |
| `HAS_PROJECTION` | Current financial/legal analysis |

### Timeline / interaction edges

| Edge | Mongo source | Excluded alternatives |
|------|--------------|------------------------|
| `RECEIVED_DOCUMENT` | `case_activity_log` where `category=document`, link via `details.fileId` | Do **not** use `entityId` alone (often `file_{id}`) |
| `COMMUNICATED` | `communications` | Exclude activity_log `communication` (duplicate, poorer content) |
| `ACTIVITY` | activity_log except document/communication/conversation | — |

### Projection-context edges

| Edge | Meaning |
|------|---------|
| `INSURER_IN` | Insurer org → projection |
| `EXPERT_IN` | Expert person → projection |
| `LEGAL_TRACK` | Parallel track (e.g. ביטוח לאומי) → projection |
| `SUBJECT_OF` | Client party → projection |

These encode **legal analysis context** without duplicating the whole projection JSON in the graph.

---

## Collections deliberately excluded

| Collection | Reason |
|------------|--------|
| `messages`, `conversations` | Low value for v1 legal graph; high volume; redundant with formal `communications` for agent goals |
| activity_log `communication` | Superseded by `communications` collection |
| activity_log `conversation` | Optional summaries; skipped to keep graph lean |

Exclusion is a **product decision**: optimize for case timeline + legal/financial reasoning, not full chat archive.

---

## Property placement: node vs edge — rules we used

| Put on **node** when… | Put on **edge** when… |
|------------------------|------------------------|
| Identity is stable (`caseId`, `fileId`, `partyId`) | It is an **occurrence** with a timestamp |
| Value describes the entity across the case lifecycle | Value describes **this specific interaction** |
| Agent filters/sorts on it often (`outcomeBand`, `caseType`) | Narrative is “what happened when document arrived” |
| Narrative is canonical (`File.summaryShort`, `caseSummary`) | Preview is enough (`bodyPreview` on `COMMUNICATED`) |

---

## Outcome bands (derived, not LLM-judged)

We added deterministic `outcomeBand` on `FinancialProjection` at ingest:

- `success`, `partial_success`, `failed`, `incomplete`

Based on terminal stage, compensation percentiles by case type, SLA (`overdue` / `at_risk`), and timing flags.

**Why deterministic?**  
Agents must not invent success/failure from prose alone. The band is auditable; `outcomeReasons` lists which rules fired.

**Tradeoff:** Most active cases land in `incomplete` — correct for a live caseload, but “show me successful cases” returns very few rows until more cases close.

---

## Known limitations (honest cons of this schema)

1. **Not a full Mongo mirror** — full OCR, long emails, nested projection JSON stay in MongoDB.
2. **Substring search, not semantic** — injury/case search uses `CONTAINS`; v2 adds embeddings + `SIMILAR_TO`.
3. **Party deduplication** — same insurer spelled differently → multiple Party nodes.
4. **Re-ingest required** — graph is built locally; not shipped in Git.
5. **Communication/activity party resolution** — sometimes falls back to client party when `userId` is missing.
6. **Sparse structured injuries** — `injuredBodyParts` rarely filled; `mainInjury` + `caseSummary` carry most injury signal.

---

## v2 direction (documented, not implemented)

From `graph_schema.yaml`:

- Vector embeddings on narrative fields
- `SIMILAR_TO` edges between cases
- Party identity resolution
- Optional richer organization modeling

v1 prioritizes **correct structure + auditable tools** over semantic similarity at scale.
