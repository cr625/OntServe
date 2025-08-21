# Scripts Directory

This directory contains utility scripts, one-time runs, database fixes, and automation scripts for the OntServe project.

## Files

- `example_usage.py` - Example usage of the OntologyManager for testing and demonstration
- `fix_proethica_database.py` - Database repair and migration script for proethica integration
- `import_bfo.py` - Script to import the Basic Formal Ontology (BFO)
- `import_proethica.py` - Script to import proethica ontology data
- `import_prov_o.py` - Script to import the PROV-O (Provenance Ontology)
- `initialize_default_ontologies.py` - Initialization script for setting up default ontologies

## Usage

Run scripts from the project root directory:

```bash
cd /path/to/OntServe
python scripts/script_name.py
```

## Guidelines

- All executable scripts should be placed in this directory
- Scripts should be well-documented with docstrings
- Include usage examples in script documentation
- Use descriptive filenames that indicate the script's purpose
