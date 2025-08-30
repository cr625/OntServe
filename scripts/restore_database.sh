#!/bin/bash

# OntServe Database Restore Script
# Restores from a timestamped backup file

# Configuration
DB_HOST="localhost"
DB_PORT="5432"
DB_NAME="ontserve"
DB_USER="ontserve_user"
BACKUP_DIR="/home/chris/onto/OntServe/backups"

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

# Set password environment variable
export PGPASSWORD="ontserve_development_password"

echo ""
echo "🗑️  Dropping and recreating database..."
# Drop database (disconnect all users first)
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "
    SELECT pg_terminate_backend(pid) 
    FROM pg_stat_activity 
    WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();
"

# Drop and recreate database
dropdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"
createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"

echo "📥 Restoring database from backup..."
# Restore the backup
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" < "$BACKUP_FILE"

# Check if restore was successful
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Database restore completed successfully!"
    
    # Get some basic stats
    echo ""
    echo "📊 Restored database statistics:"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "
        SELECT schemaname, tablename, n_tup_ins as rows 
        FROM pg_stat_user_tables 
        WHERE n_tup_ins > 0
        ORDER BY n_tup_ins DESC;
    "
else
    echo "❌ Database restore failed!"
    exit 1
fi