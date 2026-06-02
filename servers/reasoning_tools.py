"""Reasoning + validation backends for the OntServe MCP reasoning tools.

Wraps the proven Pellet validation harness (`validation/pellet_validate.py`, the
engine behind the 119/119-consistent corpus claim) and the BFO compliance
validator (`editor/services.OntologyValidationService`) as plain synchronous
functions. The FastMCP tool wrappers in `mcp_server.py` call these via
`asyncio.to_thread` (Pellet runs a blocking Java subprocess).

Why Pellet/`pellet_validate` rather than `OwlreadyImporter`: a case ontology's
disjointness axioms live in `proethica-core`, not the case file. `pellet_validate`
merges core + intermediate + case, strips `owl:imports`, and back-fills
`subClassOf` from `conceptCategory` before reasoning, so consistency results are
trustworthy. `OwlreadyImporter.import_from_file` reasons over a single TTL and
would miss the cross-ontology axioms.

`reason_ontology` / `check_consistency` reuse `validate_case` unchanged. The
detail tools (`get_inferred_hierarchy`, `get_inconsistent_classes`) need the
actual inferred edges / owl:Nothing entities that `validate_case` only counts, so
`reason_detailed` re-runs the same merge+reason recipe (reusing pellet_validate's
helpers) and collects the lists — without mutating the load-bearing `validate_case`.
"""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import asdict
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Cap list payloads so a dense case can't return a multi-thousand-row blob.
_MAX_ITEMS = 300


def reason_ontology(ontology_name: str) -> Dict[str, Any]:
    """Run Pellet over a stored ontology (merged core+intermediate+case) and
    return the full ValidationResult (consistency + inference counts + timing)."""
    from validation.pellet_validate import validate_case
    return asdict(validate_case(ontology_name))


def check_consistency(ontology_name: str) -> Dict[str, Any]:
    """Lightweight consistency view: is the ontology logically consistent?"""
    from validation.pellet_validate import validate_case
    r = validate_case(ontology_name)
    return {
        "ontology_name": r.ontology_name,
        "consistent": r.consistent,
        "disjointness_violations": r.disjointness_violations,
        "runtime_seconds": r.runtime_seconds,
        "error": r.error,
        "error_explanation": r.error_explanation,
    }


def reason_detailed(ontology_name: str, content: str | None = None) -> Dict[str, Any]:
    """Run Pellet and return the ACTUAL inferred edges and owl:Nothing entities,
    not just counts. Backs get_inferred_hierarchy + get_inconsistent_classes.

    Mirrors pellet_validate.validate_case_from_content's reason loop but collects
    the gained (child->parent) subclass edges, gained (individual->type) edges,
    and the individuals forced to owl:Nothing (disjointness violations).

    `content` (case TTL) may be passed to skip the DB fetch — used by tests to run
    against an on-disk fixture without a database.
    """
    import owlready2
    from validation.pellet_validate import (
        _fetch_case_content_from_db,
        _build_merged_graph,
    )

    base = {
        "ontology_name": ontology_name,
        "consistent": False,
        "inferred_subclasses": [],
        "inferred_types": [],
        "nothing_entities": [],
        "inferred_subclass_count": 0,
        "inferred_type_count": 0,
        "truncated": False,
        "error": None,
    }

    if content is None:
        try:
            content = _fetch_case_content_from_db(ontology_name)
        except Exception as exc:  # noqa: BLE001 - surface fetch failure to caller
            base["error"] = f"db-fetch-failed: {exc}"
            return base

    try:
        merged = _build_merged_graph(content)
        serialized = merged.serialize(format="nt")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".nt", delete=False, encoding="utf-8"
        ) as f:
            f.write(serialized)
            tmp_path = f.name
    except Exception as exc:  # noqa: BLE001
        base["error"] = f"merge/serialize-failed: {type(exc).__name__}: {exc}"
        return base

    try:
        world = owlready2.World()
        onto = world.get_ontology(f"file://{tmp_path}").load(format="ntriples")

        types_before = {
            str(ind): {str(c) for c in ind.is_a} for ind in onto.individuals()
        }
        sub_before = {
            str(cls): {str(p) for p in cls.is_a} for cls in onto.classes()
        }

        try:
            with onto:
                owlready2.sync_reasoner_pellet(
                    world, infer_property_values=False, debug=0
                )
            base["consistent"] = True
        except owlready2.OwlReadyInconsistentOntologyError as e:
            base["consistent"] = False
            base["error"] = "OwlReadyInconsistentOntologyError"
            base["error_explanation"] = str(e)[:1000]

        if base["consistent"]:
            sub_edges: List[Dict[str, str]] = []
            type_edges: List[Dict[str, str]] = []
            nothing: List[str] = []

            _TRIVIAL = {
                "http://www.w3.org/2002/07/owl#Thing",
                "http://www.w3.org/2002/07/owl#Nothing",
            }

            def _named_iri(e):
                # Keep only NAMED inferred parents/types: real .iri, not owl:Thing/Nothing.
                # Anonymous restriction superclasses (no .iri) are reasoner noise for a
                # hierarchy view and are skipped.
                iri = getattr(e, "iri", None)
                if iri and iri not in _TRIVIAL:
                    return iri
                return None

            for cls in onto.classes():
                before = sub_before.get(str(cls), set())
                for p in cls.is_a:
                    if str(p) in before:
                        continue
                    parent_iri = _named_iri(p)
                    if parent_iri:
                        sub_edges.append({"child": str(cls.iri), "parent": parent_iri})
            for ind in onto.individuals():
                before = types_before.get(str(ind), set())
                for c in ind.is_a:
                    if str(c) in before:
                        continue
                    type_iri = _named_iri(c)
                    if type_iri:
                        type_edges.append({"individual": str(ind.iri), "type": type_iri})
                if any("Nothing" in str(c) for c in ind.is_a):
                    nothing.append(str(ind.iri))

            base["inferred_subclass_count"] = len(sub_edges)
            base["inferred_type_count"] = len(type_edges)
            base["nothing_entities"] = nothing[:_MAX_ITEMS]
            base["inferred_subclasses"] = sub_edges[:_MAX_ITEMS]
            base["inferred_types"] = type_edges[:_MAX_ITEMS]
            if len(sub_edges) > _MAX_ITEMS or len(type_edges) > _MAX_ITEMS:
                base["truncated"] = True
        return base
    except Exception as exc:  # noqa: BLE001
        base["error"] = f"reason-failed: {type(exc).__name__}: {exc}"
        return base
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def get_inferred_hierarchy(ontology_name: str) -> Dict[str, Any]:
    """Inferred class-subsumption + type assertions discovered by the reasoner."""
    d = reason_detailed(ontology_name)
    return {
        "ontology_name": ontology_name,
        "consistent": d["consistent"],
        "inferred_subclasses": d["inferred_subclasses"],
        "inferred_types": d["inferred_types"],
        "inferred_subclass_count": d["inferred_subclass_count"],
        "inferred_type_count": d["inferred_type_count"],
        "truncated": d["truncated"],
        "error": d.get("error"),
    }


def get_inconsistent_classes(ontology_name: str) -> Dict[str, Any]:
    """Entities the reasoner forces to owl:Nothing (disjointness violations), plus
    a hard-inconsistency flag/explanation if the whole ontology is inconsistent."""
    d = reason_detailed(ontology_name)
    return {
        "ontology_name": ontology_name,
        "consistent": d["consistent"],
        "nothing_entities": d["nothing_entities"],
        "nothing_count": len(d["nothing_entities"]),
        "error": d.get("error"),
        "error_explanation": d.get("error_explanation"),
    }


def validate_bfo_compliance(ontology_name: str) -> Dict[str, Any]:
    """Run the BFO/PROV-O/intermediate compliance checks (errors + warnings) over
    a stored ontology's TTL, via editor.services.OntologyValidationService."""
    from config.config_loader import load_ontserve_config
    load_ontserve_config()
    from flask import Flask
    from web.app_config import config as flask_config
    from web.models import db, init_db, Ontology, OntologyVersion
    from editor.services import OntologyValidationService

    app = Flask(__name__)
    app.config.from_object(flask_config[os.environ.get("FLASK_CONFIG", "development")])
    init_db(app)
    with app.app_context():
        ont = Ontology.query.filter_by(name=ontology_name).first()
        if not ont:
            return {"ontology_name": ontology_name, "error": "ontology not found"}
        ver = OntologyVersion.query.filter_by(
            ontology_id=ont.id, is_current=True
        ).first()
        if not ver or not ver.content:
            return {"ontology_name": ontology_name, "error": "no current version content"}
        try:
            # Resolve BFO inheritance over the merged foundation+core+intermediate+case
            # graph (read from disk by pellet_validate), so transitive subClassOf chains
            # through proethica-core and IAO are visible and indirect BFO inheritance is
            # recognised instead of false-flagged. Same merge recipe the reasoning tools use.
            from validation.pellet_validate import _build_merged_graph
            merged = _build_merged_graph(ver.content)
            result = OntologyValidationService(storage_backend=None).validate_ontology(
                ver.content, context_graph=merged
            )
        except Exception as exc:  # noqa: BLE001
            return {"ontology_name": ontology_name,
                    "error": f"validation-failed: {type(exc).__name__}: {exc}"}
        result["ontology_name"] = ontology_name
        return result
