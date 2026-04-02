# OntServe

Central ontology management and serving system. Provides ontology storage, entity extraction, semantic search, and an MCP server for tool-based integration with ProEthica and other ontology consumers.

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
  servers/          MCP server (FastMCP 3.x)
    mcp_server.py     8 tools for entity/concept management
  web/              Flask web interface
    app.py            Application entry point
    config.py         Flask configuration classes
  core/             Ontology processing (manager, merger, enhanced processor)
  storage/          PostgreSQL + file storage backends
  config/           Environment configs + YAML display configs
  importers/        Format-specific importers (BFO, PROV-O, OWL)
  editor/           Ontology editing UI (Flask blueprint)
  ontologies/       TTL ontology files
  services/         SPARQL and sync services
  tests/            Unit, integration, and API tests
```

## Configuration

Environment variables are loaded from `config/{environment}.env` and the root `.env` file. See [config/README.md](config/README.md) for the full variable reference.

Key variables:
- `ONTSERVE_DB_URL` -- PostgreSQL connection string
- `ONTSERVE_MCP_PORT` -- MCP server port (default: 8082)
- `ONTSERVE_WEB_PORT` -- Web server port (default: 5003)

## MCP Tools

The MCP server exposes 8 tools for ontology integration:

| Tool | Description |
|------|-------------|
| `get_entities_by_category` | Retrieve entities by type (Role, Principle, etc.) |
| `submit_candidate_concept` | Submit new concept for review |
| `sparql_query` | Direct SPARQL query execution |
| `update_concept_status` | Update concept workflow status |
| `get_candidate_concepts` | Retrieve pending concepts |
| `store_extracted_entities` | Store extraction results |
| `get_case_entities` | Retrieve case-specific entities |
| `get_domain_info` | Get domain metadata |

## Testing

```bash
source venv-ontserve/bin/activate
python -m pytest tests/ -v
```

Tests are organized into `unit/`, `integration/`, and `api/` directories. See [tests/README.md](tests/README.md) for details on markers and fixtures.

## Production Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for production setup on the DigitalOcean server.

**Production URL:** https://ontserve.ontorealm.net
