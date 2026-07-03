#!/usr/bin/env python3
"""Rebuild the 'Relations Ontology 2015' DB row (id 22) as an honest curated
RO subset stub.

Background (2026-07-02 external-ontology validity review): the stored content
was a mislabeled 28-term grab-bag (10 RO + 9 BFO + 3 ENVO + 3 GO + 2 CL + 1
PATO), with no rdf:type on any term, definitions that were rdfs:comment copies
(one -- CL_0000540 "neuron" -- semantically misattributed), four upstream-
obsolete terms, all entity rows mistyped 'individual', and both the base_uri
column and the owl:Ontology header reusing the canonical obo/ro.owl IRI (so the
artifact would masquerade as / clobber the real Relations Ontology).

ProEthica's actual RO dependency is five object-property groundings in
proethica-core (has role, role of, participates in, has participant, causally
upstream of), all also declared in proethica-foundation (the copy the reasoner
loads). This rebuild replaces the row's content with exactly those five terms,
correctly typed as owl:ObjectProperty, carrying the canonical OBO RO labels and
definitions (verbatim from proethica-foundation.ttl:158-183). Term IRIs stay in
the obo/RO_ namespace; only the ontology document IRI becomes a proethica.org
IRI so it no longer collides with obo/ro.owl.

The row name is left as 'Relations Ontology 2015' so tools/verify_paper_claims.py
and the /ontology/<name> page keep resolving; the new stub marker (metadata.stub)
is what signals it is a hosted subset rather than the full upstream RO.

Idempotent: re-running creates another version only if the content hash differs.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from config.config_loader import load_ontserve_config  # noqa: E402

load_ontserve_config()

from flask import Flask  # noqa: E402
from sqlalchemy import select  # noqa: E402

from web.app_config import config as flask_config  # noqa: E402
from web.models import db, init_db, Ontology, OntologyVersion  # noqa: E402
from web.entity_extraction import extract_entities_from_content  # noqa: E402

ROW_NAME = "Relations Ontology 2015"
NEW_BASE_URI = "http://proethica.org/ontology/relations-subset#"
ONTOLOGY_IRI = "http://proethica.org/ontology/relations-subset"

HONEST_TTL = f"""@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix ro: <http://purl.obolibrary.org/obo/RO_> .
@prefix obo: <http://purl.obolibrary.org/obo/> .

<{ONTOLOGY_IRI}> a owl:Ontology ;
    rdfs:label "Relations Ontology 2015"@en ;
    dcterms:title "OBO Relations Ontology - curated subset (stub)"@en ;
    rdfs:comment "Curated STUB, not the full OBO Relations Ontology. Hosts only the five RO object properties proethica-core grounds its role, action and causal relations under. Term IRIs remain in the canonical obo/RO_ namespace; only this ontology document carries a proethica.org IRI, so it does not masquerade as or clobber the canonical obo/ro.owl. proethica-foundation holds the copy the reasoner loads."@en ;
    owl:versionInfo "subset-1.0.0"@en ;
    dcterms:source <http://purl.obolibrary.org/obo/ro.owl> .

ro:0000087 a owl:ObjectProperty ;
    rdfs:label "has role"@en ;
    skos:definition "A relation between an independent continuant (the bearer) and a role, in which the role specifically depends on the bearer."@en ;
    rdfs:isDefinedBy obo:ro.owl .

ro:0000081 a owl:ObjectProperty ;
    owl:inverseOf ro:0000087 ;
    rdfs:label "role of"@en ;
    skos:definition "a relation between a role and an independent continuant (the bearer), in which the role specifically depends on the bearer for its existence"@en ;
    rdfs:isDefinedBy obo:ro.owl .

ro:0000056 a owl:ObjectProperty ;
    rdfs:label "participates in"@en ;
    skos:definition "A relation between a continuant and a process, in which the continuant is somehow involved in the process."@en ;
    rdfs:isDefinedBy obo:ro.owl .

ro:0000057 a owl:ObjectProperty ;
    owl:inverseOf ro:0000056 ;
    rdfs:label "has participant"@en ;
    skos:definition "A relation between a process and a continuant, in which the continuant is somehow involved in the process. Inverse of participates in."@en ;
    rdfs:isDefinedBy obo:ro.owl .

ro:0002411 a owl:ObjectProperty ;
    rdfs:label "causally upstream of"@en ;
    skos:definition "p is causally upstream of q iff p is causally related to q, the end of p precedes the end of q, and p is not an occurrent part of q."@en ;
    rdfs:isDefinedBy obo:ro.owl .
"""


def main() -> int:
    app = Flask(__name__)
    app.config.from_object(flask_config[os.environ.get("FLASK_CONFIG", "development")])
    init_db(app)

    with app.app_context():
        ontology = db.session.execute(
            select(Ontology).where(Ontology.name == ROW_NAME)
        ).scalar_one_or_none()
        if ontology is None:
            print(f"ERROR: no ontology row named {ROW_NAME!r}")
            return 1

        new_hash = hashlib.sha256(HONEST_TTL.encode("utf-8")).hexdigest()

        latest = db.session.execute(
            select(OntologyVersion)
            .where(OntologyVersion.ontology_id == ontology.id)
            .order_by(OntologyVersion.version_number.desc())
        ).scalars().first()

        if latest and latest.content_hash == new_hash and latest.is_current:
            print("Content already current (hash match); nothing to do.")
        else:
            if latest:
                latest.is_current = False
            new_version = OntologyVersion(
                ontology_id=ontology.id,
                version_number=(latest.version_number + 1) if latest else 1,
                content=HONEST_TTL,
                content_hash=new_hash,
                version_tag="curated-ro-subset",
                change_summary="Rebuilt as honest curated RO subset stub (5 grounding properties); "
                               "removed foreign OBO terms, added rdf:type, fixed definitions, "
                               "de-collided the obo/ro.owl IRI.",
                created_by="rebuild_relations_subset",
                is_current=True,
                is_draft=False,
                workflow_status="published",
            )
            db.session.add(new_version)
            db.session.flush()
            counts = extract_entities_from_content(ontology, HONEST_TTL)
            print(f"New version {new_version.version_number}; re-extracted entities: {counts}")

        # De-collide the ontology-document IRI and mark it a stub.
        ontology.base_uri = NEW_BASE_URI
        md = dict(ontology.meta_data or {})
        md["stub"] = True
        md["source"] = "http://purl.obolibrary.org/obo/ro.owl"
        md["version"] = "subset-1.0.0"
        ontology.meta_data = md

        db.session.commit()
        print(f"base_uri -> {ontology.base_uri}; metadata.stub = True")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
