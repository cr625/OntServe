#!/usr/bin/env python3
"""Build the NSPE Code of Ethics ontology for OntServe from ProEthica's
guideline_sections (guideline_id=1).

Hybrid model (BFO/DIE-aligned, Pellet-consistent), using the purpose-built
proeth-core CodeProvision extension:

  nspe:NSPECodeOfEthics  a proeth-core:Guideline                 (IAO document)
  nspe:<code>            a proeth-core:CodeProvision              (IAO ICE)
                         proeth-core:partOfGuideline nspe:NSPECodeOfEthics ;
                         dct:isPartOf <parent provision> ;
                         dct:identifier "<code>" ;
                         skos:definition "<verbatim text>" ;
                         proeth-core:establishes <concept> .
  <concept>             a proeth-core:{Principle|Obligation|Constraint}  (IAO DIE)

The CodeProvision (ICE, descriptive document artifact) / established-concept
(DIE, prescriptive directive) split mirrors dissertation chapter 3 section 3.6.4.

For provisions carrying section_metadata.establishes (canons + a few rules), the
established concepts are the shared-vocabulary individuals named there. Directive
provisions without that metadata (most Rules of Practice / Professional
Obligations) get a minted per-provision Obligation so every directive provision
establishes at least one concept. The Preamble is a CodeProvision with no
established concept (introductory, not directive).

Usage:
    python tools/build_nspe_ontology.py            # generate + Pellet-validate, write /tmp TTL
    python tools/build_nspe_ontology.py --commit    # also commit to the ontserve DB (only if consistent)
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, DCTERMS, XSD

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

NSPE = Namespace("http://proethica.org/ontology/nspe#")
CORE = Namespace("http://proethica.org/ontology/core#")
INTERMEDIATE_IRI = URIRef("http://proethica.org/ontology/intermediate")
NSPE_ONT_IRI = URIRef("http://proethica.org/ontology/nspe")

PROETHICA_DSN = "host=localhost dbname=ai_ethical_dm user=postgres password=PASS"
ONTSERVE_DSN = "host=localhost dbname=ontserve user=postgres password=PASS"

CATEGORY_TYPE = {  # provision category -> established-concept DIE type for minted concepts
    "fundamental_canons": CORE.Principle,
    "rules_of_practice": CORE.Obligation,
    "professional_obligations": CORE.Obligation,
}
TOP_LEVEL_LABEL = {
    "I": "Fundamental Canons",
    "II": "Rules of Practice",
    "III": "Professional Obligations",
}
META_TYPE = {  # section_metadata establishes 'type' -> proeth-core class
    "principle": CORE.Principle,
    "obligation": CORE.Obligation,
    "constraint": CORE.Constraint,
}


def _frag(code: str) -> str:
    return code.replace(".", "_")


def _ancestors(code: str):
    """Dotted-code ancestry: 'II.1.a' -> ['II','II.1','II.1.a']; 'Preamble' -> ['Preamble']."""
    parts = code.split(".")
    return [".".join(parts[: i + 1]) for i in range(len(parts))]


def fetch_sections():
    conn = psycopg2.connect(PROETHICA_DSN)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT section_code, section_title, section_text, section_category,
                   parent_section_code, section_order, section_metadata
            FROM guideline_sections
            WHERE guideline_id = 1
            ORDER BY section_order
            """
        )
        return cur.fetchall()
    finally:
        conn.close()


def build_graph(rows):
    g = Graph()
    g.bind("nspe", NSPE)
    g.bind("proeth-core", CORE)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)
    g.bind("skos", SKOS)
    g.bind("dct", DCTERMS)

    # Ontology header
    g.add((NSPE_ONT_IRI, RDF.type, OWL.Ontology))
    g.add((NSPE_ONT_IRI, RDFS.label, Literal("NSPE Code of Ethics Ontology", lang="en")))
    g.add((NSPE_ONT_IRI, DCTERMS.title, Literal("National Society of Professional Engineers Code of Ethics", lang="en")))
    g.add((NSPE_ONT_IRI, DCTERMS.description, Literal(
        "Ontology representation of the NSPE Code of Ethics (rev. July 2019, Pub. #1102). "
        "Provisions are CodeProvision information content entities that establish the "
        "Principles, Obligations, and Constraints (directive information entities) derived "
        "from them, following the proeth-core CodeProvision extension and the BFO/IAO "
        "alignment in dissertation chapter 3.6.4.", lang="en")))
    g.add((NSPE_ONT_IRI, DCTERMS.created, Literal("2026-05-26", datatype=XSD.date)))
    g.add((NSPE_ONT_IRI, DCTERMS.source, URIRef("https://www.nspe.org/resources/ethics/code-ethics")))
    g.add((NSPE_ONT_IRI, OWL.imports, INTERMEDIATE_IRI))

    # The code document (Guideline container)
    code_node = NSPE.NSPECodeOfEthics
    g.add((code_node, RDF.type, OWL.NamedIndividual))
    g.add((code_node, RDF.type, CORE.Guideline))
    g.add((code_node, RDFS.label, Literal("NSPE Code of Ethics", lang="en")))

    rows_by_code = {r["section_code"]: r for r in rows}

    # Collect every code segment we must materialize (leaf rows + structural ancestors)
    all_codes = set()
    for code in rows_by_code:
        all_codes.update(_ancestors(code))

    declared_concepts = {}   # uri -> rdflib class (dedupe + conflict check)
    stats = {"provisions": 0, "grouping": 0, "minted_obl": 0, "meta_links": 0, "concepts": 0}

    def declare_concept(uri, cls, label):
        ref = URIRef(uri)
        if ref in declared_concepts:
            if declared_concepts[ref] != cls:
                raise SystemExit(
                    f"CONFLICT: concept {uri} typed as both "
                    f"{declared_concepts[ref]} and {cls}"
                )
            return ref
        declared_concepts[ref] = cls
        g.add((ref, RDF.type, OWL.NamedIndividual))
        g.add((ref, RDF.type, cls))
        if label:
            g.add((ref, RDFS.label, Literal(label, lang="en")))
        stats["concepts"] += 1
        return ref

    for code in sorted(all_codes):
        node = NSPE[_frag(code)]
        is_leaf = code in rows_by_code
        anc = _ancestors(code)

        g.add((node, RDF.type, OWL.NamedIndividual))
        g.add((node, RDF.type, CORE.CodeProvision))
        g.add((node, CORE.partOfGuideline, code_node))

        # Hierarchy: nest under immediate dotted ancestor, else under the document
        if len(anc) >= 2:
            g.add((node, DCTERMS.isPartOf, NSPE[_frag(anc[-2])]))
        else:
            g.add((node, DCTERMS.isPartOf, code_node))

        if is_leaf:
            r = rows_by_code[code]
            stats["provisions"] += 1
            g.add((node, RDFS.label, Literal(r["section_title"], lang="en")))
            g.add((node, DCTERMS.identifier, Literal(code)))
            if r["section_text"]:
                g.add((node, SKOS.definition, Literal(r["section_text"], lang="en")))

            category = r["section_category"]
            meta = r["section_metadata"] or {}
            establishes = meta.get("establishes") if isinstance(meta, dict) else None

            if establishes:
                for c in establishes:
                    cls = META_TYPE.get(c.get("type"))
                    if cls is None:
                        raise SystemExit(f"Unknown establishes type {c.get('type')!r} on {code}")
                    ref = declare_concept(c["uri"], cls, c.get("label"))
                    g.add((node, CORE.establishes, ref))
                    stats["meta_links"] += 1
            elif category in ("rules_of_practice", "professional_obligations"):
                # Mint a per-provision Obligation DIE for directive provisions
                obl = NSPE[f"{_frag(code)}_Obligation"]
                g.add((obl, RDF.type, OWL.NamedIndividual))
                g.add((obl, RDF.type, CORE.Obligation))
                g.add((obl, RDFS.label, Literal(f"Obligation established by NSPE {code}", lang="en")))
                g.add((obl, RDFS.comment, Literal(
                    f"Directive content established by NSPE Code provision {code}.", lang="en")))
                g.add((node, CORE.establishes, obl))
                stats["minted_obl"] += 1
            elif category == "fundamental_canons":
                # Canons all carry establishes metadata; mint a Principle if any lacks it
                prin = NSPE[f"{_frag(code)}_Principle"]
                g.add((prin, RDF.type, OWL.NamedIndividual))
                g.add((prin, RDF.type, CORE.Principle))
                g.add((prin, RDFS.label, Literal(f"Principle established by NSPE {code}", lang="en")))
                g.add((node, CORE.establishes, prin))
                stats["minted_obl"] += 1
            # preamble: no established concept
        else:
            stats["grouping"] += 1
            label = TOP_LEVEL_LABEL.get(code, f"NSPE Code Section {code}")
            g.add((node, RDFS.label, Literal(label, lang="en")))

    return g, stats


def validate(ttl_text: str):
    from validation.pellet_validate import validate_case_from_content
    return validate_case_from_content("nspe-code-of-ethics", ttl_text)


def commit_to_ontserve(ttl_text: str):
    content_hash = hashlib.sha256(ttl_text.encode("utf-8")).hexdigest()
    conn = psycopg2.connect(ONTSERVE_DSN)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM ontologies WHERE base_uri = %s OR name = %s",
                    ("http://proethica.org/ontology/nspe#", "NSPE Code of Ethics"))
        existing = cur.fetchone()
        if existing:
            ont_id = existing[0]
            cur.execute("SELECT COALESCE(MAX(version_number), 0) FROM ontology_versions WHERE ontology_id=%s", (ont_id,))
            next_ver = cur.fetchone()[0] + 1
            cur.execute("UPDATE ontology_versions SET is_current=false WHERE ontology_id=%s", (ont_id,))
            cur.execute(
                """
                INSERT INTO ontology_versions (ontology_id, version_number, version_tag, content,
                                               content_hash, change_summary, created_by,
                                               is_current, is_draft, workflow_status)
                VALUES (%s, %s, %s, %s, %s, %s, 'build_nspe_ontology.py', true, false, 'published')
                """,
                (ont_id, next_ver, f"establishes-refresh-v{next_ver}", ttl_text, content_hash,
                 "Refreshed after targeted establishes extraction over all 56 provisions: every "
                 "CodeProvision now establishes shared Principle/Obligation/Constraint concepts; "
                 "placeholder per-provision obligations removed."),
            )
            conn.commit()
            print(f"Updated existing NSPE ontology id={ont_id} -> version {next_ver} (current).")
            return ont_id
        cur.execute(
            """
            INSERT INTO ontologies (name, base_uri, description, is_base, is_editable,
                                    ontology_type, source_system)
            VALUES (%s, %s, %s, false, true, 'base', 'external')
            RETURNING id
            """,
            ("NSPE Code of Ethics", "http://proethica.org/ontology/nspe#",
             "Ontology representation of the NSPE Code of Ethics (rev. July 2019). "
             "Provisions as CodeProvision ICEs establishing Principle/Obligation/Constraint DIEs."),
        )
        ont_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO ontology_versions (ontology_id, version_number, version_tag, content,
                                           content_hash, change_summary, created_by,
                                           is_current, is_draft, workflow_status)
            VALUES (%s, 1, 'initial-build', %s, %s, %s, 'build_nspe_ontology.py',
                    true, false, 'published')
            """,
            (ont_id, ttl_text, content_hash,
             "Initial NSPE Code of Ethics ontology generated from ai_ethical_dm.guideline_sections "
             "(guideline_id=1): 56 CodeProvisions + Guideline + established Principle/Obligation/Constraint DIEs."),
        )
        conn.commit()
        return ont_id
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="commit to ontserve DB if consistent")
    ap.add_argument("--out", default="/tmp/nspe_code_of_ethics.ttl")
    args = ap.parse_args()

    rows = fetch_sections()
    print(f"Fetched {len(rows)} guideline sections")
    g, stats = build_graph(rows)
    ttl = g.serialize(format="turtle")
    Path(args.out).write_text(ttl, encoding="utf-8")
    print(f"Stats: {stats}")
    print(f"Triples: {len(g)}  ->  {args.out}")

    print("Running Pellet validation (merged with core + intermediate)...")
    res = validate(ttl)
    print(f"  consistent={res.consistent}  triples_merged={res.triples_merged}  "
          f"runtime={res.runtime_seconds:.1f}s  error={res.error}")
    if not res.consistent:
        print("INCONSISTENT or errored -- not committing.")
        sys.exit(1)

    if args.commit:
        ont_id = commit_to_ontserve(ttl)
        print(f"COMMITTED to ontserve as ontology id={ont_id} (version 1, published).")
    else:
        print("Validation passed. Re-run with --commit to write to OntServe.")


if __name__ == "__main__":
    main()
