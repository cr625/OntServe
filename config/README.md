# OntServe Configuration

Environment configuration files for OntServe.

## Configuration Files

- `development.env` - Development environment settings
- `production.env.template` - Production environment template (copy to `.env` and customize)
- `test.env` - Testing environment settings
- `config_loader.py` - Centralized config loader (priority: env vars > root `.env` > `config/{env}.env`)
- `entity_display.yaml` - Entity type display rules for web interface
- `case_display.yaml` - Case ontology section layout for web interface

## Environment Variables

### Core Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `FLASK_ENV` | Environment mode | `development` |
| `FLASK_DEBUG` | Enable debug mode (0/1) | `1` |
| `ENVIRONMENT` | Environment name | `development` |
| `SECRET_KEY` | Flask session secret | required in production |

### Database

| Variable | Description | Default |
|----------|-------------|---------|
| `ONTSERVE_DB_URL` | PostgreSQL connection string | `postgresql://postgres:PASS@localhost:5432/ontserve` |
| `ONTSERVE_MAX_CONNECTIONS` | Connection pool size | `10` |
| `ONTSERVE_QUERY_TIMEOUT` | Query timeout (seconds) | `30` |
| `ONTSERVE_ENABLE_VECTOR_SEARCH` | Enable pgvector search | `true` |

### Servers

| Variable | Description | Default |
|----------|-------------|---------|
| `ONTSERVE_MCP_PORT` | MCP server port | `8082` |
| `ONTSERVE_WEB_PORT` | Web server port | `5003` |
| `ONTSERVE_DEBUG` | MCP debug logging | `true` |

### Web Application (read by `web/config.py`)

| Variable | Description | Default |
|----------|-------------|---------|
| `ONTSERVE_STORAGE_DIR` | Storage directory path | `<project_root>/storage` |
| `ONTSERVE_CACHE_DIR` | Cache directory path | `<storage>/cache/downloads` |
| `ONTOLOGY_BASE_URI` | Base URI for ontologies | `https://ontserve.ontorealm.net/` |
| `ONTOLOGY_NAMESPACE_TEMPLATE` | Namespace URI template | `{base_uri}ontology/{name}#` |

## Setup

### Development

The root `.env` file and `config/development.env` are loaded automatically on startup.

### Production

1. Copy `production.env.template` to `/opt/ontserve/.env`
2. Set a strong `SECRET_KEY`
3. Configure production database URL
4. Deploy using systemd services (see DEPLOYMENT.md)

### Testing

Test configuration loads automatically via `conftest.py`.
