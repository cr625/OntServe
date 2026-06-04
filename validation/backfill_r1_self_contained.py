"""R1 self-contained-TTL backfill (2026-06-04).

The 9 priority baseline case TTLs were committed before the commit-serializer
emitted subClassOf-core for shared classes, so their persisted graphs are not
self-contained (pellet_validate reconstructs the subclass chain in memory).

This backfill adds the missing `<MintedClass> rdfs:subClassOf core:<Category>`
declarations to each stored case TTL and writes a new current ontology_versions
row, so the persisted artifact matches what the validator checks. It reuses
pellet_validate._add_missing_subclass_declarations (conceptCategory-derived),
which is provably safe for THESE 9 cases: they are already Pellet-consistent
under that exact patch, so conceptCategory == the established chain for every
shared class (a disagreement would already have made them inconsistent).

Dry-run by default; --commit writes new versions. After committing, re-validate:
each case's pellet_validate should now patch 0 declarations (self-contained).
"""
import sys
import os
import hashlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import psycopg2
from rdflib import Graph
import pellet_validate as PV

CASES = [7, 8, 14, 15, 71, 85, 86, 120, 121]
DSN = dict(host='localhost', user='postgres', password='PASS', dbname='ontserve')


def main(commit):
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    for cid in CASES:
        name = f'proethica-case-{cid}'
        cur.execute(
            """SELECT v.id, v.ontology_id, v.version_number, v.content
               FROM ontology_versions v JOIN ontologies o ON o.id = v.ontology_id
               WHERE o.name = %s AND v.is_current = true""", (name,))
        row = cur.fetchone()
        if not row:
            print(f"{name}: NO current version"); continue
        vid, ont_id, vnum, content = row
        g = Graph()
        g.parse(data=content, format='turtle')
        before = len(g)
        n = PV._add_missing_subclass_declarations(g)
        if n == 0:
            print(f"{name} v{vnum}: already self-contained (0 added)")
            continue
        new_content = g.serialize(format='turtle')
        print(f"{name} v{vnum} -> v{vnum + 1}: +{n} subClassOf-core triples ({before} -> {len(g)} triples)")
        if commit:
            h = hashlib.sha256(new_content.encode()).hexdigest()
            cur.execute("UPDATE ontology_versions SET is_current = false WHERE id = %s", (vid,))
            cur.execute(
                """INSERT INTO ontology_versions
                   (ontology_id, version_number, version_tag, content, content_hash, is_current)
                   VALUES (%s, %s, %s, %s, %s, true)""",
                (ont_id, vnum + 1, 'r1-self-contained', new_content, h))
            conn.commit()
            print(f"  committed v{vnum + 1}")
    if not commit:
        print("\nDRY RUN -- re-run with --commit to write new versions.")
    cur.close(); conn.close()


if __name__ == '__main__':
    main('--commit' in sys.argv)
