# OntServe

Central ontology management and serving system. Provides ontology storage, entity extraction, a SPARQL endpoint, and an MCP server for tool-based integration with ProEthica and other ontology consumers.

**Live site:** https://ontserve.ontorealm.net

## Paper

This repository accompanies:

> Rauch, C. B. *An Ontology-Grounded Representation for Defeasible
> Professional Ethics Analysis.* Submitted to KI2026. See
> [docs/KI2026.pdf](docs/KI2026.pdf).

OntServe instantiates the three-layer ontology architecture described in
§3–§4 of the paper: a core ontology of nine disjoint component classes
aligned to BFO and IAO, a domain layer of profession-specific subclasses,
and an individual layer of one OWL ontology per case. The repository
hosts the **code** for the server, reasoner, and MCP interface; the
**live site** above hosts the knowledge graph itself, including the 119
NSPE Board of Ethical Review case ontologies, their SPARQL endpoint, and
per-ontology browsing.

Reviewers looking for a specific claim in the paper will find the
implementing code in these files:

| Paper claim | Implementation |
|---|---|
| Nine component classes with ``owl:AllDisjointClasses`` | [`ontologies/proethica-core.ttl`](ontologies/proethica-core.ttl) |
| Defeasibility properties (``competesWith``, ``prevailsOver``, ``defeasibleUnder``) | [`ontologies/proethica-core.ttl`](ontologies/proethica-core.ttl) lines 240–270 |
| BFO 2020 / IAO alignments | [`ontologies/proethica-core.ttl`](ontologies/proethica-core.ttl), [`data/foundation/bfo-2.0.owl`](data/foundation/bfo-2.0.owl), [`data/foundation/iao-2020.owl`](data/foundation/iao-2020.owl) |
| Pellet reasoning per case, imports stripped, hierarchy diffed, inferred relationships persisted | [`editor/reasoning_service.py`](editor/reasoning_service.py) |
| SPARQL endpoint over the full graph | [`services/sparql_service.py`](services/sparql_service.py), [`servers/mcp_server.py`](servers/mcp_server.py) `/sparql` route |
| MCP interface for extraction clients | [`servers/mcp_server.py`](servers/mcp_server.py), [`servers/mcp_tool_handlers.py`](servers/mcp_tool_handlers.py) |
| Case 72 (Figure 1) worked example | [`fixtures/cases/case_072.ttl`](fixtures/cases/case_072.ttl) |
| Ontology sync (hash-based re-extraction of TTL files to DB) | [`services/ontology_sync_service.py`](services/ontology_sync_service.py) |
| Systemd deployment on the live server | [`deploy/systemd/`](deploy/systemd/) |

The LLM extraction client that produces the case ontologies is the
companion **ProEthica** project
([github.com/cr625/proethica](https://github.com/cr625/proethica)). It
consumes the MCP tools listed below to propose typed entities from case
narratives; OntServe validates the classifications against the type
structure in [`ontologies/proethica-core.ttl`](ontologies/proethica-core.ttl) and
[`ontologies/proethica-intermediate.ttl`](ontologies/proethica-intermediate.ttl).

## Prerequisites

- Python 3.11+ (3.12 recommended)
- PostgreSQL 14+ with pgvector extension
- Java JDK 11+ (optional, for OWL reasoners)

## Quick Start

```bash
# Create and activate virtual environment
python -m venv venv-ontserve
source venv-ontserve/bin/activate
pip install -r requirements.txt
pip install -e .

# Set up the database
createdb ontserve
psql -d ontserve -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Configure environment (edit values as needed)
cp config/development.env .env

# Start the MCP server (port 8082)
python servers/mcp_server.py

# Start the web interface (port 5003) in a separate terminal
python web/app.py
```

**Local URLs:**
- Web interface: http://localhost:5003
- MCP server: http://localhost:8082

## Project Structure

```
OntServe/
  servers/          MCP server (FastMCP 3.x) and tool handlers
  web/              Flask web interface, models, routes
  core/             Ontology manager, merger, entity patterns
  editor/           Ontology editing, reasoning, visualization (Flask blueprint)
  storage/          PostgreSQL and file storage backends
  services/         SPARQL service, ontology sync, Wolfram service
  importers/        Format-specific importers (BFO, PROV-O, OWL)
  config/           Environment configs and YAML display configs
  ontologies/       Core, intermediate, cases, provenance, and engineering-ethics TTL
  data/foundation/  BFO, IAO, Relations Ontology
  deploy/systemd/   Production systemd service units
  tests/            Unit, integration, and API tests
  tools/            Operational scripts (entity refresh, etc.)
  docs/             KI2026 paper PDF
```

## Configuration

Environment variables are loaded from `config/{environment}.env` and the root `.env` file. See [config/README.md](config/README.md) for the full variable reference.

Key variables:
- `ONTSERVE_DB_URL` -- PostgreSQL connection string
- `ONTSERVE_MCP_PORT` -- MCP server port (default: 8082)
- `ONTSERVE_WEB_PORT` -- Web server port (default: 5003)

## MCP Tools

The MCP server exposes tools for ontology integration. Schemas are
auto-generated from the type hints in
[`servers/mcp_server.py`](servers/mcp_server.py).

| Tool | Description |
|------|-------------|
| `get_entities_by_category` | Retrieve entities by type (Role, Principle, etc.) |
| `sparql_query` | Execute SPARQL against the loaded knowledge graph |
| `submit_candidate_concept` | Submit an extracted concept for review |
| `update_concept_status` | Approve/reject a candidate concept |
| `get_candidate_concepts` | List pending concepts |
| `get_domain_info` | Retrieve professional domain metadata |
| `store_extracted_entities` | Store entities extracted from a case section |
| `get_case_entities` | Retrieve stored entities for a case |
| `get_entity_by_uri` | Resolve a single entity IRI |
| `get_entities_by_uris` | Batch resolve up to 20 entity IRIs |
| `get_entity_by_label` | Look up an entity by label (disambiguation) |
| `wolfram_lookup` | Query Wolfram AgentOne for concept grounding (future work) |

## Testing

```bash
source venv-ontserve/bin/activate
python -m pytest tests/ -v
```

Tests are organized into `unit/`, `integration/`, and `api/` directories. See [tests/README.md](tests/README.md) for details on markers and fixtures.

## Reproducing paper claims

The live deployment is the primary artifact reviewers use to verify
§4 and §5 of the KI2026 paper. The repository accompanies it. Concrete
checks a reviewer can run without pulling the repo:

| Paper claim | How to verify on https://ontserve.ontorealm.net |
|---|---|
| 134 ontologies (§4) | Homepage ontology listing with source/type facets |
| Three professional codes of ethics (§4) | [ASCE](https://ontserve.ontorealm.net/ontology/ASCE%20Code%20of%20Ethics), [ASME](https://ontserve.ontorealm.net/ontology/ASME%20Code%20of%20Ethics), [IEEE](https://ontserve.ontorealm.net/ontology/IEEE%20Code%20of%20Ethics) |
| Foundation ontologies (§4) | [BFO](https://ontserve.ontorealm.net/ontology/bfo), [IAO](https://ontserve.ontorealm.net/ontology/Information%20Artifact%20Ontology%202020), [Relations Ontology 2015](https://ontserve.ontorealm.net/ontology/Relations%20Ontology%202015) |
| Core ontology and nine disjoint component classes (§3, §4) | [`proethica-core`](https://ontserve.ontorealm.net/ontology/proethica-core) |
| Intermediate ontology with nine-component framework (§4) | [`proethica-intermediate`](https://ontserve.ontorealm.net/ontology/proethica-intermediate) |
| Domain ontology for engineering ethics (§4) | [`engineering-ethics`](https://ontserve.ontorealm.net/ontology/engineering-ethics) |
| 119 case ontologies spanning NSPE BER 1958-2025 (§5) | Homepage "Case" filter |
| Figure 1 worked example, NSPE BER Case 72 | [`proethica-case-72`](https://ontserve.ontorealm.net/ontology/proethica-case-72), abbreviated fixture at [`fixtures/cases/case_072.ttl`](fixtures/cases/case_072.ttl) |
| SPARQL endpoint (§4) | `POST https://ontserve.ontorealm.net/sparql` with a `{"query": "..."}` body, or `GET /sparql?query=...` |
| SPARQL service load source + counts | `GET https://ontserve.ontorealm.net/sparql/status` |

[`tools/verify_paper_claims.py`](tools/verify_paper_claims.py) runs
the above checks automatically and prints a pass/fail table:

```bash
python tools/verify_paper_claims.py
python tools/verify_paper_claims.py --json
python tools/verify_paper_claims.py --base-url http://localhost:5003
```

Exit code is zero iff every claim resolves on the target deployment.

## Production Deployment

The live deployment is managed by the systemd units in
[`deploy/systemd/`](deploy/systemd/). The web interface and MCP server
run as separate services behind a reverse proxy at
https://ontserve.ontorealm.net. The web app initializes the SPARQL
service on startup against the PostgreSQL ``ontology_versions`` table,
so `/sparql` and `/sparql/status` on the public domain serve the full
graph without needing the MCP port.
