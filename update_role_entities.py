#!/usr/bin/env python
"""
Update proethica-intermediate with new role subclasses and refresh entities
"""

import psycopg2
import re

def update_role_entities():
    """Update role entities in the database"""
    
    # Read the updated TTL file
    ttl_path = '/home/chris/onto/OntServe/ontologies/proethica-intermediate.ttl'
    with open(ttl_path, 'r') as f:
        ttl_content = f.read()
    
    # Connect to database
    conn = psycopg2.connect(
        host='localhost',
        database='ontserve',
        user='postgres',
        password='PASS'
    )
    
    try:
        cur = conn.cursor()
        
        # Get ontology ID
        cur.execute("SELECT id FROM ontologies WHERE name = 'proethica-intermediate'")
        result = cur.fetchone()
        if not result:
            print("ERROR: proethica-intermediate ontology not found")
            return
        
        ontology_id = result[0]
        print(f"Found ontology ID: {ontology_id}")
        
        # Update current version with new content
        cur.execute("""
            UPDATE ontology_versions 
            SET content = %s,
                change_summary = 'Added 4 professional role categories from Chapter 2.2.1 literature'
            WHERE ontology_id = %s AND is_current = true
        """, (ttl_content, ontology_id))
        
        print("Updated ontology content")
        
        # Define the new role entities to add
        new_roles = [
            ("ProviderClientRole", "Provider-Client Role"),
            ("ProfessionalPeerRole", "Professional Peer Role"),
            ("EmployerRelationshipRole", "Employer Relationship Role"),
            ("PublicResponsibilityRole", "Public Responsibility Role")
        ]
        
        # Insert new role entities
        inserted = 0
        for local_name, label in new_roles:
            uri = f"http://proethica.org/ontology/intermediate#{local_name}"
            parent_uri = "http://proethica.org/ontology/intermediate#ProfessionalRole"
            
            # Check if entity exists
            cur.execute("""
                SELECT id FROM ontology_entities 
                WHERE ontology_id = %s AND uri = %s
            """, (ontology_id, uri))
            
            existing = cur.fetchone()
            
            if not existing:
                # Insert new entity
                cur.execute("""
                    INSERT INTO ontology_entities (
                        ontology_id, uri, label, entity_type, parent_uri
                    )
                    VALUES (%s, %s, %s, 'class', %s)
                """, (ontology_id, uri, label, parent_uri))
                inserted += 1
                print(f"Inserted: {label}")
            else:
                print(f"Already exists: {label}")
        
        conn.commit()
        print(f"\nSummary: Inserted {inserted} new role entities")
        
        # Query all role entities to verify hierarchy
        cur.execute("""
            SELECT label, uri, parent_uri
            FROM ontology_entities 
            WHERE ontology_id = %s 
            AND (label ILIKE '%role%' OR uri LIKE '%Role')
            ORDER BY 
                CASE 
                    WHEN parent_uri IS NULL THEN 0
                    WHEN parent_uri LIKE '%#Role' THEN 1
                    ELSE 2
                END,
                label
        """)
        
        role_entities = cur.fetchall()
        print(f"\nRole hierarchy ({len(role_entities)} total):")
        
        # Build hierarchy display
        hierarchy = {}
        for label, uri, parent_uri in role_entities:
            local_name = uri.split('#')[-1]
            if parent_uri:
                parent_name = parent_uri.split('#')[-1]
            else:
                parent_name = None
            
            if parent_name is None:
                print(f"• {label} ({local_name})")
            elif parent_name == "Role":
                print(f"  ├─ {label} ({local_name})")
                hierarchy[local_name] = []
            elif parent_name in hierarchy:
                print(f"    └─ {label} ({local_name})")
                hierarchy[parent_name].append(local_name)
        
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    update_role_entities()