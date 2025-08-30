#!/bin/bash

# OntServe Database Backup Script
# Creates a timestamped backup of the PostgreSQL database

# Configuration
DB_HOST="localhost"
DB_PORT="5432"
DB_NAME="ontserve"
DB_USER="ontserve_user"
BACKUP_DIR="/home/chris/onto/OntServe/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/ontserve_backup_${TIMESTAMP}.sql"

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

echo "🔄 Creating OntServe database backup..."
echo "📁 Backup directory: $BACKUP_DIR"
echo "📄 Backup file: ontserve_backup_${TIMESTAMP}.sql"

# Set password environment variable
export PGPASSWORD="ontserve_development_password"

# Create the backup
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    --verbose \
    --no-owner \
    --no-privileges \
    --format=plain \
    --file="$BACKUP_FILE"

# Check if backup was successful
if [ $? -eq 0 ]; then
    echo "✅ Database backup completed successfully!"
    echo "📄 Backup saved to: $BACKUP_FILE"
    
    # Get backup file size
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "📊 Backup size: $BACKUP_SIZE"
    
    # Count lines in backup (rough indicator of data size)
    LINE_COUNT=$(wc -l < "$BACKUP_FILE")
    echo "📝 Backup contains $LINE_COUNT lines"
    
    # Create a latest symlink for easy access
    LATEST_LINK="${BACKUP_DIR}/ontserve_backup_latest.sql"
    ln -sf "ontserve_backup_${TIMESTAMP}.sql" "$LATEST_LINK"
    echo "🔗 Latest backup symlink: $LATEST_LINK"
    
    # Show recent backups
    echo ""
    echo "📋 Recent backups in $BACKUP_DIR:"
    ls -lah "$BACKUP_DIR"/*.sql | tail -5
    
else
    echo "❌ Database backup failed!"
    exit 1
fi