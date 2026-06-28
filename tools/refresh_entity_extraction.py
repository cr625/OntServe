#!/usr/bin/env python3
"""
Refresh entity extraction from ontology content.

This script re-extracts entities from the current ontology versions
and updates the ontology_entities table. Specifically designed to refresh
MCP server entity queries after ontology updates.
"""

import sys
import os
from pathlib import Path

# Set up paths BEFORE any other imports
# This needs careful ordering to avoid conflicts between config/ directory and config.py module
# (script lives at OntServe/tools/, so the OntServe root is one level up -- matching
# populate_entity_embeddings.py. The prior `.parent.parent` resolved to /home/chris/onto,
# which made run_cleanup's extended-refresh a silent no-op behind subprocess.run.)
script_dir = Path(__file__).parent
ontserve_root = script_dir.parent
web_dir = ontserve_root / 'web'

# Add OntServe root first (for config/ package), then web dir (for models)
# The web/config.py module will handle its own imports from config/
if str(ontserve_root) not in sys.path:
    sys.path.insert(0, str(ontserve_root))
if str(web_dir) not in sys.path:
    sys.path.insert(0, str(web_dir))

import hashlib
import logging
import rdflib
from rdflib import RDF, RDFS, OWL
from rdflib.namespace import SKOS, DCTERMS
from datetime import datetime, timezone

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROETHICA_NS = 'http://proethica.org/ontology/'


def _compute_content_hash(uri: str, label: str = None, comment: str = None) -> str:
    """Compute SHA-256 content hash for entity version tracking.

    Must match OntologyEntity.compute_content_hash in web/models.py
    and the equivalent function in ProEthica's TemporaryRDFStorage.
    """
    raw = f"{uri}|{label or ''}|{comment or ''}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()
PROETHICA_INTERMEDIATE_NS = 'http://proethica.org/ontology/intermediate#'
PROETHICA_CORE_NS = 'http://proethica.org/ontology/core#'


def _pick_best_parent(g, class_uri):
    """Select the best rdfs:subClassOf parent for this class.

    Priority: proethica intermediate > proethica core > other proethica URI >
    any named (BFO/IAO/OBO) superclass. The proethica-first ordering keeps the
    category-walk CTEs terminating at the proethica boundary; the named-parent
    fallback lets a core class (whose only named parent is BFO) root in the BFO
    tree for the entity-page Class Hierarchy. Blank-node restrictions are
    excluded. Returns a URI string or None.
    """
    all_parents = [str(p) for p in g.objects(class_uri, RDFS.subClassOf)]
    if not all_parents:
        return None

    intermediate = [p for p in all_parents if p.startswith(PROETHICA_INTERMEDIATE_NS)]
    core = [p for p in all_parents if p.startswith(PROETHICA_CORE_NS)]
    other_proethica = [p for p in all_parents if p.startswith(PROETHICA_NS)
                       and p not in intermediate and p not in core]

    if intermediate:
        return intermediate[0]
    if core:
        return core[0]
    if other_proethica:
        return other_proethica[0]
    # No proethica-namespace parent: fall back to the true named superclass
    # (BFO/IAO/OBO) so the entity-page Class Hierarchy can root a core class in
    # the BFO tree. Category-walk CTEs are unaffected -- they match the category
    # in the core class's own URI and terminate at the core class, which sits
    # below these upper parents. Blank-node restrictions (str not http) excluded.
    named = [p for p in all_parents if p.startswith('http')]
    return named[0] if named else None


def refresh_ontology_entities(ontology_name: str = "proethica-intermediate"):
    """Refresh entity extraction for specified ontology."""

    from flask import Flask
    # Import config module explicitly from web directory
    import importlib.util
    config_spec = importlib.util.spec_from_file_location("web_config", str(web_dir / "app_config.py"))
    web_config_module = importlib.util.module_from_spec(config_spec)
    config_spec.loader.exec_module(web_config_module)
    config = web_config_module.config

    from models import db, Ontology, OntologyVersion, OntologyEntity
    
    # Create Flask app
    app = Flask(__name__)
    
    # Load configuration
    config_name = os.environ.get('FLASK_CONFIG', 'development')
    app.config.from_object(config[config_name])
    
    # Initialize database
    db.init_app(app)
    
    with app.app_context():
        # Find the ontology
        ontology = Ontology.query.filter_by(name=ontology_name).first()
        if not ontology:
            logger.error(f"Ontology '{ontology_name}' not found in database")
            return False
        
        logger.info(f"Found ontology: {ontology.name} (ID: {ontology.id})")
        
        # Get the current version
        current_version = OntologyVersion.query.filter_by(
            ontology_id=ontology.id,
            is_current=True
        ).first()
        
        if not current_version:
            logger.error(f"No current version found for ontology '{ontology_name}'")
            return False
        
        logger.info(f"Using version {current_version.version_number} created at {current_version.created_at}")
        
        # Capture existing embeddings (uri -> content_hash, embedding) BEFORE the delete, so the
        # delete/re-insert below does not blank them. The embedding text is "{label}: {comment}" and
        # content_hash is over (uri, label, comment), so an unchanged content_hash means the embedding
        # is still valid; changed/new entities keep NULL (populate_entity_embeddings fills those).
        prev_embeddings = {
            e.uri: (e.content_hash, e.embedding)
            for e in OntologyEntity.query.filter_by(ontology_id=ontology.id).all()
        }
        n_prev_emb = sum(1 for _ch, emb in prev_embeddings.values() if emb is not None)

        # Clear existing entities for this ontology
        deleted_count = OntologyEntity.query.filter_by(ontology_id=ontology.id).delete()
        logger.info(f"Cleared {deleted_count} existing entities")
        
        # Parse the ontology content - try file first, then database content
        g = rdflib.Graph()
        try:
            # First try parsing from original file if it exists
            # Use script directory to find ontologies folder (works on both dev and production)
            _script_dir = os.path.dirname(os.path.abspath(__file__))
            ontologies_dir = os.path.join(os.path.dirname(_script_dir), 'ontologies')
            ontology_file = os.path.join(ontologies_dir, f"{ontology_name}.ttl")
            if os.path.exists(ontology_file):
                logger.info(f"Parsing from TTL file: {ontology_file}")
                g.parse(ontology_file, format='turtle')
                logger.info(f"Parsed ontology from file with {len(g)} triples")
            else:
                # Fallback to database content
                logger.info("Parsing from database content")
                g.parse(data=current_version.content, format='turtle')
                logger.info(f"Parsed ontology from database with {len(g)} triples")
        except Exception as e:
            logger.error(f"Failed to parse ontology content: {e}")
            # Try with less strict parsing
            try:
                logger.info("Attempting to parse with error recovery...")
                g = rdflib.Graph()
                # Create a temporary file with proper prefixes
                temp_content = """@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix iao: <http://purl.obolibrary.org/obo/IAO_> .
@prefix proeth: <http://www.semanticweb.org/ontologies/proethica#> .
@prefix bfo: <http://purl.obolibrary.org/obo/BFO_> .
@prefix obo: <http://purl.obolibrary.org/obo/> .

""" + current_version.content
                
                g.parse(data=temp_content, format='turtle')
                logger.info(f"Successfully parsed with prefix fixes: {len(g)} triples")
            except Exception as e2:
                logger.error(f"All parsing attempts failed: {e2}")
                return False
        
        # Extract entities
        entities_added = 0
        
        # Predicates captured elsewhere (dedicated columns / provenance); every other
        # predicate on a class becomes a structured property below. The formal definition
        # (iao:0000115, OBO convention; skos:definition for legacy data) is NOT skipped: it is
        # captured into properties (as 'IAO_0000115'/'definition') so the entity page shows it as
        # the primary definition text (the 'comment' column holds the shorter rdfs:comment gloss).
        # It is still read separately below as a comment fallback for classes lacking rdfs:comment.
        class_standard_predicates = {
            RDF.type, RDFS.label, RDFS.comment, RDFS.subClassOf,
            rdflib.URIRef('http://www.w3.org/ns/prov#generatedAtTime'),
            rdflib.URIRef('http://www.w3.org/ns/prov#wasGeneratedBy'),
        }
        _IAO_DEFINITION = rdflib.URIRef('http://purl.obolibrary.org/obo/IAO_0000115')

        # Extract classes
        for class_uri in g.subjects(RDF.type, OWL.Class):
            # Skip blank nodes (rdflib artefacts without proper URIs)
            uri_str = str(class_uri)
            if not uri_str.startswith('http'):
                continue

            label = next(g.objects(class_uri, RDFS.label), None)
            comment = next(g.objects(class_uri, RDFS.comment), None)
            definition = (next(g.objects(class_uri, _IAO_DEFINITION), None)
                          or next(g.objects(class_uri, SKOS.definition), None))
            # Get rdfs:subClassOf for hierarchy traversal. Prefer a proethica
            # parent (keeps the category CTEs terminating at the proethica
            # boundary); fall back to the named BFO/IAO superclass so a core
            # class roots in the BFO tree for the entity-page Class Hierarchy.
            parent_uri = _pick_best_parent(g, class_uri)

            # Collect non-standard predicates (archetypeAxis, specializationAxis, skos
            # crosswalks, ...) into the structured properties JSON, mirroring the
            # individual loop, so class annotations reach the MCP/category readers.
            # subClassOf is captured as parent_uri; blank-node objects (restrictions)
            # are skipped.
            properties = {}
            for predicate, obj in g.predicate_objects(class_uri):
                if predicate in class_standard_predicates or isinstance(obj, rdflib.BNode):
                    continue
                pred_name = str(predicate).split('#')[-1].split('/')[-1]
                obj_value = str(obj)
                if pred_name in properties:
                    if isinstance(properties[pred_name], list):
                        properties[pred_name].append(obj_value)
                    else:
                        properties[pred_name] = [properties[pred_name], obj_value]
                else:
                    properties[pred_name] = obj_value

            label_str = str(label) if label else None
            comment_str = str(comment) if comment else str(definition) if definition else None
            entity = OntologyEntity(
                ontology_id=ontology.id,
                entity_type='class',
                uri=uri_str,
                label=label_str,
                comment=comment_str,
                parent_uri=parent_uri,
                properties=properties if properties else None,
                content_hash=_compute_content_hash(uri_str, label_str, comment_str),
                updated_at=datetime.now(timezone.utc)
            )
            db.session.add(entity)
            entities_added += 1
        
        logger.info(f"Extracted {entities_added} classes")
        
        # Extract object properties
        prop_count = 0
        for prop_uri in g.subjects(RDF.type, OWL.ObjectProperty):
            label = next(g.objects(prop_uri, RDFS.label), None)
            comment = next(g.objects(prop_uri, RDFS.comment), None)
            domain = next(g.objects(prop_uri, RDFS.domain), None)
            range_ = next(g.objects(prop_uri, RDFS.range), None)
            uri_str = str(prop_uri)
            label_str = str(label) if label else None
            comment_str = str(comment) if comment else None

            entity = OntologyEntity(
                ontology_id=ontology.id,
                entity_type='property',
                uri=uri_str,
                label=label_str,
                comment=comment_str,
                domain=str(domain) if domain else None,
                range=str(range_) if range_ else None,
                content_hash=_compute_content_hash(uri_str, label_str, comment_str),
                updated_at=datetime.now(timezone.utc)
            )
            db.session.add(entity)
            prop_count += 1

        # Extract datatype properties
        for prop_uri in g.subjects(RDF.type, OWL.DatatypeProperty):
            label = next(g.objects(prop_uri, RDFS.label), None)
            comment = next(g.objects(prop_uri, RDFS.comment), None)
            domain = next(g.objects(prop_uri, RDFS.domain), None)
            range_ = next(g.objects(prop_uri, RDFS.range), None)
            uri_str = str(prop_uri)
            label_str = str(label) if label else None
            comment_str = str(comment) if comment else None

            entity = OntologyEntity(
                ontology_id=ontology.id,
                entity_type='property',
                uri=uri_str,
                label=label_str,
                comment=comment_str,
                domain=str(domain) if domain else None,
                range=str(range_) if range_ else None,
                content_hash=_compute_content_hash(uri_str, label_str, comment_str),
                updated_at=datetime.now(timezone.utc)
            )
            db.session.add(entity)
            prop_count += 1

        logger.info(f"Extracted {prop_count} properties")
        entities_added += prop_count

        # Extract individuals (NamedIndividuals)
        individual_count = 0
        # Define standard predicates to skip when collecting properties
        standard_predicates = {
            RDF.type, RDFS.label, RDFS.comment, SKOS.definition,
            rdflib.URIRef('http://www.w3.org/ns/prov#generatedAtTime'),
            rdflib.URIRef('http://www.w3.org/ns/prov#wasGeneratedBy')
        }

        for individual_uri in g.subjects(RDF.type, OWL.NamedIndividual):
            label = next(g.objects(individual_uri, RDFS.label), None)
            comment = next(g.objects(individual_uri, RDFS.comment), None)
            # Fall back to skos:definition when there is no rdfs:comment (mirrors the class loop), so a
            # SKOS concept individual (e.g. an axis-vocabulary concept) carries its definition for display.
            definition = next(g.objects(individual_uri, SKOS.definition), None)

            # Get the types of this individual (excluding NamedIndividual itself)
            types = []
            for type_uri in g.objects(individual_uri, RDF.type):
                if type_uri != OWL.NamedIndividual:
                    types.append(str(type_uri))

            # Collect all other properties into a JSON structure
            properties = {}
            for predicate, obj in g.predicate_objects(individual_uri):
                if predicate not in standard_predicates:
                    pred_name = str(predicate).split('#')[-1].split('/')[-1]
                    obj_value = str(obj)
                    # Handle multiple values for same predicate
                    if pred_name in properties:
                        if isinstance(properties[pred_name], list):
                            properties[pred_name].append(obj_value)
                        else:
                            properties[pred_name] = [properties[pred_name], obj_value]
                    else:
                        properties[pred_name] = obj_value

            uri_str = str(individual_uri)
            label_str = str(label) if label else None
            comment_str = str(comment) if comment else str(definition) if definition else None
            entity = OntologyEntity(
                ontology_id=ontology.id,
                entity_type='individual',
                uri=uri_str,
                label=label_str,
                comment=comment_str,
                parent_uri=types[0] if types else None,
                properties=properties if properties else None,
                content_hash=_compute_content_hash(uri_str, label_str, comment_str),
                updated_at=datetime.now(timezone.utc)
            )
            db.session.add(entity)
            individual_count += 1

        logger.info(f"Extracted {individual_count} individuals")
        entities_added += individual_count

        # Commit the changes
        try:
            db.session.commit()
            logger.info(f"Successfully updated {entities_added} entities for ontology '{ontology_name}'")

            # Restore embeddings for entities whose (uri, content_hash) is unchanged, so a reload
            # preserves embeddings instead of blanking them. Changed/new entities stay NULL.
            if n_prev_emb:
                restored = 0
                for ent in OntologyEntity.query.filter_by(ontology_id=ontology.id).all():
                    prev = prev_embeddings.get(ent.uri)
                    if prev and prev[1] is not None and prev[0] == ent.content_hash:
                        ent.embedding = prev[1]
                        restored += 1
                db.session.commit()
                logger.info(f"Preserved {restored}/{n_prev_emb} embeddings across reload")
            
            # Update the MCP server cache timestamp
            ontology.updated_at = datetime.now()
            db.session.commit()
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to commit entity updates: {e}")
            db.session.rollback()
            return False


def main():
    """Main script entry point."""
    
    # Parse command line arguments
    ontology_name = "proethica-intermediate"
    if len(sys.argv) > 1:
        ontology_name = sys.argv[1]
    
    logger.info(f"Refreshing entity extraction for ontology: {ontology_name}")
    
    success = refresh_ontology_entities(ontology_name)
    
    if success:
        logger.info("Entity extraction refresh completed successfully")
        logger.info("MCP server will now serve updated entities on next query")
        return 0
    else:
        logger.error("Entity extraction refresh failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())