"""
Unit tests for core.entity_patterns -- shared classification patterns.

Verifies the centralized category inference, pattern dictionary, and
SQL priority generation used by MCP handlers and editor services.
"""

import pytest

from core.entity_patterns import (
    CATEGORY_PATTERNS,
    ONTOLOGY_PRIORITY,
    infer_category_from_type,
    build_ontology_priority_sql,
)


@pytest.mark.unit
class TestCategoryPatterns:
    """Verify the CATEGORY_PATTERNS dictionary structure."""

    def test_all_categories_have_patterns(self):
        for category, patterns in CATEGORY_PATTERNS.items():
            assert len(patterns) > 0, f"Category '{category}' has no patterns"

    def test_all_pattern_values_are_lowercase(self):
        for category, patterns in CATEGORY_PATTERNS.items():
            for p in patterns:
                assert p == p.lower(), f"Pattern '{p}' in '{category}' is not lowercase"

    def test_expected_categories_present(self):
        expected = {"role", "principle", "obligation", "constraint", "decision_point"}
        assert expected.issubset(CATEGORY_PATTERNS.keys())


@pytest.mark.unit
class TestInferCategoryFromType:
    """Test the centralized category inference function."""

    def test_role_from_parent_uri(self):
        assert infer_category_from_type("individual", "http://x#Role", "http://x#Y") == "Role"

    def test_principle_from_uri(self):
        assert infer_category_from_type("individual", "", "http://x#HonestyPrinciple") == "Principle"

    def test_obligation_from_parent(self):
        assert infer_category_from_type("individual", "http://x#Obligation", "http://x#Y") == "Obligation"

    def test_constraint_from_uri(self):
        assert infer_category_from_type("individual", "", "http://x#BudgetConstraint") == "Constraint"

    def test_decision_point_from_uri(self):
        assert infer_category_from_type("individual", "", "http://x#DecisionPoint1") == "Decision_Point"

    def test_state_from_condition_in_parent(self):
        assert infer_category_from_type("individual", "http://x#Condition", "http://x#Y") == "State"

    def test_capability_from_uri(self):
        assert infer_category_from_type("individual", "", "http://x#DesignCapability") == "Capability"

    def test_event_from_uri(self):
        assert infer_category_from_type("individual", "", "http://x#BridgeCollapseEvent") == "Event"

    def test_class_fallback(self):
        assert infer_category_from_type("class", "", "http://x#SomeRandomThing") == "Class"

    def test_individual_fallback(self):
        assert infer_category_from_type("individual", "", "http://x#SomeRandomThing") == "Individual"

    def test_unknown_fallback(self):
        assert infer_category_from_type("", "", "http://x#SomeRandomThing") == "Unknown"

    def test_none_parent_uri_handled(self):
        result = infer_category_from_type("class", None, "http://x#Role")
        assert result == "Role"


@pytest.mark.unit
class TestOntologyPriority:
    """Test the ONTOLOGY_PRIORITY list and SQL generation."""

    def test_priority_list_not_empty(self):
        assert len(ONTOLOGY_PRIORITY) > 0

    def test_proethica_core_is_first(self):
        assert ONTOLOGY_PRIORITY[0] == "proethica-core"

    def test_build_sql_contains_all_entries(self):
        sql = build_ontology_priority_sql()
        for name in ONTOLOGY_PRIORITY:
            assert f"'{name}'" in sql

    def test_build_sql_starts_with_case(self):
        sql = build_ontology_priority_sql()
        assert sql.startswith("CASE o.name")

    def test_build_sql_ends_with_else(self):
        sql = build_ontology_priority_sql()
        expected_else = f"ELSE {len(ONTOLOGY_PRIORITY) + 1} END"
        assert sql.endswith(expected_else)

    def test_build_sql_custom_column(self):
        sql = build_ontology_priority_sql(column="ont.name")
        assert sql.startswith("CASE ont.name")

    def test_build_sql_priority_order(self):
        sql = build_ontology_priority_sql()
        # proethica-core should map to 1, engineering-ethics to a higher number
        assert "WHEN 'proethica-core' THEN 1" in sql
        idx = ONTOLOGY_PRIORITY.index("engineering-ethics") + 1
        assert f"WHEN 'engineering-ethics' THEN {idx}" in sql
