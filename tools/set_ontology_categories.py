#!/usr/bin/env python3
"""
Set the explicit category / subcategory of ontologies (metadata.category and
metadata.subcategory, the values services.ontology_categories.resolve() reads
before falling back to its rule defaults).

Usage:
    # one ontology
    python tools/set_ontology_categories.py --set proethica-case-7 --category Cases --subcategory 2020s

    # many, from a manifest {"<ontology name>": {"category": ..., "subcategory": ...}, ...}
    python tools/set_ontology_categories.py --manifest tools/migrations/case_categories.json

    # clear an explicit value (rule default applies again)
    python tools/set_ontology_categories.py --set proethica-case-7 --clear subcategory

    # report the resolved classification of every ontology
    python tools/set_ontology_categories.py --report

Idempotent: unchanged rows are not rewritten. Uses the same config bootstrap as
tools/sync_ontology_to_db.py (FLASK_CONFIG, ONTSERVE_DB_URL).
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# ROOT must precede ROOT/web: both contain a `services` package, and the
# root one carries ontology_categories (web/services would shadow it).
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT))

from config.config_loader import load_ontserve_config  # noqa: E402

load_ontserve_config()

from flask import Flask  # noqa: E402
from sqlalchemy import select  # noqa: E402

from web.app_config import config as flask_config  # noqa: E402
from web.models import db, init_db, Ontology  # noqa: E402
from services import ontology_categories as categories  # noqa: E402


def make_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(flask_config[os.environ.get("FLASK_CONFIG", "development")])
    init_db(app)
    return app


def apply(session, name: str, category=None, subcategory=None, clear=()) -> str:
    ont = session.execute(select(Ontology).where(Ontology.name == name)).scalar_one_or_none()
    if ont is None:
        return f'{name}: NOT FOUND'
    md = dict(ont.meta_data or {})
    before = dict(md)
    if category is not None:
        md[categories.CATEGORY_KEY] = category.strip()
    if subcategory is not None:
        md[categories.SUBCATEGORY_KEY] = subcategory.strip()
    for key in clear:
        md.pop(key, None)
    if md == before:
        return f'{name}: unchanged'
    ont.meta_data = md   # reassign: db.JSON is not mutation-tracked
    return f'{name}: {before.get("category")}/{before.get("subcategory")} -> {md.get("category")}/{md.get("subcategory")}'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--set', metavar='NAME', help='ontology name to update')
    ap.add_argument('--category')
    ap.add_argument('--subcategory')
    ap.add_argument('--clear', action='append', choices=['category', 'subcategory'], default=[])
    ap.add_argument('--manifest', type=Path, help='JSON file: {name: {category, subcategory}}')
    ap.add_argument('--report', action='store_true', help='print resolved classification for all ontologies')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args(argv)

    app = make_app()
    with app.app_context():
        session = db.session
        if args.report:
            onts = session.execute(select(Ontology).order_by(Ontology.name)).scalars().all()
            for grp in categories.group_ontologies(onts):
                print(f'== {grp.category.label} ({grp.count}){"  [collapsed]" if grp.collapsed else ""}')
                for sub, n in grp.subgroups:
                    print(f'   {sub or "(none)"}: {n}')
            return 0

        lines = []
        if args.set:
            lines.append(apply(session, args.set, args.category, args.subcategory, args.clear))
        if args.manifest:
            manifest = json.loads(args.manifest.read_text())
            for name, spec in manifest.items():
                lines.append(apply(session, name, spec.get('category'), spec.get('subcategory'),
                                   spec.get('clear', [])))
        if not lines:
            ap.error('nothing to do: pass --set, --manifest or --report')
        for line in lines:
            print(line)
        changed = sum(1 for l in lines if '->' in l)
        if args.dry_run:
            session.rollback()
            print(f'dry run: {changed} would change')
        else:
            session.commit()
            print(f'committed: {changed} changed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
