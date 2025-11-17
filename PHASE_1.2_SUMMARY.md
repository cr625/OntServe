# Phase 1.2: Dependency Updates - Summary

**Status**: Documentation Complete, Implementation Pending
**Date**: 2025-11-16

## Overview

Phase 1.2 focuses on updating OntServe's dependencies to the latest stable versions (2025). This includes major version upgrades that require code changes.

## Files Created

### 1. requirements-2025.txt
Updated requirements file with latest stable versions:
- **Python**: 3.11+ required (3.12 recommended)
- **Flask**: 2.3.2 → 3.1.0
- **SQLAlchemy**: 1.4.0 → 2.0.44 (BREAKING CHANGES)
- **Flask-SQLAlchemy**: 3.0.0 → 3.1.1
- **rdflib**: 6.3.2 → 7.4.0
- **aiohttp**: 3.8.0 → 3.13.2
- **psycopg2-binary**: 2.9.6 → 2.9.11
- **asyncpg**: 0.28.0 → 0.30.0
- **owlready2**: 0.43 → 0.46
- **pgvector**: 0.2.0 → 0.3.6

### 2. SQLALCHEMY_2.0_MIGRATION.md
Comprehensive migration guide for SQLAlchemy 2.0:
- Breaking changes documentation
- Code pattern conversions (old vs new)
- Common errors and solutions
- Migration strategy
- Testing checklist
- Rollback plan

## Impact Analysis

### Files Requiring SQLAlchemy 2.0 Updates

Grep search found **109 occurrences** of legacy query patterns across **9 files**:

1. **web/models.py** - 5 occurrences
2. **web/app.py** - 56 occurrences
3. **editor/routes.py** - 24 occurrences
4. **web/init_default_ontologies.py** - 2 occurrences
5. **web/cli.py** - 4 occurrences
6. **web/import_to_db.py** - 1 occurrence
7. **core/ontology_merger.py** - 1 occurrence
8. **backups/verify_production.py** - 3 occurrences
9. **SQLALCHEMY_2.0_MIGRATION.md** - 13 occurrences (documentation examples)

### Critical Files

**High Priority**:
- `web/app.py` (56 queries) - Main application routes
- `editor/routes.py` (24 queries) - Editor functionality
- `web/models.py` (5 queries) - Model definitions

**Medium Priority**:
- `web/cli.py` (4 queries) - CLI commands
- `web/init_default_ontologies.py` (2 queries) - Initialization
- `backups/verify_production.py` (3 queries) - Backup verification

**Low Priority**:
- `web/import_to_db.py` (1 query) - Import functionality
- `core/ontology_merger.py` (1 query) - Ontology merging

## Migration Strategy

### Phase 1: Preparation (Complete)
- [x] Create requirements-2025.txt
- [x] Document breaking changes
- [x] Create migration guide
- [x] Analyze impact

### Phase 2: Safe Migration (Recommended Approach)
1. **Backup Everything**
   - Database backup
   - Git commit current state
   - Document current functionality

2. **Install Dependencies in Virtual Environment**
   ```bash
   python3 -m venv venv-2025
   source venv-2025/bin/activate
   pip install -r requirements-2025.txt
   ```

3. **Update Files Incrementally**
   - Start with `web/models.py` (low risk)
   - Then `web/cli.py` (low risk)
   - Then `editor/routes.py` (medium risk)
   - Finally `web/app.py` (high risk)
   - Test after each file update

4. **Run Tests**
   - Run existing tests after each file
   - Add new tests for critical paths
   - Test all API endpoints
   - Test MCP server connectivity
   - Test ProEthica integration

5. **Verify Compatibility**
   - Test all external API endpoints
   - Verify MCP tools work
   - Test SPARQL queries
   - Test ontology import/export
   - Test URI resolution

## Breaking Changes Summary

### SQLAlchemy 2.0

**Query Pattern Changes**:
```python
# Old
User.query.filter_by(email=email).first()

# New
from sqlalchemy import select
stmt = select(User).where(User.email == email)
user = db.session.execute(stmt).scalar_one_or_none()
```

**Result Handling**:
- `.first()` → `.scalar_one_or_none()`
- `.all()` → `.scalars().all()`
- `.count()` → `select(func.count()).select_from(Model)`
- `.get(id)` → `db.session.get(Model, id)` (unchanged, still works)

### Flask 3.1

Minor changes:
- Improved type hints
- Better async support
- Security improvements
- No major breaking changes expected

### rdflib 7.4.0

Minor API changes:
- Review SPARQL query syntax
- Check namespace handling
- Verify serialization methods

## Risk Assessment

### High Risk Changes
- **SQLAlchemy 2.0 Migration**: 109 query patterns to update
  - Risk: Database query failures
  - Mitigation: Incremental updates, comprehensive testing
  - Rollback: Git revert, requirements rollback

### Medium Risk Changes
- **Flask 3.1 Update**: API route changes
  - Risk: Deprecation warnings, minor incompatibilities
  - Mitigation: Review Flask changelog, test all routes
  - Rollback: Revert requirements

### Low Risk Changes
- **rdflib 7.4.0**: SPARQL and RDF handling
  - Risk: Query syntax issues
  - Mitigation: Test SPARQL service
  - Rollback: Revert requirements

## Testing Requirements

### Unit Tests
- [ ] All existing tests pass
- [ ] Add tests for new query patterns
- [ ] Test database connections
- [ ] Test ORM operations

### Integration Tests
- [ ] MCP server starts successfully
- [ ] Web server starts successfully
- [ ] Database queries work
- [ ] SPARQL queries work
- [ ] Ontology import works
- [ ] Entity CRUD operations work

### API Compatibility Tests
- [ ] All MCP tools respond correctly
- [ ] HTTP endpoints return expected results
- [ ] ProEthica integration works
- [ ] URI resolution works
- [ ] SPARQL endpoint works

## Recommendations

### Option 1: Complete Migration Now
**Pros**:
- Get modernization done in one session
- Easier to track changes

**Cons**:
- High risk of breaking changes
- Requires extensive testing
- Time-consuming

### Option 2: Staged Migration (RECOMMENDED)
**Pros**:
- Lower risk
- Easier to identify issues
- Can rollback individual changes
- Better for production systems

**Cons**:
- Takes longer
- Requires multiple commits

### Option 3: Defer to Later Phase
**Pros**:
- Focus on MCP modernization first
- Less risk during early phases

**Cons**:
- Delays full modernization
- May have dependency conflicts

## Recommended Next Steps

Given the scope of changes (109 query updates), I recommend:

1. **Commit current progress**:
   - requirements-2025.txt
   - SQLALCHEMY_2.0_MIGRATION.md
   - PHASE_1.2_SUMMARY.md

2. **Decision Point**:
   - **Option A**: Continue with SQLAlchemy migration now
   - **Option B**: Move to Phase 1.3 (testing setup) first, then return
   - **Option C**: Proceed to Phase 2 (MCP modernization), handle dependencies later

3. **If continuing now**:
   - Create development environment
   - Install new dependencies
   - Start with low-risk files
   - Test incrementally

## Compatibility Notes

### External Dependencies
- All external API contracts preserved
- No changes to MCP tool signatures
- No changes to HTTP endpoints
- ProEthica integration unaffected

### Database Schema
- No schema changes required
- SQLAlchemy 2.0 is query API changes only
- Existing database works without migration

## Resources Created

1. **requirements-2025.txt** - Updated dependencies
2. **SQLALCHEMY_2.0_MIGRATION.md** - Migration guide
3. **PHASE_1.2_SUMMARY.md** - This summary

## Status

**Phase 1.2 Status**: Documentation Complete, Code Migration Pending

**Recommended Action**: Decide on migration approach before proceeding.
