#!/usr/bin/env python3
"""Provenance / origin audit for OntServe ontologies.

Every class should declare its ORIGIN (see bfo-correctness-redesign.md Part 4):
  - standard-mirrored:   dcterms:source + prov:wasDerivedFrom <the REAL external IRI>
  - literature-grounded: dcterms:source <DOI / dissertation / code citation>
  - case-extracted:      prov:wasGeneratedBy + firstDiscoveredInCase

A class with none of those is UNSOURCED. A class DEFINED under a host the project
does not own (a standards-body domain) is COUNTERFEIT -- e.g. minting
https://standards.buildingsmart.org/.../IfcSafetyEngineer for a term IFC does not
have. Counterfeits must be re-minted into our namespace with the source as a link
(the ifc-roles vocab is the correct pattern); never assert owl:Class under someone
else's authoritative namespace.

Exit status is non-zero if any counterfeit is found, so this can gate a deploy.

Usage:
    python validation/provenance_audit.py            # curated layer
    python validation/provenance_audit.py --all      # include proethica-case-*
"""
import os
import sys

import psycopg2
import rdflib
from rdflib import RDF, OWL, URIRef

# Any one of these predicates means the class declares an origin.
PROV_KEYS = ('source', 'derivedfrom', 'generatedby', 'primarysource',
             'exactmatch', 'closematch', 'broadmatch', 'discovered',
             'seealso', 'isdefinedby')

# Hosts the project owns or legitimately imports -- defining classes under these
# is fine. proethica.org (ours), ontextract.org (the sibling OntExtract project),
# and the real foundations (OBO/BFO, W3C PROV-O/OWL/SKOS, Dublin Core, the legacy
# semanticweb ns). Anything else is an unowned external host => counterfeit.
OWNED_OR_FOUNDATION = ('proethica.org', 'ontextract.org', 'purl.obolibrary.org',
                       'www.w3.org', 'purl.org', 'www.semanticweb.org')


def _db_url():
    return os.environ.get('ONTSERVE_DB_URL',
                          'postgresql://postgres:PASS@localhost:5432/ontserve')


def audit(include_cases=False):
    conn = psycopg2.connect(_db_url())
    cur = conn.cursor()
    q = ("SELECT o.name, ov.content FROM ontology_versions ov "
         "JOIN ontologies o ON ov.ontology_id = o.id WHERE ov.is_current")
    if not include_cases:
        q += " AND o.name NOT LIKE 'proethica-case-%%'"
    q += " ORDER BY o.name"
    cur.execute(q)
    summary, counterfeits, unsourced = [], [], []
    for name, content in cur.fetchall():
        if not content:
            continue
        g = rdflib.Graph()
        try:
            g.parse(data=content, format='turtle')
        except Exception as exc:  # malformed TTL must not abort the audit
            print(f"  (skip {name}: parse error {exc})", file=sys.stderr)
            continue
        classes = [s for s in set(g.subjects(RDF.type, OWL.Class))
                   if isinstance(s, URIRef)]
        if not classes:
            continue
        src = un = 0
        for c in classes:
            cs = str(c)
            if any(any(k in str(p).lower() for k in PROV_KEYS)
                   for p in g.predicates(c)):
                src += 1
            else:
                un += 1
                unsourced.append((name, cs))
            if not any(h in cs for h in OWNED_OR_FOUNDATION):
                counterfeits.append((name, cs))
        summary.append((name, len(classes), src, un))
    return summary, counterfeits, unsourced


def main():
    summary, counterfeits, unsourced = audit('--all' in sys.argv)
    print(f"{'ontology':40} {'cls':>4} {'src':>4} {'unsrc':>5}")
    for name, total, src, un in sorted(summary, key=lambda x: -x[3]):
        cf = '  <-COUNTERFEIT' if any(n == name for n, _ in counterfeits) else ''
        print(f"{name:40} {total:4} {src:4} {un:5}{cf}")
    print(f"\nCOUNTERFEIT (owl:Class defined under an unowned external host): "
          f"{len(counterfeits)}")
    for name, cs in counterfeits:
        print(f"  [{name}] {cs}")
    print(f"\nUNSOURCED classes (no origin declared): {len(unsourced)} "
          f"-- backfill per bfo-correctness-redesign.md Part 4")
    return 1 if counterfeits else 0


if __name__ == '__main__':
    sys.exit(main())
