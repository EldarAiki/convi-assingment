"""Graph-discovery questions for LangChain MongoDB exploration."""

GRAPH_DISCOVERY_QUESTIONS = [
    {
        "id": "collections_overview",
        "category": "schema",
        "question": (
            "List all collections and summarize what entity each collection represents "
            "in a legal injury-claims workflow."
        ),
    },
    {
        "id": "case_hub_fields",
        "category": "relationships",
        "question": (
            "In the cases collection, which fields identify the case, the client, and "
            "the assigned staff? Show field names and 2 example values each."
        ),
    },
    {
        "id": "case_linked_collections",
        "category": "relationships",
        "question": (
            "Which collections contain a caseId field, and how many distinct caseId "
            "values appear in each? Order by count descending."
        ),
    },
    {
        "id": "contact_case_links",
        "category": "relationships",
        "question": (
            "How are contacts linked to cases? Describe the caseIds field in contacts "
            "and whether contacts can belong to multiple cases."
        ),
    },
    {
        "id": "party_types",
        "category": "entities",
        "question": (
            "What distinct contactType values exist in contacts, and how many contacts "
            "have each type?"
        ),
    },
    {
        "id": "case_types",
        "category": "entities",
        "question": (
            "What distinct caseType values exist in cases, and how many cases have each type?"
        ),
    },
    {
        "id": "case_stages",
        "category": "entities",
        "question": (
            "What are the distinct status and stage values in cases, and how are they "
            "distributed?"
        ),
    },
    {
        "id": "activity_categories",
        "category": "events",
        "question": (
            "In case_activity_log, what are the distinct category and action values, "
            "and which combinations are most common?"
        ),
    },
    {
        "id": "communication_channels",
        "category": "events",
        "question": (
            "In communications, what communication types and directions exist, and how "
            "many records per type?"
        ),
    },
    {
        "id": "document_types",
        "category": "documents",
        "question": (
            "In files, what distinct document_type and document_category values appear "
            "in processedData, and how many files per type?"
        ),
    },
    {
        "id": "conversation_links",
        "category": "relationships",
        "question": (
            "How do conversations connect cases, users, and messages? Show the key "
            "linking fields and example values."
        ),
    },
    {
        "id": "financial_projection_links",
        "category": "relationships",
        "question": (
            "How does case_financial_projections relate to cases? Are there multiple "
            "projections per case?"
        ),
    },
    {
        "id": "user_id_overlap",
        "category": "relationships",
        "question": (
            "Which collections share userId or clientId fields, and do the same IDs "
            "appear across collections?"
        ),
    },
    {
        "id": "temporal_fields",
        "category": "properties",
        "question": (
            "For cases, case_activity_log, communications, and files, what are the main "
            "date/time fields that could become edge or node properties in a timeline?"
        ),
    },
    {
        "id": "graph_node_proposal",
        "category": "synthesis",
        "question": (
            "Based on the schema, propose a graph model with node types, edge types, and "
            "the MongoDB fields that justify each. Focus on injury-claim case management."
        ),
    },
]

QUESTIONS_BY_CATEGORY = {}
for item in GRAPH_DISCOVERY_QUESTIONS:
    QUESTIONS_BY_CATEGORY.setdefault(item["category"], []).append(item)
