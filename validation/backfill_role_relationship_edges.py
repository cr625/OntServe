#!/usr/bin/env python3
"""Backfill: rewrite AGENT-to-AGENT relational edges in committed case ontologies to
ROLE-to-ROLE, so the defined relational archetypes (ProviderClientRole/ProfessionalPeerRole/
EmployerRelationshipRole) classify the role individuals under the reasoner.

Before this, the role-relationship extraction emitted edges between the bearer Agents
(Agent_Engineer_A hasClient Agent_Client_W). A defined class like
``ProviderClientRole equivalentClass Role and (hasClient some Role)`` classifies a ROLE, so
the edge must hold between the role facets. New commits already emit role-to-role (the
ontserve_commit_service rewire); this backfills the cases committed before that.

Heuristic for which facet a relationship belongs to (the agent-to-agent edge does not record
it): for each endpoint Agent, take its role facet. If the Agent bears exactly one facet, use
it. Otherwise pick the facet whose ``roleCategory`` matches the relation's Kong category;
when 0 or 2+ match, FLAG (and skip) for manual review / gold-standard re-extraction.

PROVISIONAL: the authoritative role-to-role edges come from re-extraction once the emission
rewire is live; this backfill makes the existing corpus classify in the meantime.

Updates BOTH the DB current version content AND the on-disk case TTL (keeps disk == DB; the
case-103 lesson). Re-validate with pellet_corpus_check.py afterward.

Usage:
    ONTSERVE_DB_URL=postgresql://postgres:PASS@localhost:5432/ontserve \
        python validation/backfill_role_relationship_edges.py            # all cases
        python validation/backfill_role_relationship_edges.py --dry-run  # report only
        python validation/backfill_role_relationship_edges.py proethica-case-7
"""
import os
import sys
import argparse
from pathlib import Path

import rdflib
from rdflib import RDF
import psycopg2

CORE = rdflib.Namespace("http://proethica.org/ontology/core#")
PROETH = rdflib.Namespace("http://proethica.org/ontology/intermediate#")

# The relational properties and the Kong roleCategory each implies on its SUBJECT facet.
# None = generic (no category constraint; rely on single-facet resolution).
REL_PROP_CATEGORY = {
    "hasClient": "provider_client",
    "professionalPeerOf": "professional_peer",
    "employedBy": "employer_relationship",
    "reviewsWorkOf": "professional_peer",
    "workReviewedBy": "professional_peer",
    "relatedTo": None,
}

ONTO_DIR = Path(__file__).resolve().parents[1] / "ontologies"


def _facets_of(g, agent):
    """[(facet_uri, roleCategory_or_None)] for an Agent's hasRole facets."""
    out = []
    for f in g.objects(agent, CORE.hasRole):
        rc = next(g.objects(f, PROETH.roleCategory), None) or next(g.objects(f, CORE.roleCategory), None)
        out.append((f, str(rc) if rc is not None else None))
    return out


def _pick_facet(facets, category):
    """Choose the facet for an endpoint Agent. Returns (facet_uri, reason) or (None, why_flagged)."""
    if not facets:
        return None, "agent has no role facet"
    if len(facets) == 1:
        return facets[0][0], "sole facet"
    if category is not None:
        matched = [f for f, rc in facets if rc == category]
        if len(matched) == 1:
            return matched[0], f"category={category}"
        if len(matched) > 1:
            return None, f"AMBIGUOUS: {len(matched)} facets match category={category}"
        return None, f"NO facet matches category={category} among {len(facets)}"
    return None, f"generic relation, {len(facets)} facets, no category to disambiguate"


def _rewrite_graph(g):
    """Rewrite agent-to-agent relational edges to role-to-role. Returns (n_rewritten, flags)."""
    agents = set(g.subjects(CORE.hasRole, None))
    facet_cache = {a: _facets_of(g, a) for a in agents}
    rewritten = 0
    flags = []
    for prop, category in REL_PROP_CATEGORY.items():
        for s, o in list(g.subject_objects(CORE[prop])):
            # Only touch agent-to-agent edges (skip any already role-to-role).
            if s not in agents or o not in agents:
                continue
            s_facet, s_why = _pick_facet(facet_cache.get(s, []), category)
            o_facet, o_why = _pick_facet(facet_cache.get(o, []), category)
            if s_facet is None or o_facet is None:
                flags.append(f"{prop}: {s.split('#')[-1]}->{o.split('#')[-1]} "
                             f"[subj: {s_why}] [obj: {o_why}]")
                continue
            g.remove((s, CORE[prop], o))
            g.add((s_facet, CORE[prop], o_facet))
            rewritten += 1
    return rewritten, flags


def _case_rows(conn, only):
    cur = conn.cursor()
    if only:
        cur.execute("""
            SELECT o.id, o.name, v.id, v.content
            FROM ontologies o JOIN ontology_versions v ON v.ontology_id=o.id
            WHERE o.name=%s AND v.is_current=true""", (only,))
    else:
        cur.execute("""
            SELECT o.id, o.name, v.id, v.content
            FROM ontologies o JOIN ontology_versions v ON v.ontology_id=o.id
            WHERE o.name LIKE 'proethica-case-%%' AND v.is_current=true
            ORDER BY o.name""")
    return cur.fetchall()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ontology", nargs="?", help="single case ontology name (default: all proethica-case-*)")
    ap.add_argument("--dry-run", action="store_true", help="report counts/flags; write nothing")
    args = ap.parse_args()

    db_url = os.environ.get("ONTSERVE_DB_URL")
    if not db_url:
        print("ONTSERVE_DB_URL must be set", file=sys.stderr)
        return 2
    conn = psycopg2.connect(db_url)

    total_rw, total_flags, cases = 0, 0, 0
    for ont_id, name, ver_id, content in _case_rows(conn, args.ontology):
        cases += 1
        g = rdflib.Graph()
        g.parse(data=content, format="turtle")
        n, flags = _rewrite_graph(g)
        total_rw += n
        total_flags += len(flags)
        status = "DRY" if args.dry_run else "OK"
        print(f"[{status}] {name}: rewrote {n} edge(s), flagged {len(flags)}")
        for fl in flags:
            print(f"        FLAG {fl}")
        if not args.dry_run and n:
            new_ttl = g.serialize(format="turtle")
            cur = conn.cursor()
            cur.execute("UPDATE ontology_versions SET content=%s WHERE id=%s", (new_ttl, ver_id))
            conn.commit()
            disk = ONTO_DIR / f"{name}.ttl"
            if disk.exists():
                disk.write_text(new_ttl)  # keep disk == DB (case-103 lesson)
    conn.close()
    print(f"\n{cases} case(s); {total_rw} edge(s) rewritten; {total_flags} flagged for review")
    return 0


if __name__ == "__main__":
    sys.exit(main())
