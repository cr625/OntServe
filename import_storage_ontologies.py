#!/usr/bin/env python3
"""
Import all ontologies from storage directory into the database.

This script scans the storage/ontologies directory and imports any ontology files
that aren't already in the database.
"""

import os
import sys
from pathlib import Path
import re

# Set environment
os.environ['ENVIRONMENT'] = 'development'

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from web.app import create_app
from web.models import db, Ontology, OntologyVersion
from rdflib import Graph, Namespace, RDF, RDFS, OWL
from datetime import datetime, timezone


# Common ontology metadata based on file naming conventions
ONTOLOGY_METADATA = {
    'bfo': {
        'name': 'bfo',
        'base_uri': 'http://purl.obolibrary.org/obo/bfo.owl',
        'description': 'Basic Formal Ontology - A top-level ontology designed to support scientific research',
        'version_tag': '2.0',
        'is_base': True,
        'ontology_type': 'base'
    },
    'prov-o': {
        'name': 'prov-o',
        'base_uri': 'http://www.w3.org/ns/prov#',
        'description': 'PROV Ontology - W3C provenance ontology for representing and interchanging provenance information',
        'version_tag': 'W3C Recommendation',
        'is_base': True,
        'ontology_type': 'base'
    },
    'prov': {
        'name': 'prov-o',
        'base_uri': 'http://www.w3.org/ns/prov#',
        'description': 'PROV Ontology - W3C provenance ontology for representing and interchanging provenance information',
        'version_tag': 'W3C Recommendation',
        'is_base': True,
        'ontology_type': 'base'
    }
}


def extract_ontology_metadata(graph, filename):
    """Extract metadata from the ontology file."""

    # Try to get ontology URI
    OWL_NS = Namespace("http://www.w3.org/2002/07/owl#")
    DC = Namespace("http://purl.org/dc/elements/1.1/")
    DCTERMS = Namespace("http://purl.org/dc/terms/")

    # Find the ontology declaration
    ontology_uri = None
    for s in graph.subjects(RDF.type, OWL_NS.Ontology):
        ontology_uri = str(s)
        break

    # Extract title/label
    title = None
    for obj in graph.objects(subject=None, predicate=DC.title):
        title = str(obj)
        break
    if not title:
        for obj in graph.objects(subject=None, predicate=RDFS.label):
            title = str(obj)
            break

    # Extract description
    description = None
    for obj in graph.objects(subject=None, predicate=DC.description):
        description = str(obj)
        break
    if not description:
        for obj in graph.objects(subject=None, predicate=RDFS.comment):
            description = str(obj)
            break

    # Extract version info
    version_info = None
    for obj in graph.objects(subject=None, predicate=OWL_NS.versionInfo):
        version_info = str(obj)
        break

    return {
        'ontology_uri': ontology_uri,
        'title': title,
        'description': description,
        'version_info': version_info
    }


def guess_ontology_name(filename):
    """Guess ontology name from filename."""
    # Remove common patterns and extensions
    name = filename.lower()
    name = re.sub(r'\.ttl$', '', name)
    name = re.sub(r'\.rdf$', '', name)
    name = re.sub(r'\.owl$', '', name)
    name = re.sub(r'\.n3$', '', name)

    # Convert common URL patterns to names
    # e.g., purl-obolibrary-org-obo-bfo-owl -> bfo
    if 'bfo' in name:
        return 'bfo'
    elif 'prov' in name:
        return 'prov-o'
    elif 'proethica' in name:
        if 'intermediate' in name:
            return 'proethica-intermediate'
        return 'proethica'

    # Default: use cleaned filename
    name = re.sub(r'[^a-z0-9-]', '-', name)
    return name


def import_ontology_file(file_path, force=False):
    """Import a single ontology file into the database."""

    print(f"\n{'='*70}")
    print(f"Processing: {file_path.name}")
    print(f"{'='*70}")

    # Determine format
    suffix = file_path.suffix.lower()
    format_map = {
        '.ttl': 'turtle',
        '.rdf': 'xml',
        '.owl': 'xml',
        '.n3': 'n3',
        '.nt': 'nt'
    }
    rdf_format = format_map.get(suffix, 'turtle')

    # Read and parse the file
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        print(f"✓ Read file: {len(content)} bytes")

        # Parse to extract metadata
        graph = Graph()
        graph.parse(data=content, format=rdf_format)
        print(f"✓ Parsed RDF: {len(graph)} triples")

        metadata = extract_ontology_metadata(graph, file_path.name)

    except Exception as e:
        print(f"✗ Error reading/parsing file: {e}")
        return False

    # Guess ontology name
    ontology_name = guess_ontology_name(file_path.name)

    # Get predefined metadata if available
    predefined = ONTOLOGY_METADATA.get(ontology_name, {})

    # Merge metadata
    base_uri = predefined.get('base_uri') or metadata.get('ontology_uri') or f'http://example.org/{ontology_name}'
    description = predefined.get('description') or metadata.get('description') or f'Ontology imported from {file_path.name}'
    version_tag = predefined.get('version_tag') or metadata.get('version_info') or '1.0'
    is_base = predefined.get('is_base', False)
    ontology_type = predefined.get('ontology_type', 'domain')

    # Check if already exists
    existing = db.session.query(Ontology).filter_by(name=ontology_name).first()

    if existing and not force:
        print(f"⚠ Ontology '{ontology_name}' already exists (ID: {existing.id})")
        print(f"  Use --force to reimport")
        return False

    if existing:
        print(f"⚠ Updating existing ontology (ID: {existing.id})")
        ontology = existing
    else:
        print(f"✓ Creating new ontology: {ontology_name}")
        ontology = Ontology(
            name=ontology_name,
            base_uri=base_uri,
            description=description,
            is_base=is_base,
            is_editable=not is_base,
            ontology_type=ontology_type
        )
        db.session.add(ontology)
        db.session.flush()

    # Create version
    version = OntologyVersion(
        ontology_id=ontology.id,
        version_number=1,
        version_tag=version_tag,
        content=content,
        change_summary=f'Imported from storage: {file_path.name}',
        created_by='system',
        is_current=True,
        is_draft=False,
        workflow_status='published'
    )
    db.session.add(version)
    db.session.commit()

    print(f"✅ Successfully imported '{ontology_name}' (ID: {ontology.id})")
    print(f"   Base URI: {base_uri}")
    print(f"   Description: {description[:80]}...")
    print(f"   Triples: {len(graph)}")

    return True


def main():
    """Import all ontologies from storage directory."""

    import argparse
    parser = argparse.ArgumentParser(description='Import ontologies from storage into database')
    parser.add_argument('--force', action='store_true', help='Reimport existing ontologies')
    parser.add_argument('files', nargs='*', help='Specific files to import (default: all)')
    args = parser.parse_args()

    storage_dir = project_root / 'storage' / 'ontologies'

    if not storage_dir.exists():
        print(f"ERROR: Storage directory not found: {storage_dir}")
        return 1

    # Find ontology files
    if args.files:
        files = [storage_dir / f for f in args.files]
    else:
        files = list(storage_dir.glob('*.ttl'))
        files.extend(storage_dir.glob('*.rdf'))
        files.extend(storage_dir.glob('*.owl'))
        files.extend(storage_dir.glob('*.n3'))

    if not files:
        print(f"No ontology files found in {storage_dir}")
        return 0

    print(f"Found {len(files)} ontology file(s)")

    # Create Flask app and import
    app = create_app('development')

    imported = 0
    skipped = 0
    failed = 0

    with app.app_context():
        for file_path in files:
            if not file_path.exists():
                print(f"✗ File not found: {file_path}")
                failed += 1
                continue

            try:
                if import_ontology_file(file_path, force=args.force):
                    imported += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"✗ Error importing {file_path.name}: {e}")
                import traceback
                traceback.print_exc()
                failed += 1

    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"✓ Imported: {imported}")
    print(f"⚠ Skipped:  {skipped}")
    print(f"✗ Failed:   {failed}")
    print(f"{'='*70}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
