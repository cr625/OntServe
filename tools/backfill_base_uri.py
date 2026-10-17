#!/usr/bin/env python3
"""
Backfill ontologies.base_uri from the owl:Ontology IRI declared in each row's
current version content.

Rows registered by the startup sync before 2026-10 received the file-name
pattern http://proethica.org/ontology/<name># as base_uri. For a case ontology
that namespace occurs nowhere in the graph (the case namespace is
http://proethica.org/ontology/case/<n>#, the ontology IRI .../case/<n>), so the
case page header, the canonical Link header of the content-negotiation routes
and the generated @prefix line all named an IRI the ontology does not use (all
119 case rows, found in the case 24-1 review). The sync now reads the IRI at
import (services.ontology_sync_service.ontology_iri_from_graph) and repairs a
pattern-valued row on its next re-sync. This script repairs the rows that exist
now, without waiting for a re-commit.

Usage:
    python tools/backfill_base_uri.py --dry-run             # case rows, report only
    python tools/backfill_base_uri.py                       # case rows
    python tools/backfill_base_uri.py --all                 # every row whose content declares an IRI
    python tools/backfill_base_uri.py --name proethica-case-8

Only a row whose stored base_uri differs from the declared IRI is rewritten. A
row whose current content declares no owl:Ontology IRI is reported and left as
is. Idempotent. Uses the same config bootstrap as tools/sync_ontology_to_db.py
(FLASK_CONFIG, ONTSERVE_DB_URL).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# ROOT must precede ROOT/web: both contain a `services` package, and the
# root one carries ontology_sync_service (web/services would shadow it).
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT))

from config.config_loader import load_ontserve_config  # noqa: E402

load_ontserve_config()

from flask import Flask  # noqa: E402
from sqlalchemy import select  # noqa: E402

from web.app_config import config as flask_config  # noqa: E402
from web.models import db, init_db, Ontology  # noqa: E402
from services.ontology_categories import case_id_from_name  # noqa: E402
from services.ontology_sync_service import declared_base_uri  # noqa: E402


def make_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(flask_config[os.environ.get("FLASK_CONFIG", "development")])
    init_db(app)
    return app


def select_rows(session, name: str | None, every: bool):
    """The rows to examine: one by name, every row, or (default) the case rows
    (ontology_type 'case' or a proethica-case-<n> name)."""
    onts = session.execute(select(Ontology).order_by(Ontology.name)).scalars().all()
    if name:
        return [o for o in onts if o.name == name]
    if every:
        return onts
    return [o for o in onts if o.ontology_type == 'case' or case_id_from_name(o.name)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--name', metavar='NAME', help='one ontology to examine')
    ap.add_argument('--all', action='store_true', help='examine every row, not only the case rows')
    ap.add_argument('--dry-run', action='store_true', help='report without writing')
    args = ap.parse_args(argv)

    app = make_app()
    with app.app_context():
        session = db.session
        rows = select_rows(session, args.name, args.all)
        if args.name and not rows:
            print(f'{args.name}: NOT FOUND')
            return 1
        changed = 0
        for ont in rows:
            new_uri, reason = declared_base_uri(ont.name, ont.base_uri, ont.current_content)
            if new_uri:
                print(f'{ont.name}: {ont.base_uri} -> {new_uri}')
                ont.base_uri = new_uri
                changed += 1
            else:
                print(f'{ont.name}: {reason}')
        if args.dry_run:
            session.rollback()
            print(f'dry run: {changed} of {len(rows)} would change')
        else:
            session.commit()
            print(f'committed: {changed} of {len(rows)} changed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
