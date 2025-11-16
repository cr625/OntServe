# OntServe Testing Guide

Comprehensive testing infrastructure for OntServe modernization and maintenance.

## Quick Start

```bash
# Run all tests
pytest

# Run specific test categories
pytest -m unit                  # Unit tests only
pytest -m integration           # Integration tests only
pytest -m api                   # API compatibility tests only
pytest -m mcp                   # MCP server tests only

# Run with coverage
pytest --cov=. --cov-report=html

# Run and view coverage report
pytest --cov=. --cov-report=html && open htmlcov/index.html
```

## Test Organization

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── unit/                    # Unit tests (fast, isolated)
│   ├── test_config_loader.py
│   ├── test_imports.py
│   └── test_*.py
├── integration/             # Integration tests (slower, external deps)
│   ├── test_mcp_server.py
│   ├── test_sparql_service.py
│   └── test_*.py
├── api/                     # API compatibility tests
│   ├── test_compatibility.py
│   └── test_*.py
└── fixtures/                # Test data and fixtures
    ├── ontologies/          # Sample ontologies for testing
    └── data/                # Sample test data
```

## Test Types

### Unit Tests (`tests/unit/`)

**Purpose**: Test individual components in isolation

**Characteristics**:
- Fast (<1ms per test)
- No external dependencies
- Mock external services
- Test single function/class

**Example**:
```python
@pytest.mark.unit
def test_config_loader_initialization():
    from config.config_loader import ConfigLoader
    loader = ConfigLoader()
    assert loader.project_root is not None
```

### Integration Tests (`tests/integration/`)

**Purpose**: Test component interactions and external services

**Characteristics**:
- Slower (may take seconds)
- May use database
- May use MCP server
- Test multiple components together

**Example**:
```python
@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
async def test_mcp_server_health(mcp_client):
    response = await mcp_client.get('/health')
    assert response.status == 200
```

### API Compatibility Tests (`tests/api/`)

**Purpose**: Ensure external API contracts remain stable

**Characteristics**:
- Test ProEthica integration
- Verify MCP tool signatures
- Check HTTP endpoint responses
- Validate backward compatibility

**Example**:
```python
@pytest.mark.api
def test_uri_resolution_query_param(client):
    uri = 'http://proethica.org/ontology/intermediate#Honesty'
    response = client.get(f'/resolve?uri={uri}')
    assert response.status_code in [200, 404]
```

## Test Markers

Use markers to categorize and filter tests:

```bash
# Available markers
@pytest.mark.unit           # Unit tests
@pytest.mark.integration    # Integration tests
@pytest.mark.api            # API compatibility tests
@pytest.mark.mcp            # MCP server tests
@pytest.mark.sparql         # SPARQL tests
@pytest.mark.database       # Tests requiring database
@pytest.mark.slow           # Slow tests (>1s)
@pytest.mark.requires_java  # Tests requiring Java (OWL reasoners)
@pytest.mark.external       # Tests requiring external services
```

**Examples**:
```bash
# Skip slow tests
pytest -m "not slow"

# Run only MCP tests
pytest -m mcp

# Run integration tests except database tests
pytest -m "integration and not database"

# Run unit and API tests
pytest -m "unit or api"
```

## Fixtures

### Database Fixtures

```python
def test_with_database(db_session):
    """Use database session with automatic rollback."""
    # db_session provides a database session
    # Automatically rolls back after test
    pass

def test_with_clean_database(clean_database):
    """Use completely clean database."""
    # Creates fresh database schema
    # Drops all tables after test
    pass
```

### Application Fixtures

```python
def test_flask_app(app):
    """Test with Flask application."""
    with app.app_context():
        # Your test code
        pass

def test_with_client(client):
    """Test with Flask test client."""
    response = client.get('/some-endpoint')
    assert response.status_code == 200
```

### MCP Server Fixtures

```python
@pytest.mark.asyncio
async def test_mcp(mcp_server):
    """Test with MCP server instance."""
    # mcp_server provides OntServeMCPServer instance
    pass

@pytest.mark.asyncio
async def test_mcp_with_client(mcp_client):
    """Test with MCP HTTP client."""
    response = await mcp_client.get('/health')
    assert response.status == 200
```

### Test Data Fixtures

```python
def test_with_sample_ontology(sample_ontology_ttl):
    """Test with sample ontology in Turtle format."""
    # sample_ontology_ttl provides TTL string
    pass

def test_with_sample_concept(sample_candidate_concept):
    """Test with sample candidate concept."""
    # sample_candidate_concept provides concept dict
    pass
```

### Helper Fixtures

```python
def test_with_helpers(helpers, db_session):
    """Use test helper methods."""
    ontology = helpers.create_test_ontology(db_session)
    entity = helpers.create_test_entity(db_session, ontology)
```

## Configuration

### pytest.ini

Main pytest configuration:
- Test discovery patterns
- Coverage settings
- Markers
- Logging configuration

### conftest.py

Shared fixtures and configuration for all tests.

## Coverage Reports

```bash
# Generate HTML coverage report
pytest --cov=. --cov-report=html

# View report
open htmlcov/index.html

# Generate terminal coverage report
pytest --cov=. --cov-report=term-missing

# Generate XML coverage report (for CI)
pytest --cov=. --cov-report=xml
```

**Coverage Goals**:
- Overall: 60% minimum (enforced)
- Critical paths: 80%+ target
- Core modules: 70%+ target
- New code: 80%+ target

## Running Specific Tests

```bash
# Run specific test file
pytest tests/unit/test_config_loader.py

# Run specific test class
pytest tests/unit/test_config_loader.py::TestConfigLoader

# Run specific test method
pytest tests/unit/test_config_loader.py::TestConfigLoader::test_load_config_returns_summary

# Run tests matching pattern
pytest -k "config"              # All tests with 'config' in name
pytest -k "test_mcp_server"     # All MCP server tests
```

## Testing Best Practices

### 1. Test Naming

Use descriptive names that explain what is being tested:

```python
# Good
def test_config_loader_masks_password_in_database_url():
    pass

# Bad
def test_config():
    pass
```

### 2. Test Structure (AAA Pattern)

```python
def test_something():
    # Arrange - Set up test data and conditions
    loader = ConfigLoader()

    # Act - Perform the action being tested
    result = loader.load_config('test')

    # Assert - Verify the results
    assert result['environment'] == 'test'
```

### 3. Test Isolation

Each test should be independent:
- Don't rely on test execution order
- Clean up after yourself (fixtures do this)
- Don't share state between tests

### 4. Use Fixtures

Instead of setup/teardown, use fixtures:

```python
# Good
def test_with_database(db_session):
    user = User(name='test')
    db_session.add(user)
    db_session.commit()

# Avoid
def test_manual_setup():
    session = create_session()  # Manual setup
    try:
        user = User(name='test')
        session.add(user)
        session.commit()
    finally:
        session.close()  # Manual cleanup
```

### 5. Test One Thing

Each test should verify one specific behavior:

```python
# Good
def test_user_creation_sets_username():
    user = User(username='john')
    assert user.username == 'john'

def test_user_creation_sets_email():
    user = User(email='john@example.com')
    assert user.email == 'john@example.com'

# Avoid
def test_user_creation():
    user = User(username='john', email='john@example.com')
    assert user.username == 'john'  # Testing multiple things
    assert user.email == 'john@example.com'
    assert user.is_active == True
```

## Continuous Integration

### GitHub Actions

Tests run automatically on:
- Every push to development branches
- Every pull request
- Scheduled nightly builds

Configuration: `.github/workflows/test.yml` (to be created)

### Pre-commit Hooks

Run tests before committing:

```bash
# Install pre-commit hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Debugging Tests

### Verbose Output

```bash
# More verbose output
pytest -vv

# Show local variables in tracebacks
pytest -l

# Show print statements
pytest -s
```

### Debug Specific Test

```bash
# Run with Python debugger
pytest --pdb

# Drop into debugger on failure
pytest --pdb --maxfail=1

# Use ipdb (if installed)
pytest --pdb --pdbcls=IPython.terminal.debugger:TerminalPdb
```

### View Logs

```bash
# Show log output
pytest --log-cli-level=DEBUG

# Show captured output
pytest -s
```

## ProEthica Integration Testing

Special considerations for testing ProEthica integration:

### Required Test Coverage

1. **MCP Tools**:
   - ✅ All 8 tools listed and callable
   - ✅ Tool signatures match expectations
   - ✅ Tool responses format correct

2. **HTTP Endpoints**:
   - ✅ `/resolve` works with query params
   - ✅ `/sparql` accepts queries
   - ✅ `/api/guidelines/{domain}` exists
   - ✅ Content negotiation works

3. **Data Flow**:
   - ✅ Concept submission works
   - ✅ Entity retrieval works
   - ✅ Status updates work
   - ✅ Case entity storage works

## Troubleshooting

### Tests Won't Run

```bash
# Check pytest is installed
pytest --version

# Check test discovery
pytest --collect-only

# Verbose test collection
pytest --collect-only -v
```

### Database Tests Failing

```bash
# Check database is running
psql -U postgres -l

# Check test database exists
psql -U postgres -c "CREATE DATABASE ontserve_test;"

# Check connection string
echo $ONTSERVE_DB_URL
```

### Import Errors

```bash
# Check Python path
python -c "import sys; print(sys.path)"

# Install requirements
pip install -r requirements.txt

# Install test requirements
pip install -r requirements-2025.txt
```

## Writing New Tests

### Template for Unit Test

```python
import pytest

@pytest.mark.unit
class TestMyFeature:
    """Test MyFeature functionality."""

    def test_basic_functionality(self):
        """Test basic feature works."""
        # Arrange
        feature = MyFeature()

        # Act
        result = feature.do_something()

        # Assert
        assert result == expected_value

    def test_error_handling(self):
        """Test feature handles errors correctly."""
        feature = MyFeature()

        with pytest.raises(ValueError):
            feature.do_something_invalid()
```

### Template for Integration Test

```python
import pytest

@pytest.mark.integration
@pytest.mark.database
class TestMyIntegration:
    """Test integration between components."""

    def test_integration_works(self, db_session):
        """Test components work together."""
        # Arrange
        component_a = ComponentA(db_session)
        component_b = ComponentB(db_session)

        # Act
        result = component_a.process(component_b.get_data())

        # Assert
        assert result is not None
```

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest Fixtures](https://docs.pytest.org/en/stable/fixture.html)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)
- [Testing Flask Applications](https://flask.palletsprojects.com/en/stable/testing/)
- [Testing aiohttp Applications](https://docs.aiohttp.org/en/stable/testing.html)

## Support

For issues with tests:
1. Check this README
2. Review test logs
3. Check MODERNIZATION_PROGRESS.md
4. Consult development team
