"""
Unit tests for services.allen_owl_time_mapper.

The mapper is referenced by name from ontologies/proethica-intermediate.ttl
(the ``proeth:allenRelation`` comment) and is the single point of truth
for how the extraction client's Allen-relation strings become OWL-Time
property URIs. The tests pin the full 13-relation mapping, the inverse
involution, and the input-normalization rules so regressions are loud.
"""

import pytest

from rdflib import URIRef

from services.allen_owl_time_mapper import (
    ALLEN_INVERSE,
    ALLEN_TO_OWL_TIME,
    TIME,
    allen_relations,
    allen_to_owl_time,
    inverse_of,
)


EXPECTED_MAPPING = {
    "before": TIME.intervalBefore,
    "after": TIME.intervalAfter,
    "meets": TIME.intervalMeets,
    "metby": TIME.intervalMetBy,
    "overlaps": TIME.intervalOverlaps,
    "overlappedby": TIME.intervalOverlappedBy,
    "during": TIME.intervalDuring,
    "contains": TIME.intervalContains,
    "starts": TIME.intervalStarts,
    "startedby": TIME.intervalStartedBy,
    "finishes": TIME.intervalFinishes,
    "finishedby": TIME.intervalFinishedBy,
    "equals": TIME.intervalEquals,
}


@pytest.mark.unit
def test_mapping_covers_all_thirteen_allen_relations():
    """The mapper must cover exactly Allen's 13 interval relations."""
    assert set(ALLEN_TO_OWL_TIME.keys()) == set(EXPECTED_MAPPING.keys())
    assert len(ALLEN_TO_OWL_TIME) == 13


@pytest.mark.unit
@pytest.mark.parametrize("relation,expected", list(EXPECTED_MAPPING.items()))
def test_allen_to_owl_time_returns_expected_uri(relation, expected):
    """Each Allen relation name maps to its OWL-Time property URI."""
    actual = allen_to_owl_time(relation)
    assert isinstance(actual, URIRef)
    assert actual == expected


@pytest.mark.unit
def test_lookup_is_case_insensitive():
    """Mixed-case relation names resolve the same as lowercase."""
    assert allen_to_owl_time("Before") == TIME.intervalBefore
    assert allen_to_owl_time("OVERLAPS") == TIME.intervalOverlaps
    assert allen_to_owl_time("MetBy") == TIME.intervalMetBy


@pytest.mark.unit
def test_lookup_accepts_hyphens_and_underscores():
    """Extraction clients may emit ``started-by`` or ``started_by``."""
    assert allen_to_owl_time("met-by") == TIME.intervalMetBy
    assert allen_to_owl_time("overlapped_by") == TIME.intervalOverlappedBy
    assert allen_to_owl_time("started-by") == TIME.intervalStartedBy
    assert allen_to_owl_time("finished_by") == TIME.intervalFinishedBy


@pytest.mark.unit
def test_lookup_rejects_unknown_relation():
    """Anything outside the 13 relations must raise ``ValueError``."""
    with pytest.raises(ValueError, match="Unknown Allen relation"):
        allen_to_owl_time("simultaneous")
    with pytest.raises(ValueError, match="Unknown Allen relation"):
        allen_to_owl_time("")


@pytest.mark.unit
def test_lookup_rejects_none():
    with pytest.raises(ValueError):
        allen_to_owl_time(None)


@pytest.mark.unit
def test_inverses_form_an_involution():
    """Applying the inverse twice returns the original relation.

    This is a structural check on the Allen algebra: every relation's
    inverse is itself inverted to the original. ``equals`` is
    self-inverse.
    """
    for rel in allen_relations():
        inv = inverse_of(rel)
        assert inv in ALLEN_TO_OWL_TIME
        inv2 = inverse_of(inv)
        assert inv2 == rel


@pytest.mark.unit
def test_equals_is_self_inverse():
    assert inverse_of("equals") == "equals"


@pytest.mark.unit
def test_all_pairs_are_symmetric():
    """Every pair in ALLEN_INVERSE must be symmetric."""
    for a, b in ALLEN_INVERSE.items():
        assert ALLEN_INVERSE[b] == a


@pytest.mark.unit
def test_allen_relations_stable_order():
    """allen_relations() yields exactly 13 names in a stable order."""
    names = allen_relations()
    assert len(names) == 13
    assert len(set(names)) == 13  # no duplicates
    # first and last entries are documented as ``before`` and ``equals``
    assert names[0] == "before"
    assert names[-1] == "equals"


@pytest.mark.unit
def test_all_target_properties_live_in_time_namespace():
    """Every mapped property URI must be rooted at the W3C OWL-Time namespace."""
    prefix = "http://www.w3.org/2006/time#"
    for rel, uri in ALLEN_TO_OWL_TIME.items():
        assert str(uri).startswith(prefix), f"{rel} mapped to non-OWL-Time URI {uri}"
