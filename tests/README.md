# OntServe Tests

Pytest suite for OntServe. Unit tests are fast and hermetic; integration and
API tests exercise the Flask app, the MCP server, and (optionally) a live
Postgres database.

## Running

```bash
# Full suite
pytest

# By category
pytest -m unit          # Fast, no external deps
pytest -m integration   # Flask/MCP/DB
pytest -m api           # ProEthica MCP contract + HTTP compatibility
pytest -m "not slow"    # Skip long-running tests

# Coverage
pytest --cov=web --cov=servers --cov=storage --cov-report=term-missing
```

## Layout

```
tests/
  conftest.py              Shared fixtures (DB session, Flask app, MCP client)
  unit/                    Isolated component tests
  integration/             Flask routes, MCP server, ontology sync
  api/                     ProEthica MCP contract and HTTP compatibility
```

## Database

Integration tests that need a database use the session-scoped
``db_session`` fixture in ``conftest.py``. Set ``ONTSERVE_DB_URL`` to point at
a disposable test database; the fixture rolls back after each test.
