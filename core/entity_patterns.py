"""
Shared entity classification patterns for ProEthica ontology types.

Used by MCP tool handlers and editor services for consistent
entity type inference across the system.
"""

# Pattern map: category name -> list of URI/label substrings that indicate membership.
# Checked against lowercased parent_uri and entity URI.
CATEGORY_PATTERNS = {
    "role": ["role", "engineer", "professional", "actor"],
    "principle": ["principle", "virtue", "value"],
    "obligation": ["obligation", "duty", "requirement"],
    "state": ["state", "condition", "situation"],
    "resource": ["resource", "document", "asset"],
    "action": ["action", "act", "behavior"],
    "event": ["event", "occurrence", "happening"],
    "capability": ["capability", "ability", "competence"],
    "constraint": ["constraint", "limitation", "restriction"],
    "question": ["question", "ethicalquestion"],
    "conclusion": ["conclusion", "ethicalconclusion"],
    "argument": ["argument", "toulmin"],
    "decision_point": ["decisionpoint", "decision"],
}

# Ontology priority for result ordering when multiple ontologies
# contain the same entity label. Lower index = higher priority.
ONTOLOGY_PRIORITY = [
    "proethica-core",
    "proethica-intermediate",
    "proethica-intermediate-extended",
    "engineering-ethics",
]


def infer_category_from_type(entity_type: str, parent_uri: str, uri: str) -> str:
    """Infer ProEthica category from entity type, parent URI, or URI pattern.

    Args:
        entity_type: Raw entity type string (e.g. 'class', 'individual')
        parent_uri: Parent class URI
        uri: Entity URI

    Returns:
        Human-readable category string (e.g. 'Role', 'Obligation', 'Class')
    """
    parent_lower = parent_uri.lower() if parent_uri else ""
    uri_lower = uri.lower()

    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if pattern in parent_lower or pattern in uri_lower:
                return category.title()

    if entity_type == "class":
        return "Class"
    elif entity_type == "individual":
        return "Individual"

    return entity_type or "Unknown"


def build_ontology_priority_sql(column: str = "o.name") -> str:
    """Generate SQL CASE expression for ontology priority ordering.

    Values come from the ONTOLOGY_PRIORITY constant (not user input),
    so the string interpolation is safe from injection.
    """
    cases = " ".join(
        f"WHEN '{name}' THEN {i}"
        for i, name in enumerate(ONTOLOGY_PRIORITY, 1)
    )
    return f"CASE {column} {cases} ELSE {len(ONTOLOGY_PRIORITY) + 1} END"
