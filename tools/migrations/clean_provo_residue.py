#!/usr/bin/env python3
"""Remove the local-path ingestion leak from the stored w3c-prov-o content.

The 2025-08-28 ttl_integration_script re-serialized the PROV family with a
file:// base, which resolved the PROV-O-inverses module's relative ontology IRI
to a local filesystem path: `<file:///home/chris/onto/proethica/#> a owl:Ontology`.
That stanza is otherwise a legitimate PROV-O-inverses header (its versionIRI /
specializationOf / wasRevisionOf all point at http://www.w3.org/ns/prov-o-inverses*),
so this repoints the corrupted subject to the correct canonical IRI rather than
dropping the header. No term declarations are touched; the entity set is unchanged.

Idempotent. Leaves the corpus-wide skos:definition normalization in place (that is
intentional across all hosted ontologies, not prov-o residue).
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# ROOT must precede ROOT/web: both contain a `services` package, and the root
# one carries ontology_sync_service / ontology_categories (web/services would
# shadow it, e.g. via Ontology.classification).
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT))

from config.config_loader import load_ontserve_config  # noqa: E402

load_ontserve_config()

from flask import Flask  # noqa: E402
from sqlalchemy import select  # noqa: E402

from web.app_config import config as flask_config  # noqa: E402
from web.models import db, init_db, Ontology, OntologyVersion  # noqa: E402
from web.entity_extraction import extract_entities_from_content  # noqa: E402

ROW_NAME = "w3c-prov-o"
BAD_IRI = "<file:///home/chris/onto/proethica/#>"
GOOD_IRI = "<http://www.w3.org/ns/prov-o-inverses>"


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

        latest = db.session.execute(
            select(OntologyVersion)
            .where(OntologyVersion.ontology_id == ontology.id)
            .order_by(OntologyVersion.version_number.desc())
        ).scalars().first()
        if latest is None:
            print("ERROR: no version content to clean")
            return 1

        content = latest.content
        if BAD_IRI not in content:
            print("No local-path leak present; nothing to do.")
            return 0

        cleaned = content.replace(BAD_IRI, GOOD_IRI)
        new_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()

        latest.is_current = False
        new_version = OntologyVersion(
            ontology_id=ontology.id,
            version_number=latest.version_number + 1,
            content=cleaned,
            content_hash=new_hash,
            version_tag="residue-cleanup",
            change_summary="Repoint the PROV-O-inverses header subject from the "
                           "file:///home/chris/... ingestion leak to its canonical "
                           "http://www.w3.org/ns/prov-o-inverses IRI.",
            created_by="clean_provo_residue",
            is_current=True,
            is_draft=False,
            workflow_status="published",
        )
        db.session.add(new_version)
        db.session.flush()
        counts = extract_entities_from_content(ontology, cleaned)
        db.session.commit()
        print(f"Cleaned. New version {new_version.version_number}; entities: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
