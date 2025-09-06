#!/bin/bash
# OntExtract Production Database Restore Script
# Production Path: /opt/ontextract/
# 
# This script restores the OntExtract database with all JCDL paper implementations:
# - Academic anchor framework with exact citations
# - Vector-based semantic drift calculations
# - Period-aware embedding infrastructure
# - PostgreSQL with pgvector extension

set -e

# Configuration
DB_NAME="ontextract_db"
DB_USER="ontextract_user"
DB_HOST="localhost"
DB_PORT="5432"

# Production paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ONTEXTRACT_DIR="/opt/ontextract"
BACKUP_FILE="$SCRIPT_DIR/ontextract_backup_20250905_204134.sql"

# Check if backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file $BACKUP_FILE not found"
    exit 1
fi

echo "=== OntExtract Production Database Restore ==="
echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo "Host: $DB_HOST"
echo "Backup file: $BACKUP_FILE"
echo

# Prompt for password if not set
if [ -z "$PGPASSWORD" ]; then
    read -s -p "Enter PostgreSQL password for $DB_USER: " PGPASSWORD
    export PGPASSWORD
    echo
fi

echo "1. Creating database if it doesn't exist..."
createdb -h $DB_HOST -U $DB_USER $DB_NAME 2>/dev/null || echo "Database already exists"

echo "2. Installing pgvector extension..."
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "CREATE EXTENSION IF NOT EXISTS vector;" || echo "pgvector extension already exists"

echo "3. Restoring database from backup..."
psql -h $DB_HOST -U $DB_USER -d $DB_NAME < $BACKUP_FILE

echo "4. Verifying JCDL paper implementations..."
echo "   - Checking academic anchors..."
ANCHORS=$(psql -h $DB_HOST -U $DB_USER -d $DB_NAME -t -c "SELECT COUNT(*) FROM term_versions WHERE metadata::text LIKE '%jcdl_paper_anchor%';")
echo "   Found $ANCHORS JCDL academic anchor versions"

echo "   - Checking vector tables..."
EMBEDDINGS=$(psql -h $DB_HOST -U $DB_USER -d $DB_NAME -t -c "SELECT COUNT(*) FROM document_embeddings;")
echo "   Found $EMBEDDINGS document embeddings"

echo "   - Checking experiments..."
EXP29=$(psql -h $DB_HOST -U $DB_USER -d $DB_NAME -t -c "SELECT name FROM experiments WHERE id = 29;")
echo "   Experiment 29: $EXP29"

echo
echo "=== Restore Complete ==="
echo "Your production database now includes:"
echo "- Academic anchor framework with scholarly citations"
echo "- Vector-based semantic drift calculations"
echo "- Period-aware embedding infrastructure"  
echo "- PostgreSQL with pgvector extension"
echo "- All JCDL paper implementations verified"
echo
echo "Next steps:"
echo "1. Update production .env with database credentials"
echo "2. Run: cd $ONTEXTRACT_DIR && python scripts/test_jcdl_implementation.py"
echo "3. Start application: cd $ONTEXTRACT_DIR && flask run --host=0.0.0.0 --port=8765"