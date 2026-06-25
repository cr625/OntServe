#!/usr/bin/env python3
"""Reload an ontology into the OntServe DB from its on-disk TTL.

Updates the current version's stored content (so the entity-detail source view reflects
file edits) AND refreshes the structured ontology_entities rows. One command for the
live edit -> view loop used when iterating on proethica-core.

Usage:
    ONTSERVE_DB_URL=postgresql://postgres:PASS@localhost:5432/ontserve \
        python tools/reload_ontology.py proethica-core
"""
import os
import sys
from pathlib import Path

script_dir = Path(__file__).parent
ontserve_root = script_dir.parent
web_dir = ontserve_root / 'web'
for p in (str(ontserve_root), str(web_dir), str(script_dir)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _update_version_content(name: str) -> bool:
    from flask import Flask
    import importlib.util
    config_spec = importlib.util.spec_from_file_location("web_config", str(web_dir / "app_config.py"))
    web_config_module = importlib.util.module_from_spec(config_spec)
    config_spec.loader.exec_module(web_config_module)
    config = web_config_module.config

    from models import db, Ontology, OntologyVersion

    ttl_path = ontserve_root / 'ontologies' / f'{name}.ttl'
    if not ttl_path.exists():
        print(f"TTL file not found: {ttl_path}")
        return False
    content = ttl_path.read_text()

    app = Flask(__name__)
    app.config.from_object(config[os.environ.get('FLASK_CONFIG', 'development')])
    db.init_app(app)
    with app.app_context():
        ont = Ontology.query.filter_by(name=name).first()
        if not ont:
            print(f"ontology '{name}' not found in DB")
            return False
        ver = OntologyVersion.query.filter_by(ontology_id=ont.id, is_current=True).first()
        if not ver:
            print(f"no current version for '{name}'")
            return False
        ver.content = content
        db.session.commit()
        print(f"version {ver.version_number} content updated from {ttl_path.name} ({len(content)} chars)")
    return True


def main(name: str) -> int:
    if not _update_version_content(name):
        return 1
    # Refresh the structured entity rows from the same file.
    from refresh_entity_extraction import refresh_ontology_entities
    refresh_ontology_entities(name)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'proethica-core'))
