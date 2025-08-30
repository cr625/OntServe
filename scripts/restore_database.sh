#!/bin/bash

# OntServe Database Restore Script
# Restores from a backup file with improved error handling and permissions

# Configuration - Updated for server deployment
if [ -d "/opt/ontserve" ]; then
    # Server deployment path
    BACKUP_DIR="/opt/ontserve/backups"
    DATA_BACKUP_DIR="/opt/ontserve/data"
    USE_SUDO_POSTGRES=true  # Production uses sudo -u postgres
else
    # Development path
    BACKUP_DIR="/home/chris/onto/OntServe/backups"
    DATA_BACKUP_DIR="/home/chris/onto/OntServe/data"
    USE_SUDO_POSTGRES=false
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
    echo ""
    echo "SQL backups in $BACKUP_DIR:"
    ls -lah "$BACKUP_DIR"/*.sql 2>/dev/null | tail -5
    echo ""
    echo "Dump backups in $DATA_BACKUP_DIR:"
    ls -lah "$DATA_BACKUP_DIR"/*.dump 2>/dev/null | tail -5
    echo ""
    echo "Or use 'latest' to restore from the most recent backup:"
    echo "  $0 latest"
    exit 1
fi

# Handle 'latest' option - check multiple locations
if [ "$1" == "latest" ]; then
    # First try the standard backup location
    BACKUP_FILE="${BACKUP_DIR}/ontserve_backup_latest.sql"
    if [ ! -f "$BACKUP_FILE" ]; then
        # Try finding the most recent .dump file in data directory
        LATEST_DUMP=$(find "$DATA_BACKUP_DIR" -name "*.dump" -type f -exec ls -t {} + 2>/dev/null | head -n1)
        if [ -n "$LATEST_DUMP" ]; then
            BACKUP_FILE="$LATEST_DUMP"
            echo "📄 Using latest dump file: $BACKUP_FILE"
        else
            echo "❌ No latest backup found in $BACKUP_DIR or $DATA_BACKUP_DIR"
            exit 1
        fi
    fi
else
    BACKUP_FILE="$1"
    # If relative path, check multiple directories
    if [[ "$BACKUP_FILE" != /* ]]; then
        if [ -f "${BACKUP_DIR}/${BACKUP_FILE}" ]; then
            BACKUP_FILE="${BACKUP_DIR}/${BACKUP_FILE}"
        elif [ -f "${DATA_BACKUP_DIR}/${BACKUP_FILE}" ]; then
            BACKUP_FILE="${DATA_BACKUP_DIR}/${BACKUP_FILE}"
        fi
    fi
fi

# Verify backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Detect backup format
BACKUP_FORMAT=""
if [[ "$BACKUP_FILE" == *.sql ]]; then
    BACKUP_FORMAT="sql"
elif [[ "$BACKUP_FILE" == *.dump ]]; then
    BACKUP_FORMAT="dump"
else
    echo "⚠️  Warning: Unknown backup format. Assuming SQL format."
    BACKUP_FORMAT="sql"
fi

echo "🔄 Restoring OntServe database..."
echo "📄 Backup file: $BACKUP_FILE"
echo "📋 Backup format: $BACKUP_FORMAT"
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
echo "🧹 Cleaning database schema to avoid conflicts..."

# Clean schema first to avoid conflicts
if [ "$USE_SUDO_POSTGRES" = true ]; then
    sudo -u postgres psql -d "$DB_NAME" -c "DROP SCHEMA public CASCADE;" >/dev/null 2>&1
    sudo -u postgres psql -d "$DB_NAME" -c "CREATE SCHEMA public;" >/dev/null 2>&1
else
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "DROP SCHEMA public CASCADE;" >/dev/null 2>&1
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "CREATE SCHEMA public;" >/dev/null 2>&1
fi

echo "📥 Restoring database from backup..."

# Restore based on format and authentication method
RESTORE_SUCCESS=false
if [ "$USE_SUDO_POSTGRES" = true ]; then
    if [ "$BACKUP_FORMAT" = "dump" ]; then
        echo "Using pg_restore with sudo..."
        if sudo -u postgres pg_restore --clean --no-owner --verbose --dbname="$DB_NAME" "$BACKUP_FILE" >/dev/null 2>&1; then
            RESTORE_SUCCESS=true
        fi
    else
        echo "Using psql with sudo..."
        if sudo -u postgres psql -d "$DB_NAME" < "$BACKUP_FILE" >/dev/null 2>&1; then
            RESTORE_SUCCESS=true
        fi
    fi
else
    if [ "$BACKUP_FORMAT" = "dump" ]; then
        echo "Using pg_restore with password..."
        if PGPASSWORD="$DB_PASSWORD" pg_restore --clean --no-owner --verbose -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" --dbname="$DB_NAME" "$BACKUP_FILE" >/dev/null 2>&1; then
            RESTORE_SUCCESS=true
        fi
    else
        echo "Using psql with password..."
        if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" < "$BACKUP_FILE" >/dev/null 2>&1; then
            RESTORE_SUCCESS=true
        fi
    fi
fi

# Check if restore was successful
if [ "$RESTORE_SUCCESS" = true ]; then
    echo ""
    echo "🔐 Setting up database permissions..."
    
    # Grant permissions to ontserve_user
    if [ "$USE_SUDO_POSTGRES" = true ]; then
        sudo -u postgres psql -d "$DB_NAME" -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO $DB_USER;" >/dev/null 2>&1
        sudo -u postgres psql -d "$DB_NAME" -c "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO $DB_USER;" >/dev/null 2>&1
    else
        # In development, this might not be needed, but include for completeness
        PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -d "$DB_NAME" -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO $DB_USER;" >/dev/null 2>&1
        PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -d "$DB_NAME" -c "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO $DB_USER;" >/dev/null 2>&1
    fi
    
    echo "✅ Database restore completed successfully!"
    
    # Get some basic stats
    echo ""
    echo "📊 Restored database statistics:"
    if [ "$USE_SUDO_POSTGRES" = true ]; then
        sudo -u postgres psql -d "$DB_NAME" -c "SELECT COUNT(*) as total_tables FROM information_schema.tables WHERE table_schema = 'public';"
        echo ""
        echo "🔄 Restarting OntServe services..."
        if systemctl is-active --quiet ontserve-mcp && systemctl is-active --quiet ontserve-web; then
            sudo systemctl restart ontserve-mcp ontserve-web
            echo "✅ Services restarted successfully!"
            echo ""
            echo "🌐 OntServe should be available at: https://ontserve.ontorealm.net/"
        else
            echo "⚠️  Some services may not be running. Check with: sudo systemctl status ontserve-mcp ontserve-web"
        fi
    else
        PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT COUNT(*) as total_tables FROM information_schema.tables WHERE table_schema = 'public';"
    fi
else
    echo "❌ Database restore failed!"
    echo "💡 Try running with verbose output to see detailed error messages."
    exit 1
fi