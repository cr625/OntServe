#!/usr/bin/env python
"""
Update proethica-intermediate ontology with new state classes
"""

import sys
import os
import psycopg2
from psycopg2 import sql
import json

def update_ontology():
    """Update proethica-intermediate ontology with new state classes"""
    
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
        
        # Update current version to not current
        cur.execute("""
            UPDATE ontology_versions 
            SET is_current = false 
            WHERE ontology_id = %s AND is_current = true
        """, (ontology_id,))
        
        # Create new version
        cur.execute("""
            INSERT INTO ontology_versions (
                ontology_id, version_number, version_tag, content, 
                change_summary, created_by, is_current, is_draft, workflow_status
            )
            VALUES (%s, 14, 'v14.0.0-state-classes', %s, 
                    'Added 18 state classes based on Chapter 2.2.4 literature review', 
                    'system', true, false, 'published')
            RETURNING id
        """, (ontology_id, ttl_content))
        
        new_version_id = cur.fetchone()[0]
        print(f"Created new version ID: {new_version_id}")
        
        # Extract and store state entities from TTL
        import re
        
        # Clear existing entities for this ontology
        cur.execute("DELETE FROM ontology_entities WHERE ontology_id = %s", (ontology_id,))
        
        # Extract all class definitions
        class_pattern = r':(\w+)\s+(?:a|rdf:type)\s+owl:Class\s*;[^.]*?rdfs:label\s+"([^"]+)"'
        matches = re.findall(class_pattern, ttl_content, re.DOTALL)
        
        entity_count = 0
        state_count = 0
        
        for local_name, label in matches:
            uri = f"http://proethica.org/ontology/intermediate#{local_name}"
            
            # Check if it's a state class
            is_state = 'State' in local_name or 'state' in label.lower()
            if is_state:
                state_count += 1
            
            # Check if entity exists
            cur.execute("""
                SELECT id FROM ontology_entities 
                WHERE ontology_id = %s AND uri = %s
            """, (ontology_id, uri))
            
            existing = cur.fetchone()
            
            if existing:
                # Update existing entity
                cur.execute("""
                    UPDATE ontology_entities 
                    SET label = %s, entity_type = 'class',
                        parent_uri = CASE WHEN %s THEN 'http://proethica.org/ontology/intermediate#State' ELSE parent_uri END
                    WHERE ontology_id = %s AND uri = %s
                """, (label, is_state and local_name != 'State', ontology_id, uri))
            else:
                # Insert new entity
                cur.execute("""
                    INSERT INTO ontology_entities (
                        ontology_id, uri, label, entity_type, parent_uri
                    )
                    VALUES (%s, %s, %s, 'class', 
                            CASE WHEN %s THEN 'http://proethica.org/ontology/intermediate#State' ELSE NULL END)
                """, (ontology_id, uri, label, is_state and local_name != 'State'))
            
            entity_count += 1
        
        print(f"Extracted {entity_count} entities total, including {state_count} state-related entities")
        
        # Commit changes
        conn.commit()
        print("Successfully updated proethica-intermediate ontology")
        
        # Query and display state entities
        cur.execute("""
            SELECT uri, label 
            FROM ontology_entities 
            WHERE ontology_id = %s 
            AND (label ILIKE '%state%' OR parent_uri = 'http://proethica.org/ontology/intermediate#State')
            ORDER BY label
        """)
        
        state_entities = cur.fetchall()
        print(f"\nState entities in database ({len(state_entities)} total):")
        for uri, label in state_entities:
            print(f"  - {label}: {uri}")
        
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    update_ontology()