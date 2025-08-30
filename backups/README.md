# OntServe Database Backups

This directory contains PostgreSQL database backups for the OntServe system.

## Backup System

### Automatic Backups
- **Location**: `/home/chris/onto/OntServe/backups/`
- **Format**: `ontserve_backup_YYYYMMDD_HHMMSS.sql`
- **Latest Symlink**: `ontserve_backup_latest.sql` always points to the most recent backup

### Creating Backups

```bash
# Run backup script
cd /home/chris/onto/OntServe
./scripts/backup_database.sh
```

### Restoring Backups

```bash
# Restore from latest backup
./scripts/restore_database.sh latest

# Restore from specific backup
./scripts/restore_database.sh ontserve_backup_20250829_211940.sql

# List available backups
./scripts/restore_database.sh
```

## Database Information

- **Database Name**: `ontserve`
- **Host**: `localhost:5432`
- **User**: `ontserve_user`
- **Schema**: Full schema with extensions (uuid-ossp, vector)

## Backup Contents

The backup includes:
- **Schema**: Complete table structure, indexes, constraints, triggers
- **Extensions**: UUID and vector extensions
- **Data**: All ontology data, entities, versions, users, audit logs
- **Functions**: Custom database functions and triggers
- **Views**: Materialized and standard views

## Database Tables

### Core Tables
- `ontologies` - Ontology metadata and content
- `ontology_versions` - Version history and content
- `ontology_entities` - Individual entities (classes, properties)
- `ontology_imports` - Import relationships between ontologies

### Concept Management  
- `concepts` - Concept definitions with approval workflow
- `concept_triples` - RDF triples with temporal and embedding data
- `concept_relationships` - Relationships between concepts
- `concept_versions` - Version history for concepts

### Workflow & Administration
- `approval_workflows` - Concept approval process management
- `candidate_metadata` - Extraction session metadata
- `domains` - Professional domain management
- `users` - User accounts and permissions
- `audit_log` - Complete audit trail

### System
- `search_history` - Query history and analytics
- `system_config` - System-wide configuration

## Security Notes

- Backups contain complete database structure and data
- Password authentication handled via environment variables
- No sensitive data should be committed to version control
- Backups should be stored securely and access-controlled

## Maintenance

### Recommended Backup Schedule
- **Development**: Manual backups before major changes
- **Production**: Daily automated backups with retention policy
- **Critical Changes**: Manual backup before schema migrations

### Backup Retention
- Keep at least 7 recent backups
- Archive monthly backups for longer-term retention
- Monitor backup sizes and cleanup old backups as needed

## Troubleshooting

### Common Issues
1. **Permission Errors**: Ensure PGPASSWORD environment variable is set
2. **Connection Issues**: Verify PostgreSQL service is running
3. **Space Issues**: Check disk space before creating backups
4. **Restore Failures**: Ensure target database exists and is empty

### Verification
```bash
# Check backup integrity
pg_restore --list /path/to/backup.sql

# Verify restore
psql -h localhost -U ontserve_user -d ontserve -c "\dt"
```

---
*Last Updated: 2025-08-29*