# SQLAlchemy 2.0 Migration Guide

This document outlines the breaking changes when migrating from SQLAlchemy 1.4 to 2.0 and how they affect OntServe.

## Major Breaking Changes

### 1. Query API Changes

**Old (SQLAlchemy 1.4)**:
```python
# Session.query() method
user = session.query(User).filter_by(id=1).first()
users = session.query(User).filter(User.name.like('%john%')).all()
count = session.query(User).count()
```

**New (SQLAlchemy 2.0)**:
```python
from sqlalchemy import select
from sqlalchemy.orm import Session

# Use select() with session.execute()
stmt = select(User).where(User.id == 1)
user = session.execute(stmt).scalar_one_or_none()

stmt = select(User).where(User.name.like('%john%'))
users = session.execute(stmt).scalars().all()

stmt = select(func.count()).select_from(User)
count = session.execute(stmt).scalar()
```

### 2. Relationship Loading

**Old**:
```python
# Lazy loading was default
user.posts  # Automatically loads posts
```

**New**:
```python
from sqlalchemy.orm import selectinload

# Explicit loading required in 2.0 style
stmt = select(User).options(selectinload(User.posts)).where(User.id == 1)
user = session.execute(stmt).scalar_one()
```

### 3. Flask-SQLAlchemy Changes

**Old (Flask-SQLAlchemy 2.x with SQLAlchemy 1.4)**:
```python
User.query.filter_by(email=email).first()
db.session.query(OntologyEntity).filter_by(uri=uri).first()
```

**New (Flask-SQLAlchemy 3.x with SQLAlchemy 2.0)**:
```python
db.session.execute(select(User).filter_by(email=email)).scalar_one_or_none()
db.session.execute(select(OntologyEntity).where(OntologyEntity.uri == uri)).scalar_one_or_none()

# Or use the convenience method
db.session.get(User, user_id)  # Get by primary key
```

## Files Requiring Updates in OntServe

### web/models.py
- Update all `ClassName.query.*` patterns
- Add `from sqlalchemy import select` import
- Replace `.query.filter_by()` with `db.session.execute(select()...)`
- Replace `.query.all()` with `.scalars().all()`
- Replace `.query.first()` with `.scalar_one_or_none()`

### storage/postgresql_storage.py
- Update raw SQL execution methods
- Ensure connection and session management follows 2.0 patterns
- Update any ORM-based queries

### web/app.py
- Update all database queries in route handlers
- Replace `Model.query.*` with `db.session.execute(select(Model)...)`

## Common Patterns

### Pattern 1: Get Single Record by Filter
```python
# Old
entity = OntologyEntity.query.filter_by(uri=uri).first()

# New
stmt = select(OntologyEntity).where(OntologyEntity.uri == uri)
entity = db.session.execute(stmt).scalar_one_or_none()
```

### Pattern 2: Get All Records with Filter
```python
# Old
entities = OntologyEntity.query.filter_by(ontology_id=ont_id).all()

# New
stmt = select(OntologyEntity).where(OntologyEntity.ontology_id == ont_id)
entities = db.session.execute(stmt).scalars().all()
```

### Pattern 3: Count Records
```python
# Old
count = OntologyEntity.query.count()

# New
from sqlalchemy import func
stmt = select(func.count()).select_from(OntologyEntity)
count = db.session.execute(stmt).scalar()
```

### Pattern 4: Get by Primary Key
```python
# Old
entity = OntologyEntity.query.get(entity_id)

# New - Simplified
entity = db.session.get(OntologyEntity, entity_id)
```

### Pattern 5: Complex Joins
```python
# Old
results = db.session.query(OntologyEntity, Ontology).join(Ontology).filter(
    Ontology.name == 'proethica-core'
).all()

# New
stmt = (
    select(OntologyEntity, Ontology)
    .join(Ontology)
    .where(Ontology.name == 'proethica-core')
)
results = db.session.execute(stmt).all()
```

### Pattern 6: Order By and Limit
```python
# Old
entities = OntologyEntity.query.order_by(OntologyEntity.label).limit(10).all()

# New
stmt = select(OntologyEntity).order_by(OntologyEntity.label).limit(10)
entities = db.session.execute(stmt).scalars().all()
```

## Result Handling

### Scalar Methods
- `.scalar()` - Get first column of first row (or None)
- `.scalar_one()` - Get first column of first row (raise if not exactly one)
- `.scalar_one_or_none()` - Get first column of first row (or None, raise if multiple)
- `.scalars()` - Get all first columns
- `.scalars().all()` - Get all first columns as list

### Row Methods
- `.first()` - Get first row (or None)
- `.one()` - Get exactly one row (raise otherwise)
- `.one_or_none()` - Get one row or None (raise if multiple)
- `.all()` - Get all rows

## Migration Strategy for OntServe

1. **Backup Database**: Create backup before migration
2. **Update Requirements**: Install SQLAlchemy 2.0.44 and Flask-SQLAlchemy 3.1.1
3. **Run Tests**: Ensure all tests pass before code changes
4. **Update Models File**: Start with web/models.py
5. **Update Storage Layer**: Update storage/postgresql_storage.py
6. **Update Routes**: Update web/app.py and editor/routes.py
7. **Run Tests Again**: Verify all functionality works
8. **Check Performance**: Monitor query performance

## Testing Checklist

- [ ] Database connection works
- [ ] All models can be queried
- [ ] Ontology import/export works
- [ ] Entity CRUD operations work
- [ ] Search functionality works
- [ ] User authentication works
- [ ] MCP server database queries work
- [ ] SPARQL service works
- [ ] Versioning system works
- [ ] Concept manager works

## Common Errors and Solutions

### Error: "AttributeError: 'NoneType' object has no attribute 'query'"
**Solution**: Replace `Model.query` with `select(Model)`

### Error: "This Session's transaction has been rolled back"
**Solution**: Ensure proper session handling and commit/rollback

### Error: "Can't execute multiple result sets"
**Solution**: Use `.scalars()` or `.scalar()` instead of raw `.execute()`

## Resources

- SQLAlchemy 2.0 Documentation: https://docs.sqlalchemy.org/en/20/
- Flask-SQLAlchemy 3.x Documentation: https://flask-sqlalchemy.palletsprojects.com/
- SQLAlchemy 2.0 Migration Guide: https://docs.sqlalchemy.org/en/20/changelog/migration_20.html

## Rollback Plan

If issues arise during migration:
1. Restore from backup
2. Revert requirements to SQLAlchemy 1.4
3. Restore code changes from git
4. Investigate issues in development environment
5. Re-attempt migration with fixes
