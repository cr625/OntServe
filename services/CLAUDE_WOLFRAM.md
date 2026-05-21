# CLAUDE_WOLFRAM.md - Wolfram Integration for Ontology-Supported Language Processing

Development reference for `services/wolfram_service.py` and the broader role of
Wolfram technologies in an ontology-supported language pipeline within OntServe.
Scope is the linguistic and lexical-grounding layer. The description-logic
reasoning layer is documented separately and is explicitly out of scope for the
Wolfram component (see "Architectural Boundary").

---

## Current Implementation

`WolframService` (in `services/wolfram_service.py`) is a thin client for the
Wolfram AgentOne chat-completions API at
`https://services.wolfram.com/api/agent-one/v1/chat/completions`. AgentOne
combines an LLM with Wolfram Language computation and curated knowledge, exposed
through an OpenAI-compatible message format.

**Consumers:**

- `servers/mcp_tool_handlers.py` -- `handle_wolfram_lookup` wraps the service as
  the `wolfram_lookup` MCP tool. It accepts a `query` and optional `context`,
  formats them as `"In the context of {context}: {query}"`, and runs the
  synchronous request on a worker thread via `asyncio.to_thread`.
- `servers/mcp_server.py` -- constructs the service at startup and passes it to
  the handler container; degrades to `None` when no API key is present.
- `web/wolfram_routes.py`, `web/app.py` -- web-interface access to the same
  service instance.

**Authentication:** `WOLFRAM_API_KEY` environment variable. The key is sent as
the raw `Authorization` header value (not a bearer token).

**Current capability:** free-text question answering for ontology grounding. A
caller asks for a definition or classification of a term and receives prose. The
response is not parsed into structured fields; it is treated as a natural-language
explanation.

---

## Architectural Boundary

Wolfram occupies the **linguistic and lexical-grounding layer**. It does not
perform description-logic reasoning, and the codebase should not present it as
doing so.

| Layer | Responsibility | Technology |
|-------|----------------|------------|
| Linguistic front-end | Tokenisation, part-of-speech, lemmatisation, word-sense disambiguation, lexical relations, entity grounding | Wolfram (AgentOne and Wolfram Engine/Cloud functions) |
| Ontology grounding | Mapping disambiguated terms to OntServe entities and IRIs | OntServe MCP tools, vector and label matching |
| Logical layer | Consistency checking, automatic classification, inference of implicit relations, defeasible-obligation evaluation | OWL-DL reasoner (Pellet, HermiT, or ELK) over the RDF/OWL |

The separation matters for the DAAD project (`docs-internal/daad_research_proposal_v4.md`).
The proposal places consistency checking, classification, and the structural
encoding of defeasible obligations inside an OWL-DL reasoner. OWL-DL is monotonic;
defeasibility is encoded structurally through reified obligations and explicit
override relations, with conflict resolution implemented as a priority policy over
those relations rather than inside the reasoner. Wolfram contributes nothing to
that logical layer. It contributes to the stages that produce clean, sense-resolved,
predicate-argument structure for the reasoner to operate on.

---

## Wolfram Capabilities Relevant to the Pipeline

Two access paths exist, and they differ in what they return.

**AgentOne (currently integrated).** Returns prose. Suited to open-ended grounding
questions, disambiguation explanations, and computation-backed answers. It is not
deterministic and its output schema is unconstrained, so downstream parsing is
brittle. Appropriate for human-facing lookups and for LLM-to-LLM grounding where a
second model consumes the prose.

**Wolfram Engine / Wolfram Cloud functions (extension point, not yet integrated).**
Return structured values from named linguistic primitives. These are deterministic
and directly parseable:

- `WordData` -- definitions, parts of speech, and lexical relations including
  hypernyms, hyponyms, synonyms, and meronyms. A hypernym chain is a ready-made
  taxonomy fragment that can be compared against the BFO-grounded class hierarchy.
- `SemanticInterpretation` and `Interpreter` -- word-sense disambiguation and
  entity resolution. `SemanticInterpretation["Apple"]` distinguishes the company,
  the fruit, and the stock. This is the resolution step that precedes ontology
  grounding.
- `TextStructure` and `TextCases` -- sentence and grammatical structure, named-entity
  spans, and typed extraction over free text.
- `DictionaryLookup`, `WordDefinition` -- lexical confirmation and gloss retrieval.

The Python access path for the deterministic functions is the `wolframclient`
package (`WolframLanguageSession`) against a local Wolfram Engine, or the Wolfram
Cloud API. Adding this path is the principal proposed extension to
`WolframService` (see "Proposed Extensions").

---

## Ontology-Supported Language Pipeline

The pipeline stages, and where Wolfram fits each one:

1. **Segmentation and normalisation.** Tokenise, lemmatise, tag parts of speech.
   `TextStructure` provides this; an LLM extractor can also, but the Wolfram path
   is deterministic and cheaper to validate.
2. **Word-sense disambiguation.** Resolve each candidate term to a sense before
   grounding. `SemanticInterpretation` produces the sense; this is where the
   semantic-change concern from prior work (Rauch, Choi, & Kelly, 2024) is
   addressed operationally, by pinning a term to a versioned sense rather than a
   surface string.
3. **Lexical-relation enrichment.** Retrieve hypernym and synonym sets via
   `WordData`. The hypernym chain is a candidate `rdfs:subClassOf` path; it is
   evidence for, not a substitute for, placement in the BFO-grounded hierarchy.
4. **Frame-semantic parse.** Extract predicate-argument structure (see "Frame
   Semantics Bridge"). This is the stage that produces the relational triples the
   D-tuple consumes.
5. **Ontology grounding.** Map the disambiguated, enriched terms to OntServe
   entities through the MCP tools (`get_entity_by_label`, `get_entities_by_uris`,
   `sparql_query`). The Wolfram hypernym evidence informs the match but the
   authoritative placement is OntServe's.
6. **RDF assertion.** Emit triples into the case ontology.
7. **DL reasoning.** Hand off to the OWL-DL reasoner for consistency,
   classification, inferred relations, and defeasible-override evaluation. Wolfram
   has no role here.

Stages one through four are the Wolfram contribution. They convert narrative text
into the sense-resolved, structured input the grounding and reasoning layers
require.

---

## Frame Semantics Bridge

The host group at HHU Düsseldorf (Kallmeyer and colleagues) develops Lexicalized
Tree Adjoining Grammar combined with decompositional frame semantics, where
syntactic substitution and adjunction trigger unification of semantic frames
defined as base-labelled feature structures (Kallmeyer & Osswald, JLM). Frames
are the natural intermediate representation between a syntactic parse and the
ProEthica D-tuple.

A frame's core elements correspond to D-tuple components and their relations:

- A frame's Agent or Experiencer role maps to an entity bearing a `Role` (R).
- A frame evoked by a deontic predicate ("shall report", "must disclose") maps to
  an `Obligation` (O) with the bearer as its subject.
- The frame's eventuality and its participants map to `Action` (A) or `Event` (E)
  individuals with typed object properties between them.

The practical consequence: a frame-semantic parse produces exactly the
predicate-argument structure that becomes RDF object-property assertions. This is
the structural fidelity the evaluation measures. Wolfram's `TextStructure` is a
pragmatic source of shallow predicate-argument structure; a frame-semantic parser
from the LTAG line is the principled source the research stay would integrate.

---

## Description Logic and Reasoner Integration

Documented here only to fix the boundary. Detail belongs in the reasoner
component, not the Wolfram component.

The RDF/OWL structure permits an OWL-DL reasoner to perform:

- **Consistency checking** as the ontology is extended with new board opinions or
  new professional domains. Inconsistencies introduced during extension are
  currently undetected.
- **Automatic classification** of extracted individuals under the BFO-grounded
  hierarchy, materialising `rdf:type` and `rdfs:subClassOf` inferences.
- **Inference of implicit relations** that extend retrieval beyond asserted edges.
- **Defeasible-obligation evaluation** over the reified obligation and override
  structure already present in the corpus. The three object properties
  (`competesWith`, `prevailsOver`, `defeasibleUnder`) and 4839 edges across 118
  cases (see `OntServe/CLAUDE.md`) are the substrate. A priority policy over
  `prevailsOver` and `defeasibleUnder` resolves conflicts; the monotonic reasoner
  evaluates the structure but does not retract.

Candidate reasoners: ELK for fast classification of the EL fragment, HermiT or
Pellet for the full DL fragment including the property characteristics the
defeasibility edges rely on. SHACL is a complementary option for shape validation
of the reified obligation structure where full DL reasoning is unnecessary.

---

## Proposed Extensions to WolframService

In priority order. None of these change the AgentOne path, which remains the
free-text grounding tool.

1. **Add a deterministic linguistic backend.** Introduce a second method group on
   `WolframService` (or a sibling class) that calls named Wolfram Language
   functions through `wolframclient` against a local Wolfram Engine or the Wolfram
   Cloud API. Target functions: `WordData`, `SemanticInterpretation`,
   `TextStructure`. Return structured dicts, not prose. This is the prerequisite
   for stages one through four of the pipeline.
2. **Structured response contract.** Define typed return shapes for lexical
   lookups (sense identifier, gloss, part of speech, hypernym chain) so downstream
   grounding does not parse prose. AgentOne lookups keep their current prose
   contract; the new backend gets its own.
3. **Word-sense disambiguation endpoint.** Expose a `disambiguate(term, context)`
   operation that returns ranked senses with identifiers, feeding stage two.
4. **Hypernym-to-subclass evidence.** Expose a `lexical_parents(term)` operation
   returning the hypernym chain as candidate superclass IRIs, surfaced to the
   grounding layer as evidence with a confidence signal, never as an authoritative
   assertion.
5. **Caching.** Deterministic lookups are cacheable by `(function, term, sense)`.
   The current AgentOne path is not safely cacheable. Add caching only to the
   deterministic backend.

The current `query` method, error handling, and status reporting are the model for
the new methods: explicit per-status-code handling, structured failure dicts (no
exceptions across the boundary), and elapsed-time logging.

---

## Configuration and Environment

- `WOLFRAM_API_KEY` -- required for the AgentOne path. Sent as the raw
  `Authorization` header value. When absent, the service degrades to a configured
  failure state rather than raising, and the MCP server passes `wolfram_service=None`.
- A deterministic backend would add a separate credential or a local Wolfram
  Engine path. Keep it independent of `WOLFRAM_API_KEY` so the two paths fail
  independently.
- Per the workspace instruction: do not suppress errors or add fallbacks in
  development. A missing key or unreachable engine should surface as a clear
  configured-failure result, matching the existing `is_configured` and structured
  error pattern.

---

## Testing

- `tests/unit/test_mcp_handlers.py` covers `handle_wolfram_lookup` for the
  unconfigured, empty-query, and success paths with a stubbed service.
- A deterministic backend should be tested against recorded `wolframclient`
  responses so the suite does not require a live Wolfram Engine. Keep the AgentOne
  path tests separate from the deterministic-backend tests; they have different
  contracts and different failure modes.

---

## Open Design Questions

- Whether the deterministic backend runs against a self-hosted Wolfram Engine
  (deterministic, offline, licence cost) or the Wolfram Cloud API (network
  dependency, per-call cost). The pipeline's batch nature over the 119-case corpus
  argues for the local engine.
- Where word-sense identifiers are persisted so a term's sense is versioned with
  the ontology, addressing terminological drift rather than re-disambiguating on
  each run.
- Whether shallow `TextStructure` predicate-argument output is sufficient for the
  evaluation, or whether the frame-semantic parser from the LTAG line is required
  for the structural-fidelity claim. This is a question for the research stay.

---

## References

- Wolfram NLP documentation: https://reference.wolfram.com/language/guide/NaturalLanguageProcessing.html
- Wolfram NLU System: https://www.wolfram.com/natural-language-understanding/
- AgentOne API: https://www.wolfram.com/apis/documentation/cag/wolfram-agent-one-api/
- Kallmeyer & Osswald, Syntax-driven semantic frame composition in LTAG (JLM):
  https://user.phil-fak.uni-duesseldorf.de/~kallmeyer/papers/KallmeyerOsswald-JLM.pdf
- DAAD research proposal: `docs-internal/daad_research_proposal_v4.md`
- Defeasibility edge backfill and corpus totals: `OntServe/CLAUDE.md`
</content>
</invoke>
