#!/usr/bin/env python3
"""
Phase 1.7 repair: ProfessionalCompetence subClassOf-Principle drift.

Root cause (uniform across the 18 inconsistent dev cases): each case TTL carries
a stale `proeth:ProfessionalCompetence rdfs:subClassOf proeth-core:Principle`
triple (a pre-fix conceptCategory-derived emission). proethica-intermediate
authoritatively declares ProfessionalCompetence subClassOf Capability, so the
merged graph makes the class both Capability AND Principle -> disjoint clash
under the nine-way AllDisjointClasses -> Pellet-inconsistent.

Fix per case:
  1. Remove the `ProfessionalCompetence subClassOf Principle` triple (defer to
     intermediate's authoritative Capability parent -- matches what a fresh
     commit now produces after the 2026-05-26 commit-typing fix).
  2. Reconcile the companion `conceptCategory = "Principle"` literal on
     ProfessionalCompetence individuals to "Capability" (Direction A: the
     reasoner-visible type chain is the source of truth).
  3. Pellet-verify the fixed content in the SAME context the corpus sweep uses
     (core + intermediate, conceptCategory fallback). Only persist if consistent.
  4. Write the fixed TTL to disk and re-import via OntologySyncService
     (force=True) -- canonical importer: sets content_hash from the disk file
     (DB/disk hash-locked, no startup re-drift) and refreshes entity rows.

Usage:
  python validation/fix_professional_competence_drift.py          # dry run
  python validation/fix_professional_competence_drift.py apply     # persist
"""
import os
import sys
from pathlib import Path

ONTSERVE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ONTSERVE_ROOT))
sys.path.insert(0, str(ONTSERVE_ROOT / "web"))
sys.path.insert(0, str(ONTSERVE_ROOT / "validation"))

from rdflib import Graph, RDF, RDFS, URIRef, Literal  # noqa: E402

from diagnose_drift import (  # noqa: E402
    _base_graph,
    _strip_external_imports,
    run_pellet,
    _add_missing_subclass_declarations,
)

CORE = "http://proethica.org/ontology/core#"
INT = "http://proethica.org/ontology/intermediate#"
PC = URIRef(INT + "ProfessionalCompetence")
PRIN = URIRef(CORE + "Principle")
CAP = URIRef(CORE + "Capability")
CC = URIRef(INT + "conceptCategory")

CASES = [7, 9, 12, 16, 58, 59, 85, 109, 112, 120, 131, 139, 142, 146, 147, 150, 161, 162]

BACKUP_DIR = Path("/tmp/drift_fix_backups")


def fix_graph(content: str):
    g = Graph()
    g.parse(data=content, format="turtle")
    removed = len(list(g.triples((PC, RDFS.subClassOf, PRIN))))
    g.remove((PC, RDFS.subClassOf, PRIN))
    cc_fixed = 0
    for ind in list(g.subjects(RDF.type, PC)):
        for o in list(g.objects(ind, CC)):
            if str(o) == "Principle":
                g.remove((ind, CC, o))
                g.add((ind, CC, Literal("Capability")))
                cc_fixed += 1
    return g, removed, cc_fixed


def pellet_ok(g: Graph):
    # Mirror the corpus sweep context exactly: core + intermediate (NOT extended)
    gm = _base_graph(with_extended=False)
    gm.parse(data=g.serialize(format="turtle"), format="turtle")
    _strip_external_imports(gm)
    _add_missing_subclass_declarations(gm)
    return run_pellet(gm)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "dry"
    apply = mode == "apply"

    from config.config_loader import load_ontserve_config
    load_ontserve_config()
    from flask import Flask
    from web.app_config import config as flask_config
    from web.models import db, init_db, Ontology, OntologyVersion
    from services.ontology_sync_service import OntologySyncService

    app = Flask(__name__)
    app.config.from_object(flask_config[os.environ.get("FLASK_CONFIG", "development")])
    init_db(app)

    if apply:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    ontologies_dir = ONTSERVE_ROOT / "ontologies"
    print(f"MODE: {'APPLY' if apply else 'DRY RUN'}\n")
    print(f"{'case':>5} {'rmTriple':>9} {'ccFix':>6} {'pellet':>8} {'action':>10}")

    all_ok = True
    with app.app_context():
        for c in CASES:
            name = f"proethica-case-{c}"
            ont = Ontology.query.filter_by(name=name).first()
            ver = OntologyVersion.query.filter_by(ontology_id=ont.id, is_current=True).first()
            content = ver.content

            g, removed, cc_fixed = fix_graph(content)
            cons, note = pellet_ok(g)
            cons_s = {True: "OK", False: "INCON", None: "ERR"}[cons]

            action = "-"
            if apply and cons:
                # per-case backup of the pre-fix current content
                (BACKUP_DIR / f"{name}_pre.ttl").write_text(content, encoding="utf-8")
                # write fixed content to disk and re-import via canonical sync
                disk = ontologies_dir / f"{name}.ttl"
                disk.write_text(g.serialize(format="turtle"), encoding="utf-8")
                svc = OntologySyncService(db.session, ontologies_dir)
                res = svc._sync_single_ontology(disk, force=True)
                action = res.get("action", "?") + f"/v{res.get('version','?')}"
            elif apply and not cons:
                all_ok = False
                action = "SKIP(incon)"

            print(f"{c:>5} {removed:>9} {cc_fixed:>6} {cons_s:>8} {action:>10}")

    print("\n" + ("All fixes consistent." if all_ok else "WARNING: some cases not consistent -- inspect."))
    if not apply:
        print("Dry run only. Re-run with 'apply' to persist (disk + DB + entity refresh).")


if __name__ == "__main__":
    main()
