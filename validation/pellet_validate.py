#!/usr/bin/env python3
"""
Pellet validation pipeline (library module).

Differs from editor.reasoning_service in two critical ways:
  1. Merges proethica-core and proethica-intermediate from local disk into the
     case graph BEFORE reasoning, so the AllDisjointClasses axiom and the
     BFO/IAO superclass chain are actually present for Pellet to check.
  2. Strips owl:imports triples for EXTERNAL vocabularies (BFO, IAO, RO,
     OWL-Time) so owlready2 does not attempt to fetch them over the network.

Usage (as library):
    from pellet_validate import validate_case
    result = validate_case("proethica-case-72")
"""
import hashlib
import logging
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import rdflib
from rdflib import Graph, OWL, RDF, URIRef, Literal

ONTSERVE_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ONTSERVE_ROOT / "web"
sys.path.insert(0, str(ONTSERVE_ROOT))
sys.path.insert(0, str(WEB_DIR))

FOUNDATION_TTL = ONTSERVE_ROOT / "ontologies" / "proethica-foundation.ttl"
CORE_TTL = ONTSERVE_ROOT / "ontologies" / "proethica-core.ttl"
INTERMEDIATE_TTL = ONTSERVE_ROOT / "ontologies" / "proethica-intermediate.ttl"

log = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    ontology_name: str
    consistent: bool
    runtime_seconds: float
    triples_merged: int
    classes_loaded: int
    properties_loaded: int
    individuals_loaded: int
    inferred_type_assertions: int = 0
    inferred_subclass_assertions: int = 0
    disjointness_violations: int = 0
    error: Optional[str] = None
    error_explanation: Optional[str] = None


def _load_graph(ttl_path: Path) -> Graph:
    g = Graph()
    g.parse(str(ttl_path), format="turtle")
    return g


def _fetch_case_content_from_db(ontology_name: str) -> str:
    """Load case TTL from ontology_versions (current)."""
    from config.config_loader import load_ontserve_config
    load_ontserve_config()
    from flask import Flask
    from web.app_config import config as flask_config
    from web.models import db, init_db, Ontology, OntologyVersion

    app = Flask(__name__)
    app.config.from_object(flask_config[os.environ.get("FLASK_CONFIG", "development")])
    init_db(app)
    with app.app_context():
        ont = Ontology.query.filter_by(name=ontology_name).first()
        if not ont:
            raise RuntimeError(f"ontology {ontology_name} not found")
        ver = OntologyVersion.query.filter_by(
            ontology_id=ont.id, is_current=True
        ).first()
        if not ver:
            raise RuntimeError(f"no current version for {ontology_name}")
        return ver.content


CATEGORY_TO_CORE = {
    "Role": URIRef("http://proethica.org/ontology/core#Role"),
    "Principle": URIRef("http://proethica.org/ontology/core#Principle"),
    "Obligation": URIRef("http://proethica.org/ontology/core#Obligation"),
    "State": URIRef("http://proethica.org/ontology/core#State"),
    "Resource": URIRef("http://proethica.org/ontology/core#Resource"),
    "Action": URIRef("http://proethica.org/ontology/core#Action"),
    "Event": URIRef("http://proethica.org/ontology/core#Event"),
    "Capability": URIRef("http://proethica.org/ontology/core#Capability"),
    "Constraint": URIRef("http://proethica.org/ontology/core#Constraint"),
}
CONCEPT_CATEGORY = URIRef("http://proethica.org/ontology/intermediate#conceptCategory")
RDFS_SUBCLASSOF = URIRef("http://www.w3.org/2000/01/rdf-schema#subClassOf")


def _add_missing_subclass_declarations(g: Graph) -> int:
    """For each LLM-generated class used as rdf:type but not declared with
    rdfs:subClassOf, derive the parent core class from the conceptCategory
    field of its instances and add the missing declaration.

    Returns the number of subClassOf triples added.
    """
    added = 0
    # Collect all (class_uri -> conceptCategory) from individual instances
    class_categories = {}
    for ind in g.subjects(RDF.type, OWL.NamedIndividual):
        for _, _, cls in g.triples((ind, RDF.type, None)):
            if cls == OWL.NamedIndividual:
                continue
            # Check if class already has a subClassOf declaration
            existing = list(g.objects(cls, RDFS_SUBCLASSOF))
            if existing:
                continue
            if cls not in class_categories:
                # Read the conceptCategory from this individual
                cats = list(g.objects(ind, CONCEPT_CATEGORY))
                if cats:
                    class_categories[cls] = str(cats[0])

    for cls_uri, cat in class_categories.items():
        core_parent = CATEGORY_TO_CORE.get(cat)
        if core_parent:
            g.add((cls_uri, RDF.type, OWL.Class))
            g.add((cls_uri, RDFS_SUBCLASSOF, core_parent))
            added += 1

    return added


def _build_merged_graph(case_content: str) -> Graph:
    g = Graph()
    # Foundation stub first: the curated BFO/IAO/RO subset core aligns to, declared
    # locally so the alignment is reasoned (branch disjointness + subclass chains) rather
    # than dangling. Replaces reliance on the stripped external bfo.owl/iao.owl/ro.owl.
    g.parse(str(FOUNDATION_TTL), format="turtle")
    g.parse(str(CORE_TTL), format="turtle")
    g.parse(str(INTERMEDIATE_TTL), format="turtle")
    g.parse(data=case_content, format="turtle")

    # Remove ALL owl:imports triples — we've merged everything we need locally.
    for s, p, o in list(g.triples((None, OWL.imports, None))):
        g.remove((s, p, o))

    # Add missing rdfs:subClassOf for LLM-generated types
    n = _add_missing_subclass_declarations(g)
    if n:
        log.info("Added %d missing subClassOf declarations from conceptCategory", n)

    return g


def validate_case(ontology_name: str) -> ValidationResult:
    import owlready2

    t0 = time.time()

    try:
        case_content = _fetch_case_content_from_db(ontology_name)
    except Exception as exc:
        return ValidationResult(
            ontology_name=ontology_name,
            consistent=False,
            runtime_seconds=0.0,
            triples_merged=0,
            classes_loaded=0,
            properties_loaded=0,
            individuals_loaded=0,
            error=f"db-fetch-failed: {exc}",
        )

    return validate_case_from_content(ontology_name, case_content, t0)


def validate_case_from_content(
    ontology_name: str, case_content: str, t_start: Optional[float] = None
) -> ValidationResult:
    import owlready2

    if t_start is None:
        t_start = time.time()

    try:
        merged = _build_merged_graph(case_content)
    except Exception as exc:
        return ValidationResult(
            ontology_name=ontology_name,
            consistent=False,
            runtime_seconds=time.time() - t_start,
            triples_merged=0,
            classes_loaded=0,
            properties_loaded=0,
            individuals_loaded=0,
            error=f"merge-failed: {exc}",
        )

    triples_merged = len(merged)

    # Use N-Triples: simpler format than RDF/XML, and much more robust for
    # IRIs containing em dashes, apostrophes, or other characters that break
    # rdflib's RDF/XML serializer or owlready2's XML parser.
    try:
        serialized = merged.serialize(format="nt")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".nt", delete=False, encoding="utf-8"
        ) as f:
            f.write(serialized)
            tmp_path = f.name
    except Exception as exc:
        return ValidationResult(
            ontology_name=ontology_name,
            consistent=False,
            runtime_seconds=time.time() - t_start,
            triples_merged=triples_merged,
            classes_loaded=0,
            properties_loaded=0,
            individuals_loaded=0,
            error=f"nt-serialize-failed: {type(exc).__name__}",
            error_explanation=str(exc)[:500],
        )

    try:
        try:
            world = owlready2.World()
            onto = world.get_ontology(f"file://{tmp_path}").load(format="ntriples")
        except Exception as parse_exc:
            return ValidationResult(
                ontology_name=ontology_name,
                consistent=False,
                runtime_seconds=time.time() - t_start,
                triples_merged=triples_merged,
                classes_loaded=0,
                properties_loaded=0,
                individuals_loaded=0,
                error=f"owlready-parse-failed: {type(parse_exc).__name__}",
                error_explanation=str(parse_exc)[:500],
            )

        classes_before = len(list(onto.classes()))
        properties_before = len(list(onto.properties()))
        individuals_before = len(list(onto.individuals()))

        consistent = True
        err = None
        err_explanation = None
        inferred_types = 0
        inferred_subclasses = 0
        disjointness_violations = 0

        # Snapshot: map individual -> set of class IRIs before reasoning
        types_before = {
            str(ind): {str(c) for c in ind.is_a}
            for ind in onto.individuals()
        }
        # Snapshot: map class -> set of parent IRIs before reasoning
        sub_before = {
            str(cls): {str(p) for p in cls.is_a}
            for cls in onto.classes()
        }

        try:
            with onto:
                owlready2.sync_reasoner_pellet(
                    world, infer_property_values=False, debug=0
                )
        except owlready2.OwlReadyInconsistentOntologyError as e:
            consistent = False
            err = "OwlReadyInconsistentOntologyError"
            err_explanation = str(e)[:1000]

        if consistent:
            # Count inferred type assertions: individuals that gained is_a entries
            for ind in onto.individuals():
                after = {str(c) for c in ind.is_a}
                gained = after - types_before.get(str(ind), set())
                inferred_types += len(gained)
            for cls in onto.classes():
                after = {str(p) for p in cls.is_a}
                gained = after - sub_before.get(str(cls), set())
                inferred_subclasses += len(gained)

            # Check for individuals typed as owl:Nothing (soft disjointness violation)
            for ind in onto.individuals():
                if any("Nothing" in str(c) for c in ind.is_a):
                    disjointness_violations += 1

        return ValidationResult(
            ontology_name=ontology_name,
            consistent=consistent,
            runtime_seconds=time.time() - t_start,
            triples_merged=triples_merged,
            classes_loaded=classes_before,
            properties_loaded=properties_before,
            individuals_loaded=individuals_before,
            inferred_type_assertions=inferred_types,
            inferred_subclass_assertions=inferred_subclasses,
            disjointness_violations=disjointness_violations,
            error=err,
            error_explanation=err_explanation,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    import json
    name = sys.argv[1] if len(sys.argv) > 1 else "proethica-case-72"
    result = validate_case(name)
    print(json.dumps(asdict(result), indent=2))
