#!/usr/bin/env python3
"""
Migrate concepts from the MCP concepts table to the ontology_entities table for web interface visualization.

This script converts concepts that were imported via the MCP server into entities
that can be visualized in the web interface.
"""

import os
import sys
import json
import psycopg2
import logging
from pathlib import Path
from typing import Dict, List, Tuple

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ConceptToEntityMigrator:
    """Migrates concepts from MCP schema to web interface schema."""
    
    def __init__(self, db_url: str):
        """Initialize the migrator."""
        self.db_url = db_url
        self.conn = None
        
    def connect(self):
        """Connect to the database."""
        try:
            self.conn = psycopg2.connect(self.db_url)
            self.conn.autocommit = False
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
            
    def disconnect(self):
        """Disconnect from the database."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
    
    def get_ontology_mapping(self) -> Dict[str, int]:
        """Get mapping of domain names to ontology IDs."""
        cur = self.conn.cursor()
        
        # Get or create ontologies for each domain
        cur.execute("""
            SELECT d.name, d.id, o.id as ontology_id 
            FROM domains d 
            LEFT JOIN ontologies o ON d.id = o.domain_id
        """)
        
        mapping = {}
        for domain_name, domain_id, ontology_id in cur.fetchall():
            if ontology_id is None:
                # Create ontology for this domain
                logger.info(f"Creating ontology for domain: {domain_name}")
                cur.execute("""
                    INSERT INTO ontologies (domain_id, name, base_uri, description, is_base, is_editable)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    domain_id, 
                    domain_name,
                    f"http://www.w3.org/ns/{domain_name}#",
                    f"Base ontology for {domain_name}",
                    True,
                    False
                ))
                ontology_id = cur.fetchone()[0]
                self.conn.commit()
                logger.info(f"Created ontology with ID: {ontology_id}")
                
            mapping[domain_name] = ontology_id
            
        cur.close()
        return mapping
    
    def map_concept_type(self, primary_type: str, uri: str, label: str) -> str:
        """Map concept primary_type to entity_type."""
        # Analyze the URI and label to determine the correct entity type
        if 'Class' in label or any(word in uri.lower() for word in ['class', 'type', 'concept']):
            return 'class'
        elif 'Property' in label or any(word in uri.lower() for word in ['property', 'relation', 'predicate']):
            return 'property'
        elif primary_type == 'Resource':
            # Default Resources to classes unless they seem like properties
            if any(word in label.lower() for word in ['property', 'relation', 'has', 'is', 'was', 'were']):
                return 'property'
            return 'class'
        elif primary_type == 'Action':
            # Actions are typically properties/predicates
            return 'property'
        elif primary_type == 'State':
            # States could be individuals/instances
            return 'individual'
        else:
            # Default fallback
            return 'class'
    
    def migrate_concepts_for_domain(self, domain_name: str, ontology_id: int) -> int:
        """Migrate concepts for a specific domain to entities."""
        cur = self.conn.cursor()
        
        # Get all concepts for this domain
        cur.execute("""
            SELECT c.uri, c.label, c.primary_type, c.description
            FROM concepts c
            JOIN domains d ON c.domain_id = d.id
            WHERE d.name = %s AND c.status = 'approved'
        """, (domain_name,))
        
        concepts = cur.fetchall()
        logger.info(f"Found {len(concepts)} approved concepts for domain: {domain_name}")
        
        migrated_count = 0
        
        for uri, label, primary_type, description in concepts:
            # Check if entity already exists
            cur.execute("""
                SELECT id FROM ontology_entities 
                WHERE ontology_id = %s AND uri = %s
            """, (ontology_id, uri))
            
            if cur.fetchone():
                logger.debug(f"Entity already exists for URI: {uri}")
                continue
                
            # Map concept type to entity type
            entity_type = self.map_concept_type(primary_type, uri, label or '')
            
            # Extract comment from description
            comment = description[:500] if description else None
            
            # Insert into ontology_entities table
            try:
                cur.execute("""
                    INSERT INTO ontology_entities 
                    (ontology_id, entity_type, uri, label, comment, properties)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    ontology_id,
                    entity_type,
                    uri,
                    label,
                    comment,
                    json.dumps({})  # Convert empty dict to JSON string
                ))
                migrated_count += 1
                logger.debug(f"Migrated {entity_type}: {uri}")
                
            except Exception as e:
                logger.error(f"Failed to migrate concept {uri}: {e}")
                continue
        
        self.conn.commit()
        logger.info(f"Migrated {migrated_count} concepts to entities for domain: {domain_name}")
        cur.close()
        return migrated_count
    
    def migrate_all_concepts(self) -> Dict[str, int]:
        """Migrate all concepts to entities."""
        logger.info("Starting concept to entity migration...")
        
        # Get ontology mapping
        ontology_mapping = self.get_ontology_mapping()
        
        results = {}
        total_migrated = 0
        
        for domain_name, ontology_id in ontology_mapping.items():
            logger.info(f"Migrating concepts for domain: {domain_name}")
            count = self.migrate_concepts_for_domain(domain_name, ontology_id)
            results[domain_name] = count
            total_migrated += count
        
        logger.info(f"Migration complete. Total entities created: {total_migrated}")
        return results
    
    def create_version_for_ontology(self, ontology_id: int, domain_name: str):
        """Create a version entry for the ontology."""
        cur = self.conn.cursor()
        
        # Check if version already exists
        cur.execute("""
            SELECT id FROM ontology_versions 
            WHERE ontology_id = %s AND is_current = true
        """, (ontology_id,))
        
        if cur.fetchone():
            logger.info(f"Version already exists for ontology {ontology_id}")
            cur.close()
            return
        
        # Create a basic version with placeholder content
        placeholder_content = f"""@prefix {domain_name}: <http://www.w3.org/ns/{domain_name}#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

# {domain_name.upper()} Ontology - Migrated from concepts
# This version was automatically created from MCP concept data
"""
        
        cur.execute("""
            INSERT INTO ontology_versions 
            (ontology_id, version_number, content, change_summary, created_by, is_current)
            VALUES (%s, 1, %s, %s, %s, true)
        """, (
            ontology_id,
            placeholder_content,
            f"Initial version created from {domain_name} concepts migration",
            "system-migration"
        ))
        
        self.conn.commit()
        cur.close()
        logger.info(f"Created version for ontology {ontology_id}")

def main():
    """Main function."""
    # Get database URL from environment
    db_url = os.environ.get(
        'ONTSERVE_DB_URL',
        'postgresql://ontserve_user:ontserve_development_password@localhost:5432/ontserve'
    )
    
    migrator = ConceptToEntityMigrator(db_url)
    
    try:
        migrator.connect()
        
        # Migrate all concepts to entities
        results = migrator.migrate_all_concepts()
        
        # Create versions for ontologies that need them
        ontology_mapping = migrator.get_ontology_mapping()
        for domain_name, ontology_id in ontology_mapping.items():
            migrator.create_version_for_ontology(ontology_id, domain_name)
        
        print("\nMigration Results:")
        for domain, count in results.items():
            print(f"  {domain}: {count} entities created")
        
        print(f"\nTotal entities migrated: {sum(results.values())}")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        migrator.disconnect()

if __name__ == "__main__":
    main()