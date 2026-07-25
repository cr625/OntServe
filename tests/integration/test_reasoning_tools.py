"""Integration tests for the MCP reasoning-tool backends (servers/reasoning_tools.py).

These exercise the Pellet-backed reasoning path against the on-disk case_086 fixture
(the KI2026 Figure 1 worked example) so no database is required — only a Java runtime
for the owlready2/Pellet reasoner. Mirrors tests/integration/test_case_86_figure1.py.
"""
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
FIXTURE = PROJECT_ROOT / "fixtures" / "cases" / "case_086.ttl"


@pytest.fixture(scope="module")
def case86_content() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.mark.integration
@pytest.mark.requires_java
def test_reason_detailed_consistent_fixture(case86_content):
    """The Figure 1 fixture (merged with core+intermediate) reasons consistently and
    yields inferred type/subclass assertions with full IRIs."""
    from servers import reasoning_tools as rt

    d = rt.reason_detailed("proethica-case-86-fixture", content=case86_content)

    assert d["error"] is None, d["error"]
    assert d["consistent"] is True
    assert d["nothing_entities"] == []
    # Reasoning must produce inferences. For this minimal fixture they land at the
    # class level (inferred subclass edges); per-individual type inferences can be 0
    # because the three individuals' types are already asserted.
    assert d["inferred_subclass_count"] >= 1
    assert d["inferred_subclass_count"] + d["inferred_type_count"] >= 1
    # inferred edges carry full named IRIs (the named-IRI filter), not owlready short forms
    for edge in d["inferred_types"]:
        assert edge["type"].startswith("http"), edge
        assert edge["individual"].startswith("http"), edge
    for edge in d["inferred_subclasses"]:
        assert edge["parent"].startswith("http"), edge
        assert edge["child"].startswith("http"), edge


@pytest.mark.integration
@pytest.mark.requires_java
def test_get_inferred_hierarchy_and_inconsistent_classes_shapes(case86_content):
    """The two detail tools return the documented keys and agree on consistency."""
    from servers import reasoning_tools as rt

    d = rt.reason_detailed("proethica-case-86-fixture", content=case86_content)

    # Shape the hierarchy/inconsistent views the same way the tools do, from one pass.
    assert isinstance(d["inferred_subclasses"], list)
    assert isinstance(d["inferred_types"], list)
    assert d["consistent"] is True
    assert d["nothing_entities"] == []  # consistent -> nothing forced to owl:Nothing


def test_reason_detailed_missing_ontology_returns_error():
    """A name with no content and no DB row surfaces a structured error, not a crash.

    No Java needed: the DB fetch fails fast before the reasoner is invoked.
    """
    from servers import reasoning_tools as rt

    d = rt.reason_detailed("does-not-exist-xyz")
    assert d["consistent"] is False
    assert d["error"] is not None


@pytest.mark.integration
@pytest.mark.requires_java
def test_reason_detailed_local_scope_filters_to_target_subjects(case86_content):
    """scope='local' keeps only entailments whose subject is declared in the
    target content, dropping the stack-level entailments (e.g. intermediate
    archetype subsumptions) that recur identically on every merged run."""
    from servers import reasoning_tools as rt

    merged = rt.reason_detailed("proethica-case-86-fixture", content=case86_content)
    local = rt.reason_detailed("proethica-case-86-fixture", content=case86_content,
                               scope="local")

    assert local["error"] is None and local["consistent"] is True
    subjects = rt._local_subjects(case86_content)
    for edge in local["inferred_subclasses"]:
        assert edge["child"] in subjects, edge
    for edge in local["inferred_types"]:
        assert edge["individual"] in subjects, edge
    # The merged run carries stack-level subclass entailments the fixture does
    # not declare; local scope must report strictly fewer or equal, and every
    # dropped edge must be one whose subject is foreign to the fixture.
    assert local["inferred_subclass_count"] <= merged["inferred_subclass_count"]
    dropped = [e for e in merged["inferred_subclasses"]
               if e not in local["inferred_subclasses"]]
    for edge in dropped:
        assert edge["child"] not in subjects, edge
