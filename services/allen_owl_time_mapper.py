"""
Allen interval algebra -> OWL-Time property mapper.

The KI2026 paper (Section 1, "encodes temporal relations through Allen's
[1] interval algebra via OWL-Time [5]") and the proethica-intermediate
ontology (`proeth:allenRelation` / `proeth:owlTimeProperty`) both rely
on a mapping from Allen's thirteen interval-algebra relations to the
corresponding properties in the W3C OWL-Time ontology.

This module is the canonical mapping. It is referenced by name from
``ontologies/proethica-intermediate.ttl`` in the ``proeth:allenRelation``
comment; keep the two in sync.

Reference:
    James F. Allen, "Maintaining knowledge about temporal intervals,"
    Communications of the ACM 26(11), 832-843, 1983.

    W3C Recommendation, "Time Ontology in OWL" (2017):
    https://www.w3.org/TR/owl-time/

The 13 Allen relations split into six pairs plus ``equals`` (its own
inverse). The mapping below uses OWL-Time's ``intervalX`` property
family verbatim so that materialized triples round-trip into any
standards-compliant SPARQL engine that understands OWL-Time.
"""

from __future__ import annotations

from rdflib import Namespace, URIRef

# Canonical W3C OWL-Time namespace
TIME = Namespace("http://www.w3.org/2006/time#")


# The 13 Allen interval-algebra relations mapped to OWL-Time properties.
# Keys are the lowercase names ProEthica's extraction clients emit via
# proeth:allenRelation; values are full URIs for proeth:owlTimeProperty.
ALLEN_TO_OWL_TIME: dict[str, URIRef] = {
    # Precedence -- two disjoint intervals, one before the other.
    "before":          TIME.intervalBefore,
    "after":           TIME.intervalAfter,
    # Meeting -- one interval's end coincides with another's start.
    "meets":           TIME.intervalMeets,
    "metby":           TIME.intervalMetBy,
    # Overlap -- intervals share a proper subinterval without containment.
    "overlaps":        TIME.intervalOverlaps,
    "overlappedby":    TIME.intervalOverlappedBy,
    # Containment.
    "during":          TIME.intervalDuring,
    "contains":        TIME.intervalContains,
    # Shared start.
    "starts":          TIME.intervalStarts,
    "startedby":       TIME.intervalStartedBy,
    # Shared end.
    "finishes":        TIME.intervalFinishes,
    "finishedby":      TIME.intervalFinishedBy,
    # Identity (its own inverse).
    "equals":          TIME.intervalEquals,
}


# Inverses. ``equals`` is self-inverse; the rest pair up.
ALLEN_INVERSE: dict[str, str] = {
    "before":        "after",
    "after":         "before",
    "meets":         "metby",
    "metby":         "meets",
    "overlaps":      "overlappedby",
    "overlappedby":  "overlaps",
    "during":        "contains",
    "contains":      "during",
    "starts":        "startedby",
    "startedby":     "starts",
    "finishes":      "finishedby",
    "finishedby":    "finishes",
    "equals":        "equals",
}


def allen_to_owl_time(relation: str) -> URIRef:
    """Map an Allen relation name to an OWL-Time property URI.

    Matching is case- and whitespace-insensitive so that extraction
    clients can emit the names in either short form ("before") or
    mixed case ("Before"). Raises ``ValueError`` for anything outside
    the thirteen Allen relations.
    """
    if relation is None:
        raise ValueError("Allen relation name must not be None")

    key = relation.strip().lower().replace("-", "").replace("_", "")
    try:
        return ALLEN_TO_OWL_TIME[key]
    except KeyError:
        raise ValueError(
            f"Unknown Allen relation: {relation!r}. "
            f"Expected one of: {sorted(ALLEN_TO_OWL_TIME)}"
        )


def inverse_of(relation: str) -> str:
    """Return the Allen inverse of a relation name (case-insensitive)."""
    if relation is None:
        raise ValueError("Allen relation name must not be None")
    key = relation.strip().lower().replace("-", "").replace("_", "")
    try:
        return ALLEN_INVERSE[key]
    except KeyError:
        raise ValueError(
            f"Unknown Allen relation: {relation!r}. "
            f"Expected one of: {sorted(ALLEN_INVERSE)}"
        )


def allen_relations() -> tuple[str, ...]:
    """Return the thirteen Allen relation names in a stable order."""
    return (
        "before",
        "after",
        "meets",
        "metby",
        "overlaps",
        "overlappedby",
        "during",
        "contains",
        "starts",
        "startedby",
        "finishes",
        "finishedby",
        "equals",
    )
