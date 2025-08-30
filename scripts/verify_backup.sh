#!/bin/bash

# OntServe Database Backup Verification Script
# Verifies backup integrity and content

BACKUP_DIR="/home/chris/onto/OntServe/backups"

if [ $# -eq 0 ]; then
    echo "Usage: $0 <backup_file|latest>"
    exit 1
fi

# Handle 'latest' option
if [ "$1" == "latest" ]; then
    BACKUP_FILE="${BACKUP_DIR}/ontserve_backup_latest.sql"
else
    BACKUP_FILE="$1"
    # If relative path, assume it's in backup directory
    if [[ "$BACKUP_FILE" != /* ]]; then
        BACKUP_FILE="${BACKUP_DIR}/${BACKUP_FILE}"
    fi
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "🔍 Verifying OntServe database backup..."
echo "📄 Backup file: $BACKUP_FILE"
echo ""

# Basic file information
echo "📊 File Information:"
echo "  Size: $(du -h "$BACKUP_FILE" | cut -f1)"
echo "  Lines: $(wc -l < "$BACKUP_FILE")"
echo "  Created: $(stat -c %y "$BACKUP_FILE")"
echo ""

# Check backup format and structure
echo "🔧 Backup Structure:"
echo "  PostgreSQL dump: $(grep -c "PostgreSQL database dump" "$BACKUP_FILE")"
echo "  Extensions: $(grep -c "CREATE EXTENSION" "$BACKUP_FILE")"
echo "  Tables: $(grep -c "CREATE TABLE" "$BACKUP_FILE")"
echo "  Indexes: $(grep -c "CREATE INDEX" "$BACKUP_FILE")"
echo "  Views: $(grep -c "CREATE VIEW" "$BACKUP_FILE")"
echo "  Functions: $(grep -c "CREATE FUNCTION" "$BACKUP_FILE")"
echo "  Triggers: $(grep -c "CREATE TRIGGER" "$BACKUP_FILE")"
echo ""

# Check data content
echo "📋 Data Content:"
echo "  Data tables: $(grep -c "COPY public\." "$BACKUP_FILE")"
echo "  Ontologies: $(grep -A 1000 "COPY public.ontologies" "$BACKUP_FILE" | grep -E "^[0-9]" | wc -l)"
echo "  Entities: $(grep -A 1000 "COPY public.ontology_entities" "$BACKUP_FILE" | grep -E "^[0-9]" | wc -l)"
echo "  Versions: $(grep -A 1000 "COPY public.ontology_versions" "$BACKUP_FILE" | grep -E "^[0-9]" | wc -l)"
echo "  Concepts: $(grep -A 1000 "COPY public.concepts" "$BACKUP_FILE" | grep -E "^[0-9]" | wc -l)"
echo ""

# Check for key ontologies
echo "🔍 Key Ontologies Found:"
if grep -q "proethica-intermediate" "$BACKUP_FILE"; then
    echo "  ✅ proethica-intermediate"
else
    echo "  ❌ proethica-intermediate MISSING"
fi

if grep -q "engineering-ethics" "$BACKUP_FILE"; then
    echo "  ✅ engineering-ethics"
else
    echo "  ❌ engineering-ethics MISSING"
fi

if grep -q "Basic Formal Ontology" "$BACKUP_FILE"; then
    echo "  ✅ Basic Formal Ontology (BFO)"
else
    echo "  ❌ Basic Formal Ontology (BFO) MISSING"
fi

# Check backup completeness
echo ""
echo "✅ Backup Integrity Check:"
if grep -q "PostgreSQL database dump completed" "$BACKUP_FILE" || grep -q "\-\- Completed on" "$BACKUP_FILE"; then
    echo "  ✅ Backup appears complete"
else
    echo "  ⚠️  Backup completion status unclear"
fi

# Check for obvious corruption
if grep -q "ERROR\|FATAL\|pg_dump: error" "$BACKUP_FILE"; then
    echo "  ❌ Errors found in backup"
else
    echo "  ✅ No obvious errors detected"
fi

echo ""
echo "🎯 Backup verification complete!"
echo ""
echo "💡 To restore this backup:"
echo "   ./scripts/restore_database.sh $(basename "$BACKUP_FILE")"