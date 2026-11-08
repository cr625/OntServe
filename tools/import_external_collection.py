#!/usr/bin/env python3
"""
Import an external ontology collection from a manifest into OntServe.

    python tools/import_external_collection.py \\
        --manifest config/external/robotics.yaml --source-dir ~/dev/physical/ontologies
    python tools/import_external_collection.py --manifest ... --source-dir ... --dry-run
    python tools/import_external_collection.py --manifest ... --source-dir ... --only soma

services/external_collection.py describes the manifest and the steps. Each
entry is converted to Turtle at ontologies/external/<category-slug>/<name>.ttl
and registered in the database of ONTSERVE_DB_URL, with the configuration of
FLASK_CONFIG (as tools/sync_ontology_to_db.py). A re-run with unchanged input
changes nothing. --dry-run writes no file and rolls the database back. The
exit status is 1 when an entry fails.

Production is restored from the development database ``ontserve``, so the
tool refuses a database of that name unless --allow-main-database is given.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
# ROOT must precede ROOT/web: both contain a `services` package, and the
# root one carries external_collection (web/services would shadow it).
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT))

from config.config_loader import load_ontserve_config  # noqa: E402

load_ontserve_config()

from flask import Flask  # noqa: E402
from web.app_config import config as flask_config  # noqa: E402
from web.models import db, init_db  # noqa: E402
from services.external_collection import ManifestError, import_collection, load_manifest  # noqa: E402

MAIN_DATABASE = "ontserve"


def make_app() -> Flask:
    """The Flask app with its configuration, before the database is initialised."""
    app = Flask(__name__)
    app.config.from_object(flask_config[os.environ.get("FLASK_CONFIG", "development")])
    return app


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, required=True, help="collection manifest (YAML)")
    ap.add_argument("--source-dir", type=Path, required=True,
                    help="folder the file paths of the manifest are relative to")
    ap.add_argument("--only", action="append", metavar="NAME", default=[],
                    help="import only this entry (repeatable)")
    ap.add_argument("--dry-run", action="store_true", help="report the changes, write nothing")
    ap.add_argument("--ontologies-dir", type=Path, default=ROOT / "ontologies",
                    help="the ontologies folder (default: the one of this checkout)")
    ap.add_argument("--allow-main-database", action="store_true",
                    help=f"permit the database named {MAIN_DATABASE}")
    args = ap.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    app = make_app()
    url = app.config["SQLALCHEMY_DATABASE_URI"]
    masked = re.sub(r'(://[^:/@]*:)[^@]*@', r'\1****@', url)
    print(f"Database: {masked}")
    if urlparse(url).path.lstrip("/") == MAIN_DATABASE and not args.allow_main_database:
        print(f"ERROR: the database {MAIN_DATABASE} is the one production is restored from. "
              f"Set ONTSERVE_DB_URL to another database or pass --allow-main-database.", file=sys.stderr)
        return 1
    init_db(app)
    print(f"Collection: {manifest.collection} ({manifest.category}), {len(manifest.entries)} entries"
          + (" [dry run]" if args.dry_run else ""))

    namespace = app.config["ONTOLOGY_NAMESPACE_TEMPLATE"].format(
        base_uri=app.config["ONTOLOGY_BASE_URI"], name="").rstrip("#")
    with app.app_context():
        try:
            results = import_collection(db.session, manifest, args.source_dir.expanduser(),
                                        args.ontologies_dir, namespace, only=args.only,
                                        dry_run=args.dry_run)
        except ManifestError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    failed = [r["name"] for r in results if not r.get("ok")]
    if failed:
        print(f"{len(failed)} of {len(results)} entries failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
