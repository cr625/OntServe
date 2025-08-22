#!/usr/bin/env python3
"""
Import BFO (Basic Formal Ontology) into OntServe MCP database.

This script downloads BFO and imports it into the proper database schema.
"""

import os
import sys
import psycopg2
import uuid
import json
import requests
from datetime import datetime

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

def download_bfo():
    """Download BFO ontology."""
    bfo_url = "http://purl.obolibrary.org/obo/bfo.owl"
    print(f"📥 Downloading BFO from {bfo_url}")
    
    try:
        response = requests.get(bfo_url, timeout=30)
        response.raise_for_status()
        content = response.text
        print(f"✅ Downloaded BFO: {len(content)} characters")
        return content
    except Exception as e:
        print(f"❌ Failed to download BFO: {e}")
        return None

def import_bfo_to_database(conn, domain_id, content):
    """Import BFO ontology into the database."""
    cur = conn.cursor()
    
    # Check if BFO already exists
    cur.execute("SELECT id FROM ontologies WHERE domain_id = %s AND name = %s", (domain_id, "bfo"))
    existing = cur.fetchone()
    
    if existing:
        print(f"⚠️  BFO already exists. Skipping...")
        cur.close()
        return True
    
    # Insert ontology record
    cur.execute("""
        INSERT INTO ontologies (uuid, domain_id, name, base_uri, description, is_base, is_editable, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        str(uuid.uuid4()),
        domain_id,
        "bfo",
        "http://purl.obolibrary.org/obo/bfo.owl#",
        "Basic Formal Ontology (BFO) - A top-level ontology designed to support scientific research",
        True,  # is_base
        False,  # is_editable (BFO shouldn't be edited)
        json.dumps({
            'source_url': 'http://purl.obolibrary.org/obo/bfo.owl',
            'format': 'owl',
            'imported_at': datetime.now().isoformat(),
            'license': 'http://creativecommons.org/licenses/by/4.0/'
        })
    ))
    
    ontology_id = cur.fetchone()[0]
    
    # Create initial version
    cur.execute("""
        INSERT INTO ontology_versions (ontology_id, version_number, content, created_by, is_current)
        VALUES (%s, %s, %s, %s, %s)
    """, (ontology_id, 1, content, 'bfo_import_script', True))
    
    conn.commit()
    cur.close()
    print(f"✅ Imported BFO into database")
    return True

def main():
    """Import BFO ontology."""
    print("🚀 Importing BFO to OntServe Database")
    print("=" * 40)
    
    try:
        # Download BFO
        bfo_content = download_bfo()
        if not bfo_content:
            return False
        
        conn = get_db_connection()
        print("✅ Connected to OntServe database")
        
        # Ensure BFO domain exists
        bfo_domain_id = ensure_domain_exists(
            conn,
            "bfo",
            "Basic Formal Ontology",
            "http://purl.obolibrary.org/obo/bfo.owl#",
            "BFO upper-level ontology for scientific research"
        )
        
        # Import BFO
        success = import_bfo_to_database(conn, bfo_domain_id, bfo_content)
        
        conn.close()
        
        if success:
            print("\n🎉 Successfully imported BFO!")
            return True
        else:
            print("❌ BFO import failed")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)