# OntServe Production Deployment Guide

## Last Updated: September 27, 2025

This document provides instructions for deploying the latest version of OntServe to the production server at https://ontserve.ontorealm.net/

## Pre-Deployment Checklist

- [x] Database backup created: `backups/ontserve_dev_backup_before_deploy.sql`
- [x] Branches merged: develop → main
- [x] Configuration reviewed: No server-specific changes needed in main

## Key Changes in This Release

### Code Improvements
1. **Enhanced MCP Server** (`servers/mcp_server.py`)
   - Added store_extracted_entities and get_case_entities tools
   - Improved concept manager integration
   - Better error handling and logging

2. **Concept Manager Updates** (`storage/concept_manager.py`)
   - Added get_ontology_entities_by_category method
   - Enhanced entity retrieval with dual source support (concepts + ontology)
   - Better metadata handling

3. **Web Interface Enhancements**
   - Environment indicator badge in navigation (development mode only)
   - Improved login flow with next page redirect support
   - ProEthica-specific ontology display with 9-concept framework
   - Template variable calculation optimization

### Repository Cleanup
- Moved old backup files to archive folder
- Updated .gitignore for better organization
- Removed obsolete ontology backup files

## Deployment Steps

### 1. Connect to Production Server
```bash
ssh root@ontserve.ontorealm.net
# or use your specific user account
```

### 2. Navigate to OntServe Directory
```bash
cd /opt/ontserve
# or your production directory
```

### 3. Backup Production Database
```bash
PGPASSWORD=your_prod_password pg_dump -U postgres -h localhost -d ontserve > backups/ontserve_prod_backup_$(date +%Y%m%d_%H%M%S).sql
```

### 4. Pull Latest Code
```bash
git fetch origin
git checkout main
git pull origin main
```

### 5. Update Python Dependencies
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 6. Database Migration

The new code adds methods to concept_manager but doesn't require schema changes. However, ensure the following tables exist:
- candidate_concepts
- concept_versions
- ontology_entities

If needed, run:
```bash
psql -U postgres -d ontserve < config/schema.sql
```

### 7. Environment Configuration

Update production `.env` file if needed:
```bash
# Edit /opt/ontserve/.env or production location
FLASK_ENV=production
FLASK_DEBUG=0
ENVIRONMENT=production
ONTSERVE_DB_URL=postgresql://postgres:PROD_PASSWORD@localhost:5432/ontserve
```

Ensure web/config.py uses ProductionConfig:
- The code already has proper production detection
- SECRET_KEY should be set in environment variables

### 8. Update Ontology Files

Copy any new ontology files if needed:
```bash
# These files are gitignored, so manual copy may be needed
# ontologies/proethica-case-*.ttl files are temporary and should not be copied
```

### 9. Restart Services

```bash
# Stop services
systemctl stop ontserve-web
systemctl stop ontserve-mcp

# Start services
systemctl start ontserve-mcp
systemctl start ontserve-web

# Check status
systemctl status ontserve-mcp
systemctl status ontserve-web
```

Or if using supervisor:
```bash
supervisorctl restart ontserve:*
```

### 10. Verification

1. **Check Web Interface**: https://ontserve.ontorealm.net/
   - Login functionality
   - Ontology visualization
   - Search functionality
   - No "Development" badge should appear

2. **Check MCP Server**: Port 8082
   - Test entity retrieval
   - Verify new tools are available

3. **Check Logs**:
```bash
tail -f /var/log/ontserve/web.log
tail -f /var/log/ontserve/mcp.log
```

## Rollback Plan

If issues arise:

1. **Restore Code**:
```bash
git checkout previous_commit_hash
```

2. **Restore Database** (if needed):
```bash
PGPASSWORD=your_prod_password psql -U postgres -h localhost -d ontserve < backups/ontserve_prod_backup_TIMESTAMP.sql
```

3. **Restart Services**:
```bash
systemctl restart ontserve-web ontserve-mcp
```

## Post-Deployment

1. **Monitor** logs for errors
2. **Test** key functionality:
   - Entity extraction
   - Concept submission
   - SPARQL queries
   - Web interface navigation

3. **Update** documentation if needed

## Notes

- The development database backup is available at `backups/ontserve_dev_backup_before_deploy.sql` if needed for reference
- The archive folder contains old files moved during cleanup - these are not needed in production
- Template changes are backward compatible and don't require data migration
- The new environment indicator only shows in development mode (controlled by config)

## Support

For issues or questions about this deployment, refer to:
- GitHub Issues: https://github.com/MatLab-Research/OntServe/issues
- Development documentation: /home/chris/onto/docs/