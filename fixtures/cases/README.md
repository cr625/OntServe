# Case Ontology Fixtures

This directory holds minimal renderings of NSPE Board of Ethical Review
cases used in Figure 1 of the KI2026 paper. They are committed to the
repository so that reviewers can inspect the worked example directly
without a database.

Note on naming: the `case_0NN` numbers are ProEthica internal document
indices, not NSPE case numbers. Internal case 86 is NSPE BER Case 04-8
(2004); internal case 72 is NSPE BER Case 76-4 (1976).

## Files

| File | Purpose |
|---|---|
| `case_086.ttl` | Current Figure 1 worked example: NSPE BER Case 04-8 (2004). Three typed individuals plus the three defeasibility edges the paper draws. Uses abbreviated local names from the figure caption. A confidentiality obligation (NSPE II.1.c) competes with the paramount public-welfare obligation (NSPE I.1, reported via II.1.f); under the client's unpermitted wetland-fill violation the confidentiality obligation is defeasible and the public-welfare obligation prevails. |
| `case_072.ttl` | Superseded earlier worked example: NSPE BER Case 76-4 (1976). Retained for provenance. It states the same faithful-agent-versus-public-welfare conflict but under the retired pre-1979 "Section 1 / Section 2(a)" numbering. NSPE marks pre-1980 opinions as historical only, so the camera-ready figure was moved to the current-Code Case 04-8 above. |
| `malformed_disjoint.ttl` | Deliberately incorrect fixture used by `tests/integration/test_disjointness_enforcement.py` to verify that the `owl:AllDisjointClasses` assertion in `proethica-core.ttl` produces an inconsistency when a single individual is typed as both a `State` and an `Action`. |

## Why only the worked-example cases are shipped here

The paper's evaluation (§5) uses 119 NSPE BER case ontologies. Those
live in the OntServe production database and are browsable on the
live site:

- All case ontologies: https://ontserve.ontorealm.net/ (filter: Case)
- Case 04-8 (internal 86) on the live site: https://ontserve.ontorealm.net/ontology/proethica-case-86
- Raw TTL: https://ontserve.ontorealm.net/ontology/proethica-case-86/content

Shipping all 119 as files in the repository would create a large
derivative dataset without adding reproducibility value. The live site
serves each case ontology as TTL on demand, and the extraction
pipeline that produces them lives in the companion ProEthica project.

## How Figure 1 relates to the live case ontology

The paper's Figure 1 caption states "Local names abbreviated.
Provenance triples omitted." The live Case 04-8 ontology uses longer
descriptive local names produced by the LLM extraction client (for
example `Engineer_A_Public_Welfare_Paramount_Wetland_Fill_Environmental`
rather than `Obl_PublicWelfare`). As of the 2026-05-23 corpus pass the
live ontologies materialize the three defeasibility edges
(`competesWith`, `prevailsOver`, `defeasibleUnder`) and the R-P-O
dependency edges directly, and the corpus is 119/119 Pellet-consistent.

`case_086.ttl` in this directory is the canonical place to see the full
Figure 1 pattern, typed individuals plus defeasibility edges, in one
abbreviated OWL file.

## Running the Figure 1 test

The Figure 1 integration test loads the fixture with the core and
intermediate ontologies, runs Pellet via owlready2, asserts
consistency, and checks that the three defeasibility edges are
queryable by SPARQL. The existing test keyed to the older fixture
(`tests/integration/test_case_72_figure1.py`) should be repointed to
`case_086.ttl` when the camera-ready figure swap lands.
