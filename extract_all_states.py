#!/usr/bin/env python
"""
Extract all state classes and insert them into the OntServe database
"""

import psycopg2

# All the state classes we defined
state_classes = [
    # Base state class
    ("State", "State"),
    
    # Conflict States
    ("ConflictOfInterest", "Conflict of Interest State"),
    ("CompetingDuties", "Competing Duties State"),
    
    # Risk States
    ("PublicSafetyAtRisk", "Public Safety at Risk"),
    ("EnvironmentalHazard", "Environmental Hazard Present"),
    
    # Competence States
    ("OutsideCompetence", "Outside Area of Competence"),
    ("QualifiedToPerform", "Qualified to Perform"),
    
    # Relationship States
    ("ClientRelationship", "Client Relationship Established"),
    ("EmploymentTerminated", "Employment Terminated"),
    
    # Information States
    ("ConfidentialInformation", "Confidential Information Held"),
    ("PublicInformation", "Public Information Available"),
    
    # Emergency States
    ("EmergencySituation", "Emergency Situation"),
    ("CrisisConditions", "Crisis Conditions"),
    
    # Regulatory States
    ("RegulatoryCompliance", "Regulatory Compliance State"),
    ("NonCompliant", "Non-Compliant State"),
    
    # Decision States
    ("JudgmentOverruled", "Judgment Overruled"),
    ("UnderReview", "Under Review"),
    ("DecisionPending", "Decision Pending")
]

def insert_state_entities():
    """Insert all state class entities into the database"""
    
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
        
        inserted = 0
        updated = 0
        
        for local_name, label in state_classes:
            uri = f"http://proethica.org/ontology/intermediate#{local_name}"
            
            # Determine parent URI
            if local_name == "State":
                parent_uri = None  # State is the base class
            else:
                parent_uri = "http://proethica.org/ontology/intermediate#State"
            
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
                    SET label = %s, entity_type = 'class', parent_uri = %s
                    WHERE ontology_id = %s AND uri = %s
                """, (label, parent_uri, ontology_id, uri))
                updated += 1
                print(f"Updated: {label}")
            else:
                # Insert new entity
                cur.execute("""
                    INSERT INTO ontology_entities (
                        ontology_id, uri, label, entity_type, parent_uri
                    )
                    VALUES (%s, %s, %s, 'class', %s)
                """, (ontology_id, uri, label, parent_uri))
                inserted += 1
                print(f"Inserted: {label}")
        
        conn.commit()
        print(f"\nSummary: Inserted {inserted} new entities, updated {updated} existing entities")
        
        # Query all state entities to verify
        cur.execute("""
            SELECT label, uri 
            FROM ontology_entities 
            WHERE ontology_id = %s 
            AND (uri LIKE '%#State' OR parent_uri = 'http://proethica.org/ontology/intermediate#State')
            ORDER BY label
        """)
        
        state_entities = cur.fetchall()
        print(f"\nAll state entities in database ({len(state_entities)} total):")
        for label, uri in state_entities:
            local_name = uri.split('#')[-1]
            print(f"  - {label} ({local_name})")
        
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    insert_state_entities()