# OntExtract Production Database Backup

**Created**: September 5, 2025  
**Size**: 519KB  
**Status**: JCDL Paper Implementation Complete  
**Production Path**: `/opt/ontextract/`  
**Backup Location**: `OntServe/backups/`

## Files Included

### Main Backup
- **`ontextract_backup_20250905_204134.sql`** - Complete database dump (519KB)
  - All tables, data, indexes, and constraints
  - Academic anchor framework with exact JCDL citations
  - Vector-based semantic drift calculations
  - PostgreSQL with pgvector extension support

### Restore Scripts  
- **`restore_production.sh`** - Automated production restore script (production-aware paths)
- **`verify_production.py`** - Post-restore verification script (production-aware paths)

## What's Included in This Backup

### JCDL Paper Implementations
- **Academic Anchor Framework**: 4 foundational terms with scholarly citations
  - Anscombe (1957): Philosophical agency and intentional action
  - Jensen & Meckling (1976): Principal-agent economic theory  
  - Wooldridge & Jennings (1995): Computational intelligent agents
  - Sutton & Barto (2018): Reinforcement learning agents
- **Vector-Based Drift Analysis**: PostgreSQL pgvector integration
- **Period-Aware Embedding Infrastructure**: Historical model selection
- **Experiment 29**: Agent evolution visualization framework

### Database Schema
- **Terms & TermVersions**: Complete temporal analysis framework
- **Experiments**: Research workflows and configurations
- **Semantic Drift**: Vector-based drift calculations
- **Document Processing**: Multi-format analysis pipeline
- **User Management**: Authentication and session handling
- **Vector Storage**: pgvector embeddings table

## Production Restore Instructions

### Quick Restore (Recommended)
```bash
# 1. Copy backup files to production server
scp -r OntServe/backups/ user@production:/opt/
cd /opt/backups

# 2. Run automated restore
./restore_production.sh

# 3. Verify installation
python verify_production.py
```

### Manual Restore
```bash
# 1. Create database and install pgvector
createdb -U ontextract_user ontextract_db
psql -U ontextract_user -d ontextract_db -c "CREATE EXTENSION vector;"

# 2. Restore from backup
cd /opt/backups
psql -U ontextract_user -d ontextract_db < ontextract_backup_20250905_204134.sql

# 3. Verify key implementations
python verify_production.py
```

## Post-Restore Verification

The `verify_production.py` script checks:
- pgvector extension functionality
- Academic anchor framework (JCDL compliance)
- Experiment 29 configuration
- Vector storage capabilities

Expected output:
```
✅ pgvector extension working
✅ Academic anchors: 4 JCDL versions for 'agent'  
✅ Experiment 29: Agent Evolution: JCDL Academic Anchor Framework
✅ Vector storage: document embeddings table ready
```

## Environment Configuration

Update production `.env` file:
```bash
# Database Configuration
DATABASE_URL=postgresql://ontextract_user:YOUR_PASSWORD@localhost:5432/ontextract_db
SQLALCHEMY_DATABASE_URI=postgresql://ontextract_user:YOUR_PASSWORD@localhost:5432/ontextract_db

# JCDL Paper Features
ENABLE_PERIOD_AWARE_EMBEDDINGS=true
ENABLE_VECTOR_DRIFT_ANALYSIS=true
ENABLE_ACADEMIC_ANCHORS=true
```

## Testing JCDL Implementation

After restore, run the comprehensive test suite:
```bash
cd /opt/ontextract
python scripts/test_jcdl_implementation.py
```

This verifies all 5 JCDL paper claims:
1. PostgreSQL pgvector operations
2. Period-aware embedding selection  
3. Academic anchor framework
4. Vector-based semantic drift calculations
5. End-to-end integration

## Troubleshooting

### pgvector Issues
```bash
# Install pgvector if missing
sudo apt-get install postgresql-14-pgvector
psql -U ontextract_user -d ontextract_db -c "CREATE EXTENSION vector;"
```

### Permission Issues
```bash
# Set correct database permissions
psql -U postgres -c "ALTER USER ontextract_user CREATEDB;"
```

### Missing Dependencies
```bash
# Install required packages
pip install -r requirements.txt
```

---

**Status**: Production-ready with all JCDL paper implementations verified
**Next Steps**: Deploy to production server and run verification scripts