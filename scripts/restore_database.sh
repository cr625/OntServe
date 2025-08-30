#!/bin/bash

# OntServe Database Restore Script
# Restores from a backup file using simple psql

# Configuration - Updated for server deployment
if [ -d "/opt/ontserve" ]; then
    # Server deployment path
    BACKUP_DIR="/opt/ontserve/backups"
else
    # Development path
    BACKUP_DIR="/home/chris/onto/OntServe/backups"
fi

DB_HOST="localhost"
DB_PORT="5432"
DB_NAME="ontserve"
DB_USER="ontserve_user"
DB_PASSWORD="ontserve_development_password"

# Check if backup file is provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <backup_file>"
    echo "Available backups:"
    ls -lah "$BACKUP_DIR"/*.sql 2>/dev/null | tail -5
    echo ""
    echo "Or use 'latest' to restore from the most recent backup:"
    echo "  $0 latest"
    exit 1
fi

# Handle 'latest' option
if [ "$1" == "latest" ]; then
    BACKUP_FILE="${BACKUP_DIR}/ontserve_backup_latest.sql"
    if [ ! -f "$BACKUP_FILE" ]; then
        echo "❌ No latest backup found at $BACKUP_FILE"
        exit 1
    fi
else
    BACKUP_FILE="$1"
    # If relative path, assume it's in backup directory
    if [[ "$BACKUP_FILE" != /* ]]; then
        BACKUP_FILE="${BACKUP_DIR}/${BACKUP_FILE}"
    fi
fi

# Verify backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "🔄 Restoring OntServe database..."
echo "📄 Backup file: $BACKUP_FILE"
echo ""
echo "⚠️  WARNING: This will completely replace the current database!"
echo "   Current data will be lost permanently."
echo ""
read -p "Are you sure you want to continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "❌ Restore cancelled."
    exit 1
fi

echo ""
echo "📥 Restoring database from backup using psql..."

# Use simple psql with password embedded in connection string
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" < "$BACKUP_FILE"

# Check if restore was successful
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Database restore completed successfully!"
    
    # Get some basic stats
    echo ""
    echo "📊 Restored database statistics:"
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT COUNT(*) as total_tables FROM information_schema.tables WHERE table_schema = 'public';"
else
    echo "❌ Database restore failed!"
    exit 1
fi