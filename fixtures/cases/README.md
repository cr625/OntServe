# Case Ontology Fixtures

This directory holds a minimal rendering of NSPE Board of Ethical Review
Case 72 used in Figure 1 of the KI2026 paper. It is committed to the
repository so that reviewers can inspect the worked example directly
without a database.

## Files

| File | Purpose |
|---|---|
| `case_072.ttl` | Verbatim OWL rendering of Figure 1. Three typed individuals plus the three defeasibility edges the paper draws. Uses abbreviated local names from the figure caption. |
| `malformed_disjoint.ttl` | Deliberately incorrect fixture used by `tests/integration/test_disjointness_enforcement.py` to verify that the `owl:AllDisjointClasses` assertion in `proethica-core.ttl` produces an inconsistency when a single individual is typed as both a `State` and an `Action`. |

## Why only Case 72 is shipped here

The paper's evaluation (§5) uses 119 NSPE BER case ontologies. Those
live in the OntServe production database and are browsable on the
live site:

- All case ontologies: https://ontserve.ontorealm.net/ (filter: Case)
- Case 72 on the live site: https://ontserve.ontorealm.net/ontology/proethica-case-72
- Raw TTL: https://ontserve.ontorealm.net/ontology/proethica-case-72/content

Shipping all 119 as files in the repository would create a large
derivative dataset without adding reproducibility value. The live site
serves each case ontology as TTL on demand, and the extraction
pipeline that produces them lives in the companion ProEthica project.

## How Figure 1 relates to the live Case 72

The paper's Figure 1 caption states "Local names abbreviated.
Provenance triples omitted." The live Case 72 ontology (a) uses longer
descriptive local names produced by the LLM extraction client, and
(b) currently materializes the typed individuals and their source text
but not yet the three defeasibility edges (`competesWith`,
`prevailsOver`, `defeasibleUnder`). The defeasibility edges live in
the core ontology as first-class object properties ready to be written
by a post-extraction step or by an external reasoning engine.

`case_072.ttl` in this directory is therefore the canonical place to
see the full Figure 1 pattern -- typed individuals plus defeasibility
edges -- in one OWL file.

## Running the Figure 1 test

```bash
pytest tests/integration/test_case_72_figure1.py -v
```

This loads the fixture with the core and intermediate ontologies,
runs Pellet via owlready2, asserts consistency, and checks that the
three defeasibility edges are queryable by SPARQL.
