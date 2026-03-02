"""
MCP Tool Schema Definitions

JSON Schema input definitions for each MCP tool exposed by the OntServe server.
These are returned by the list_tools handler and define the contract with clients.
"""


TOOL_DEFINITIONS = [
    {
        "name": "get_entities_by_category",
        "description": "Retrieve ontology entities by category from a professional domain",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Entity category (Role, Principle, Obligation, etc.)",
                    "enum": [
                        "Role", "Principle", "Obligation", "State", "Resource",
                        "Action", "Event", "Capability", "Constraint",
                        "Provision", "Guideline",
                    ],
                },
                "domain_id": {
                    "type": "string",
                    "description": "Professional domain identifier",
                    "default": "engineering-ethics",
                },
                "status": {
                    "type": "string",
                    "description": "Concept status filter",
                    "enum": ["candidate", "approved", "deprecated"],
                    "default": "approved",
                },
            },
            "required": ["category"],
        },
    },
    {
        "name": "sparql_query",
        "description": "Execute SPARQL query on professional domain ontology",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SPARQL query string",
                },
                "domain_id": {
                    "type": "string",
                    "description": "Professional domain identifier",
                    "default": "engineering-ethics",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "submit_candidate_concept",
        "description": "Submit a candidate concept extracted by ProEthica",
        "inputSchema": {
            "type": "object",
            "properties": {
                "concept": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "description": "Concept label with type suffix"},
                        "category": {"type": "string", "description": "Concept category"},
                        "description": {"type": "string", "description": "Concept description"},
                        "uri": {"type": "string", "description": "Concept URI"},
                        "confidence_score": {"type": "number", "description": "Extraction confidence"},
                        "source_document": {"type": "string", "description": "Source document"},
                        "extraction_method": {"type": "string", "description": "Extraction method used"},
                        "llm_reasoning": {"type": "string", "description": "LLM reasoning for extraction"},
                    },
                    "required": ["label", "category", "uri"],
                },
                "domain_id": {
                    "type": "string",
                    "description": "Professional domain identifier",
                    "default": "engineering-ethics",
                },
                "submitted_by": {
                    "type": "string",
                    "description": "User/system submitting the concept",
                    "default": "proethica-extractor",
                },
            },
            "required": ["concept"],
        },
    },
    {
        "name": "update_concept_status",
        "description": "Update the status of a candidate concept (approve/reject)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "concept_id": {
                    "type": "string",
                    "description": "Concept identifier",
                },
                "status": {
                    "type": "string",
                    "description": "New status",
                    "enum": ["approved", "rejected", "deprecated"],
                },
                "user": {
                    "type": "string",
                    "description": "User making the change",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for status change",
                },
            },
            "required": ["concept_id", "status", "user"],
        },
    },
    {
        "name": "get_candidate_concepts",
        "description": "Retrieve candidate concepts for review",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain_id": {
                    "type": "string",
                    "description": "Professional domain identifier",
                    "default": "engineering-ethics",
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category (optional)",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status",
                    "default": "candidate",
                },
            },
            "required": ["domain_id"],
        },
    },
    {
        "name": "get_domain_info",
        "description": "Get information about a professional domain",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain_id": {
                    "type": "string",
                    "description": "Professional domain identifier",
                    "default": "engineering-ethics",
                },
            },
            "required": ["domain_id"],
        },
    },
    {
        "name": "store_extracted_entities",
        "description": "Store extracted entities from LLM in case-specific ontology",
        "inputSchema": {
            "type": "object",
            "properties": {
                "case_id": {
                    "type": "string",
                    "description": "Case identifier",
                },
                "section_type": {
                    "type": "string",
                    "description": "Section type (facts, analysis, questions, etc.)",
                },
                "entities": {
                    "type": "array",
                    "description": "Array of extracted entities",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "description": {"type": "string"},
                            "category": {"type": "string"},
                            "confidence": {"type": "number"},
                            "extraction_metadata": {"type": "object"},
                        },
                        "required": ["label", "category"],
                    },
                },
                "extraction_session": {
                    "type": "object",
                    "description": "Extraction session metadata",
                },
            },
            "required": ["case_id", "section_type", "entities"],
        },
    },
    {
        "name": "get_case_entities",
        "description": "Retrieve stored entities for a specific case",
        "inputSchema": {
            "type": "object",
            "properties": {
                "case_id": {
                    "type": "string",
                    "description": "Case identifier",
                },
                "section_type": {
                    "type": "string",
                    "description": "Optional section type filter",
                },
                "category": {
                    "type": "string",
                    "description": "Optional entity category filter",
                },
            },
            "required": ["case_id"],
        },
    },
    {
        "name": "get_entity_by_uri",
        "description": (
            "Retrieve an entity's definition and metadata by its URI. "
            "Use this to resolve ProEthica entity IRIs during reasoning."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "uri": {
                    "type": "string",
                    "description": "The full entity URI (e.g., 'http://proethica.org/ontology/case/56#Engineer_A')",
                },
                "include_properties": {
                    "type": "boolean",
                    "description": "Whether to include all RDF properties in the response",
                    "default": False,
                },
            },
            "required": ["uri"],
        },
    },
    {
        "name": "get_entities_by_uris",
        "description": "Retrieve definitions for multiple entities at once. More efficient than multiple single lookups.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "uris": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of entity URIs to resolve (max 20)",
                },
            },
            "required": ["uris"],
        },
    },
    {
        "name": "get_entity_by_label",
        "description": (
            "Retrieve an entity's definition, URI, and metadata by its label. "
            "Use for disambiguation when matching extracted concepts against existing ontology classes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "The entity label to look up (exact match, case-insensitive)",
                },
            },
            "required": ["label"],
        },
    },
]
