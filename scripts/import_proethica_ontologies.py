#!/usr/bin/env python3
"""
Import ProEthica ontologies into OntServe MCP database.

This script imports both engineering-ethics.ttl and proethica-intermediate.ttl
ontologies into the OntServe database using the MCP server schema with proper
domains and concept management.
"""

import os
import sys
import psycopg2
import psycopg2.extras
import uuid
import json
from pathlib import Path
from datetime import datetime

# Set up database connection
def get_db_connection():
    return psycopg2.connect(
        host='localhost',
        port=5435,
        database='ontserve',
        user='ontserve_user',
        password='ontserve_development_password'
    )

def ensure_domain_exists(conn, domain_name, display_name, namespace_uri, description):
    """Ensure the domain exists and return its ID."""
    cur = conn.cursor()
    
    # Check if domain exists
    cur.execute("SELECT id FROM domains WHERE name = %s", (domain_name,))
    result = cur.fetchone()
    
    if result:
        cur.close()
        return result[0]
    
    # Create domain
    cur.execute("""
        INSERT INTO domains (uuid, name, display_name, namespace_uri, description, is_active)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (str(uuid.uuid4()), domain_name, display_name, namespace_uri, description, True))
    
    domain_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    print(f"✅ Created domain: {domain_name}")
    return domain_id

def import_ontology_to_database(conn, domain_id, ontology_name, ontology_path, description):
    """Import ontology file into the database."""
    cur = conn.cursor()
    
    # Read ontology content
    if not os.path.exists(ontology_path):
        print(f"❌ File not found: {ontology_path}")
        return False
    
    with open(ontology_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"✅ Read {ontology_name}: {len(content)} characters")
    
    # Check if ontology already exists
    cur.execute("SELECT id FROM ontologies WHERE domain_id = %s AND name = %s", (domain_id, ontology_name))
    existing = cur.fetchone()
    
    if existing:
        print(f"⚠️  Ontology '{ontology_name}' already exists. Skipping...")
        cur.close()
        return True
    
    # Create base URI from the ontology name
    base_uri = f"http://proethica.org/ontology/{ontology_name.replace('-', '_')}#"
    
    # Insert ontology record
    cur.execute("""
        INSERT INTO ontologies (uuid, domain_id, name, base_uri, description, is_base, is_editable, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        str(uuid.uuid4()),
        domain_id,
        ontology_name,
        base_uri,
        description,
        True,  # is_base
        True,  # is_editable
        json.dumps({
            'imported_from': ontology_path,
            'format': 'turtle',
            'imported_at': datetime.now().isoformat()
        })
    ))
    
    ontology_id = cur.fetchone()[0]
    
    # Create initial version
    cur.execute("""
        INSERT INTO ontology_versions (ontology_id, version_number, content, created_by, is_current)
        VALUES (%s, %s, %s, %s, %s)
    """, (ontology_id, 1, content, 'import_script', True))
    
    conn.commit()
    cur.close()
    print(f"✅ Imported {ontology_name} into database")
    return True

def main():
    """Import ProEthica ontologies."""
    print("🚀 Importing ProEthica Ontologies to OntServe Database")
    print("=" * 60)
    
    # Paths to ProEthica ontologies
    proethica_base = "/home/chris/onto/proethica/ontologies"
    engineering_ethics_path = os.path.join(proethica_base, "engineering-ethics.ttl")
    proethica_intermediate_path = os.path.join(proethica_base, "proethica-intermediate.ttl")
    
    try:
        conn = get_db_connection()
        print("✅ Connected to OntServe database")
        
        # Ensure engineering-ethics domain exists
        engineering_domain_id = ensure_domain_exists(
            conn,
            "engineering-ethics",
            "Engineering Ethics",
            "http://proethica.org/ontology/engineering_ethics#",
            "Professional engineering ethics domain based on NSPE Code of Ethics"
        )
        
        # Import engineering-ethics.ttl
        success1 = import_ontology_to_database(
            conn,
            engineering_domain_id,
            "engineering-ethics",
            engineering_ethics_path,
            "Domain-specific ontology for engineering ethics based on NSPE Code of Ethics and ISO standards"
        )
        
        # Import proethica-intermediate.ttl to the same domain
        success2 = import_ontology_to_database(
            conn,
            engineering_domain_id,
            "proethica-intermediate",
            proethica_intermediate_path,
            "Intermediate ontology connecting BFO upper-level concepts to engineering ethics domain"
        )
        
        conn.close()
        
        if success1 and success2:
            print("\n🎉 Successfully imported all ProEthica ontologies!")
            print("   - engineering-ethics.ttl")
            print("   - proethica-intermediate.ttl")
            return True
        else:
            print("❌ Some imports failed")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)