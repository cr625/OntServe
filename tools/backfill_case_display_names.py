#!/usr/bin/env python3
"""
Backfill human-readable display names onto case ontologies.

Case ontologies are named ``proethica-case-<N>`` where ``<N>`` is the
ProEthica document id. The human case title (e.g. "Misrepresentation of
Qualifications") lives only in the ProEthica database (``ai_ethical_dm``),
not in OntServe. The case-view header reads ``ontology.meta_data['display_name']``
and falls back to the ontology name when that key is absent, which is why the
header currently shows the opaque ``proethica-case-60`` identifier.

This one-time maintenance script reads each title from ``ai_ethical_dm`` and
writes it into the OntServe ontology's JSON metadata. It is idempotent and
re-runnable. It does not touch ontology content or versions.

Both databases are local PostgreSQL (development). The durable path is for
ProEthica's commit service to set ``display_name`` when it creates or updates a
case ontology; until then this backfill keeps the existing corpus correct.

Usage:
    python tools/backfill_case_display_names.py [--dry-run]
"""

import argparse
import os
import re
import sys

import psycopg2
from sqlalchemy.orm.attributes import flag_modified

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.app import app
from web.models import db, Ontology

CASE_NAME_RE = re.compile(r'^proethica-case-(\d+)$')

PROETHICA_DSN = os.environ.get(
    'PROETHICA_DB_DSN',
    'host=localhost dbname=ai_ethical_dm user=postgres password=PASS',
)


def load_titles():
    """Return {document_id: title} for every titled ProEthica document."""
    conn = psycopg2.connect(PROETHICA_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, title FROM documents WHERE title IS NOT NULL")
            return {row[0]: row[1].strip() for row in cur.fetchall() if row[1] and row[1].strip()}
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true',
                        help='Report changes without writing them')
    args = parser.parse_args()

    titles = load_titles()
    print(f"Loaded {len(titles)} document titles from ai_ethical_dm")

    updated = 0
    unmatched = []
    with app.app_context():
        case_ontologies = (
            db.session.query(Ontology)
            .filter(Ontology.name.like('proethica-case-%'))
            .all()
        )
        print(f"Found {len(case_ontologies)} case ontologies in OntServe")

        for ont in case_ontologies:
            m = CASE_NAME_RE.match(ont.name)
            if not m:
                continue
            doc_id = int(m.group(1))
            title = titles.get(doc_id)
            if not title:
                unmatched.append(ont.name)
                continue

            meta = dict(ont.meta_data or {})
            if meta.get('display_name') == title:
                continue

            meta['display_name'] = title
            ont.meta_data = meta
            flag_modified(ont, 'meta_data')
            updated += 1
            print(f"  {ont.name} -> {title}")

        if args.dry_run:
            db.session.rollback()
            print(f"[dry-run] would update {updated} ontologies")
        else:
            db.session.commit()
            print(f"Updated {updated} ontologies")

    if unmatched:
        print(f"No matching document title for {len(unmatched)}: "
              f"{', '.join(sorted(unmatched))}")


if __name__ == '__main__':
    main()
