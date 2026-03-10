"""
Unit tests for MCP tool handler helpers.

Tests the shared formatting, category inference, and batch query logic
without requiring a database connection or running MCP server.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from servers.mcp_tool_handlers import MCPToolHandlers, _infer_category_from_type


@pytest.fixture
def handlers():
    """Create MCPToolHandlers with no real dependencies."""
    return MCPToolHandlers(
        concept_manager=None,
        storage=None,
        sparql_service=None,
        source_text_manager=None,
        db_connected=False,
    )


# ------------------------------------------------------------------
# _format_entity_result
# ------------------------------------------------------------------

@pytest.mark.unit
class TestFormatEntityResult:
    """Test the shared entity formatting helper."""

    def test_basic_formatting(self, handlers):
        row = {
            "uri": "http://proethica.org/ontology/core#Role",
            "label": "Role",
            "comment": "A role in professional ethics",
            "entity_type": "class",
            "parent_uri": "",
            "properties": {},
            "source_ontology": "proethica-core",
        }
        result = handlers._format_entity_result(row)

        assert result["uri"] == "http://proethica.org/ontology/core#Role"
        assert result["label"] == "Role"
        assert result["definition"] == "A role in professional ethics"
        assert result["source_ontology"] == "proethica-core"
        assert result["found"] is True
        assert "properties" not in result

    def test_label_fallback_to_uri_fragment(self, handlers):
        row = {
            "uri": "http://proethica.org/ontology/core#Engineer",
            "label": None,
            "comment": "",
            "entity_type": "individual",
            "parent_uri": "http://proethica.org/ontology/core#Role",
            "properties": {},
            "source_ontology": "proethica-core",
        }
        result = handlers._format_entity_result(row)
        assert result["label"] == "Engineer"

    def test_label_fallback_to_uri_path(self, handlers):
        row = {
            "uri": "http://example.org/ontology/Engineer",
            "label": None,
            "comment": "",
            "entity_type": "individual",
            "parent_uri": "",
            "properties": {},
            "source_ontology": "test",
        }
        result = handlers._format_entity_result(row)
        assert result["label"] == "Engineer"

    def test_definition_fallback_to_properties(self, handlers):
        row = {
            "uri": "http://proethica.org/ontology/core#TestObligation",
            "label": "Test Obligation",
            "comment": "",
            "entity_type": "individual",
            "parent_uri": "http://proethica.org/ontology/core#Obligation",
            "properties": {
                "obligationstatement": "Engineers shall hold public safety paramount"
            },
            "source_ontology": "proethica-core",
        }
        result = handlers._format_entity_result(row)
        assert "public safety" in result["definition"]

    def test_include_properties_false(self, handlers):
        row = {
            "uri": "http://example.org/test#A",
            "label": "A",
            "comment": "desc",
            "entity_type": "class",
            "parent_uri": "",
            "properties": {"key": "value"},
            "source_ontology": "test",
        }
        result = handlers._format_entity_result(row, include_properties=False)
        assert "properties" not in result

    def test_include_properties_true(self, handlers):
        row = {
            "uri": "http://example.org/test#A",
            "label": "A",
            "comment": "desc",
            "entity_type": "class",
            "parent_uri": "",
            "properties": {"key": "value"},
            "source_ontology": "test",
        }
        result = handlers._format_entity_result(row, include_properties=True)
        assert result["properties"] == {"key": "value"}

    def test_empty_properties_not_included(self, handlers):
        row = {
            "uri": "http://example.org/test#A",
            "label": "A",
            "comment": "desc",
            "entity_type": "class",
            "parent_uri": "",
            "properties": {},
            "source_ontology": "test",
        }
        result = handlers._format_entity_result(row, include_properties=True)
        assert "properties" not in result

    def test_category_inference_from_parent_uri(self, handlers):
        row = {
            "uri": "http://proethica.org/ontology/case/7#facts_CivilEngineer",
            "label": "Civil Engineer",
            "comment": "",
            "entity_type": "individual",
            "parent_uri": "http://proethica.org/ontology/core#Role",
            "properties": {},
            "source_ontology": "proethica-case-7",
        }
        result = handlers._format_entity_result(row)
        assert result["entity_type"] == "Role"


# ------------------------------------------------------------------
# _infer_category_from_type
# ------------------------------------------------------------------

@pytest.mark.unit
class TestInferCategoryFromType:
    """Test the module-level category inference function."""

    def test_role_from_parent_uri(self):
        assert _infer_category_from_type("individual", "http://x#Role", "http://x#Y") == "Role"

    def test_principle_from_uri(self):
        assert _infer_category_from_type("individual", "", "http://x#HonestyPrinciple") == "Principle"

    def test_obligation_from_parent(self):
        assert _infer_category_from_type("individual", "http://x#Obligation", "http://x#Y") == "Obligation"

    def test_constraint_from_uri(self):
        assert _infer_category_from_type("individual", "", "http://x#BudgetConstraint") == "Constraint"

    def test_decision_point_from_uri(self):
        assert _infer_category_from_type("individual", "", "http://x#DecisionPoint1") == "Decision_Point"

    def test_class_fallback(self):
        assert _infer_category_from_type("class", "", "http://x#SomeRandomThing") == "Class"

    def test_individual_fallback(self):
        assert _infer_category_from_type("individual", "", "http://x#SomeRandomThing") == "Individual"

    def test_unknown_fallback(self):
        assert _infer_category_from_type("", "", "http://x#SomeRandomThing") == "Unknown"


# ------------------------------------------------------------------
# _extract_definition_from_properties
# ------------------------------------------------------------------

@pytest.mark.unit
class TestExtractDefinitionFromProperties:
    """Test the static definition extraction helper."""

    def test_obligation_statement(self, handlers):
        props = {"obligationstatement": "Engineers shall hold safety paramount"}
        assert "safety" in handlers._extract_definition_from_properties(props)

    def test_rdfs_comment(self, handlers):
        props = {"comment": "A descriptive comment"}
        assert handlers._extract_definition_from_properties(props) == "A descriptive comment"

    def test_list_value(self, handlers):
        props = {"description": ["First description", "Second"]}
        assert handlers._extract_definition_from_properties(props) == "First description"

    def test_empty_properties(self, handlers):
        assert handlers._extract_definition_from_properties({}) == ""

    def test_priority_order(self, handlers):
        props = {
            "description": "low priority",
            "obligationstatement": "high priority",
        }
        assert "high priority" in handlers._extract_definition_from_properties(props)


# ------------------------------------------------------------------
# handle_get_entities_by_uris (batch query logic)
# ------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestBatchEntityLookup:
    """Test the batch URI lookup logic (mocked storage)."""

    @pytest.fixture
    def connected_handlers(self):
        """Create handlers with mocked storage for batch query testing."""
        storage = MagicMock()
        h = MCPToolHandlers(
            concept_manager=None,
            storage=storage,
            sparql_service=None,
            source_text_manager=None,
            db_connected=True,
        )
        return h, storage

    async def test_batch_returns_found_and_not_found(self, connected_handlers):
        h, storage = connected_handlers
        storage._execute_query.return_value = [
            {
                "uri": "http://x#A",
                "label": "A",
                "comment": "desc A",
                "entity_type": "class",
                "parent_uri": "",
                "properties": {},
                "source_ontology": "test",
            },
        ]

        result = await h.handle_get_entities_by_uris({
            "uris": ["http://x#A", "http://y/B"],
        })

        assert result["found_count"] == 1
        assert result["not_found"] == ["http://y/B"]
        assert result["entities"][0]["label"] == "A"

    async def test_batch_query_uses_any_parameter(self, connected_handlers):
        h, storage = connected_handlers
        storage._execute_query.return_value = []

        # Use URIs without # to avoid fragment fallback path
        await h.handle_get_entities_by_uris({
            "uris": ["http://x/A", "http://x/B"],
        })

        # First call should be the batch ANY query
        call_args = storage._execute_query.call_args_list[0]
        assert "ANY(%s)" in call_args[0][0]
        assert call_args[0][1] == (["http://x/A", "http://x/B"],)

    async def test_empty_uris_returns_error(self, connected_handlers):
        h, _ = connected_handlers
        result = await h.handle_get_entities_by_uris({"uris": []})
        assert "error" in result

    async def test_truncates_to_20(self, connected_handlers):
        h, storage = connected_handlers
        storage._execute_query.return_value = []

        # Use URIs without # to avoid fragment fallback path
        uris = [f"http://x/{i}" for i in range(25)]
        await h.handle_get_entities_by_uris({"uris": uris})

        # First call should be the batch ANY query with 20 URIs
        call_args = storage._execute_query.call_args_list[0]
        assert len(call_args[0][1][0]) == 20

    async def test_db_not_connected(self):
        h = MCPToolHandlers(None, None, None, None, db_connected=False)
        result = await h.handle_get_entities_by_uris({
            "uris": ["http://x#A"],
        })
        assert "error" in result
        assert result["not_found"] == ["http://x#A"]
