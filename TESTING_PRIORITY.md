# OntServe Testing Priority Summary

**Date**: 2025-11-17
**Status**: Tests created, awaiting execution
**Critical Risk**: ProEthica integration breakage

---

## CRITICAL: ProEthica Integration Must Not Break

### Why This Matters

ProEthica (production system serving professional ethics research) depends on OntServe for:
1. **Document annotation** - HTTP REST API (Port 5003)
2. **Concept extraction** - MCP JSON-RPC (Port 8082)
3. **Entity queries** - Both HTTP and MCP

**Any breaking changes will stop ProEthica from functioning.**

---

## Test Files Created (Ready to Run)

### 1. ProEthica Integration Tests (HIGHEST PRIORITY)
**File**: `tests/integration/test_proethica_integration.py`
**Tests**: 19 comprehensive integration tests
**Coverage**:
- ✅ HTTP REST API endpoints
- ✅ MCP JSON-RPC methods
- ✅ Tool availability (get_entities_by_category, etc.)
- ✅ Response formats (result.content[0].text)
- ✅ Entity field names (id/uri, label/name, etc.)
- ✅ Breaking change protection

**Run with**:
```bash
pytest tests/integration/test_proethica_integration.py -v
```

### 2. Route Tests (Regression Protection)
**File**: `tests/integration/test_routes.py`
**Tests**: 11 route tests
**Coverage**:
- ✅ Edit route functionality (fixes the bug we just found)
- ✅ Route conflict resolution
- ✅ URL encoding with spaces
- ✅ Authentication redirects
- ✅ Reserved route names

**Run with**:
```bash
pytest tests/integration/test_routes.py -v
```

### 3. Existing Tests (From Phase 1.3)
- `tests/unit/test_config_loader.py` - 13 tests
- `tests/unit/test_imports.py` - 1 test
- `tests/integration/test_mcp_server.py` - 27 tests
- `tests/api/test_compatibility.py` - 15 tests

**Total**: 66+ tests covering unit, integration, and API compatibility

---

## Action Required: Install Dependencies & Run Tests

### Step 1: Install Test Dependencies (5 minutes)

```bash
cd /home/chris/onto/OntServe
pip install pytest-asyncio pytest-flask pytest-cov aiohttp
```

### Step 2: Run ProEthica Integration Tests (5 minutes)

```bash
# Run ONLY ProEthica integration tests
pytest tests/integration/test_proethica_integration.py -v

# Expected: 19 tests, some may fail due to missing fixtures
# Fix fixtures, then re-run until all pass
```

### Step 3: Run All Tests (10 minutes)

```bash
# Run all tests
pytest -v --tb=short

# With coverage
pytest --cov=. --cov-report=html --cov-report=term-missing
```

### Step 4: View Coverage Report

```bash
# Open in browser
xdg-open htmlcov/index.html  # Linux
# or
open htmlcov/index.html  # Mac
```

---

## What Tests Verify

### Breaking Change Protection

These tests will FAIL if you accidentally:
- ❌ Change port 5003 (REST API)
- ❌ Change port 8082 (MCP)
- ❌ Change entity field names (id, uri, label, name, etc.)
- ❌ Change MCP response format (result.content[0].text)
- ❌ Change tool argument names (category, domain_id, status)
- ❌ Remove required MCP tools (get_entities_by_category, etc.)

### Integration Verification

Tests verify these critical flows work:
- ✅ ProEthica can query ontology entities via REST API
- ✅ ProEthica can call MCP tools via JSON-RPC
- ✅ Entity data has correct field names
- ✅ Responses are in expected format
- ✅ All required tools exist

### Regression Protection

Tests catch bugs like:
- ✅ Edit route returning 404 (bug we just fixed)
- ✅ Route conflicts with catch-all patterns
- ✅ URL encoding issues
- ✅ Authentication redirect loops

---

## Test Results Interpretation

### All Tests Pass ✅
**Meaning**: Safe to continue with modernization
**Action**: Proceed with Phase 1.2 (SQLAlchemy migration)

### ProEthica Tests Fail ❌
**Meaning**: CRITICAL - Breaking change detected
**Action**:
1. DO NOT DEPLOY
2. Fix the failing test
3. Verify integration with ProEthica
4. Re-run tests until all pass

### Other Tests Fail ⚠️
**Meaning**: Non-critical but should be fixed
**Action**:
1. Review failure
2. Fix if related to new features
3. May proceed with caution

---

## Integration with Modernization

### Phase 1.2: SQLAlchemy Migration

**Before migration**:
- [ ] Install test dependencies
- [ ] Run all tests - get baseline
- [ ] Ensure ProEthica tests pass

**During migration**:
- Run tests after each file update
- Focus on ProEthica integration tests
- Fix immediately if tests fail

**After migration**:
- [ ] All tests pass (especially ProEthica)
- [ ] Coverage maintained or improved
- [ ] No breaking changes

### Phase 2: MCP Modernization

**Before MCP changes**:
- [ ] All MCP tests passing
- [ ] Document current MCP tool signatures
- [ ] Baseline performance metrics

**During MCP modernization**:
- Update tests to match new MCP spec
- Ensure backward compatibility
- Test with ProEthica

---

## Quick Reference Commands

```bash
# Install dependencies
pip install pytest-asyncio pytest-flask pytest-cov aiohttp

# Run ProEthica integration tests only
pytest tests/integration/test_proethica_integration.py -v

# Run route tests only
pytest tests/integration/test_routes.py -v

# Run all integration tests
pytest tests/integration/ -v

# Run all tests with coverage
pytest --cov=. --cov-report=html --cov-report=term-missing

# Run tests in watch mode (continuous)
ptw -- -v  # requires: pip install pytest-watch

# Run only fast tests (skip slow integration tests)
pytest -m "not slow" -v
```

---

## Files to Review

1. **PROETHICA_ONTSERVE_INTEGRATION.md** - Integration documentation
2. **TESTING_ASSESSMENT.md** - Comprehensive testing plan
3. **tests/integration/test_proethica_integration.py** - ProEthica tests
4. **tests/integration/test_routes.py** - Route tests
5. **tests/README.md** - Testing guide

---

## Success Criteria Before Continuing

### Must Complete Today
- [ ] Test dependencies installed
- [ ] All tests run successfully
- [ ] ProEthica integration tests pass (19/19)
- [ ] Route tests pass (11/11)
- [ ] Baseline coverage report generated

### Nice to Have
- [ ] 60%+ code coverage
- [ ] Sample test data created
- [ ] UI tests with Playwright
- [ ] Pre-commit hooks set up

---

## Risk Assessment

**Without Tests**:
- 🔴 HIGH RISK of breaking ProEthica
- 🔴 Unknown what's currently working
- 🔴 Can't safely refactor
- 🔴 SQLAlchemy migration dangerous

**With Tests Passing**:
- 🟢 Safe to refactor
- 🟢 Confidence in changes
- 🟢 ProEthica protected
- 🟢 Can deploy with confidence

---

## Next Session Checklist

When resuming work:
1. ✅ Review this document
2. ✅ Run tests to verify current state
3. ✅ Check ProEthica integration tests pass
4. ✅ Review coverage report
5. ✅ Proceed with next modernization phase

**Do NOT proceed with Phase 1.2 (SQLAlchemy migration) until all ProEthica integration tests pass.**

---

## Questions?

- See TESTING_ASSESSMENT.md for detailed analysis
- See tests/README.md for testing guide
- See PROETHICA_ONTSERVE_INTEGRATION.md for integration details
