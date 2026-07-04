#!/usr/bin/env python3
"""
Sync ONE ontology TTL file from disk into the OntServe database.

Thin CLI wrapper over services.ontology_sync_service.OntologySyncService.
_sync_single_ontology, the same proven importer the web app runs on startup
(web/app.py:75). It creates the Ontology record if missing (registration),
writes a NEW current ontology_versions row from the disk TTL content when the
file hash differs (version import), and re-extracts the flattened
ontology_entities rows.

This replaces the two broken disk->DB paths the ProEthica commit service used
to shell out to: scripts/register_case_ontologies.py (never existed) and
scripts/refresh_entity_extraction.py (relocated to tools/, and refreshes only
the entity table, never the version content where edges live). Keeping disk and
DB in lockstep here is what prevents the case-103-class regression where a later
startup sync silently reverts DB-only edge materialization.

    python tools/sync_ontology_to_db.py proethica-case-8
    python tools/sync_ontology_to_db.py proethica-case-8 --force
    python tools/sync_ontology_to_db.py proethica-case-8 --summary "retyped X to Y"
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from config.config_loader import load_ontserve_config  # noqa: E402

load_ontserve_config()

from flask import Flask  # noqa: E402
from web.app_config import config as flask_config  # noqa: E402
from web.models import db, init_db  # noqa: E402
from services.ontology_sync_service import OntologySyncService  # noqa: E402


def make_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(flask_config[os.environ.get("FLASK_CONFIG", "development")])
    init_db(app)
    return app


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ontology_name", help="e.g. proethica-case-8")
    ap.add_argument("--force", action="store_true",
                    help="re-import even if the file hash is unchanged")
    ap.add_argument("--summary", default=None,
                    help="change summary recorded on the new ontology_versions row "
                         "(the DB history is the audit trail for gitignored case TTLs); "
                         "defaults to the generic auto-sync message")
    args = ap.parse_args()

    ontologies_dir = ROOT / "ontologies"
    ttl_path = ontologies_dir / f"{args.ontology_name}.ttl"
    if not ttl_path.exists():
        print(f"ERROR: TTL not found: {ttl_path}", file=sys.stderr)
        return 1

    app = make_app()
    with app.app_context():
        service = OntologySyncService(db.session, ontologies_dir)
        result = service._sync_single_ontology(ttl_path, force=args.force,
                                               change_summary=args.summary)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
