# OntServe - Unified Ontology Server

A modular, extensible ontology management system that provides unified access to various ontology formats with support for multiple storage backends and API protocols.

## Features

- **Multiple Ontology Formats**: Support for PROV-O, BFO, and custom ontologies
- **Flexible Storage**: File-based, database, or hybrid storage backends
- **Modular Architecture**: Plugin-based system for importers and modules
- **Version Control**: Track ontology versions and history
- **Intelligent Caching**: In-memory and file-based caching for performance
- **Rich Extraction**: Extract classes, properties, and individuals from ontologies
- **Multiple APIs**: REST, MCP, and direct Python library access (planned)

## Installation

### Requirements

```bash
pip install rdflib requests
```

### Basic Setup

```python
from OntServe import OntologyManager

# Configure the manager
config = {
    'storage_type': 'file',
    'storage_config': {
        'storage_dir': './ontology_storage'
    },
    'cache_dir': './ontology_cache',
    'log_level': 'INFO'
}

# Create instance
manager = OntologyManager(config)
```

## Quick Start

### Import PROV-O Ontology

```python
# Import the W3C PROV-O ontology
result = manager.import_prov_o()

if result['success']:
    print(f"Imported {result['ontology_id']}")
    print(f"Triple count: {result['metadata']['triple_count']}")
```

### Import Custom Ontology

```python
# From URL
result = manager.import_ontology(
    source='https://example.com/ontology.ttl',
    ontology_id='my-ontology',
    name='My Custom Ontology'
)

# From file
result = manager.import_ontology(
    source='path/to/ontology.ttl',
    ontology_id='local-ontology'
)
```

### Extract Ontology Components

```python
# Extract classes
classes = manager.extract_classes('prov-o')
for cls in classes:
    print(f"Class: {cls['label']} ({cls['uri']})")

# Extract properties
properties = manager.extract_properties('prov-o')

# Extract individuals
individuals = manager.extract_individuals('prov-o')
```

### Manage Versions

```python
# Create a new version
version_id = manager.create_version('my-ontology', new_content)

# List versions
versions = manager.get_versions('my-ontology')

# Retrieve specific version
ontology = manager.get_ontology('my-ontology', version='2025-01-21T10:00:00')
```

## Architecture

### Core Components

1. **OntologyManager**: Central coordinator for all operations
2. **Storage Backends**: Pluggable storage implementations
   - FileStorage: File-based storage with JSON metadata
   - DatabaseStorage: SQLAlchemy-based (coming soon)
   - HybridStorage: Automatic fallback between storage types (coming soon)
3. **Importers**: Specialized importers for different ontology types
   - PROVImporter: PROV-O specific features
   - BFOImporter: BFO ontology support (coming soon)
4. **Modules**: Pluggable modules for additional functionality
   - QueryModule: SPARQL queries (coming soon)
   - ValidationModule: Ontology validation (coming soon)
   - ProvenanceModule: PROV-O specific operations (coming soon)

### Directory Structure

```
OntServe/
├── core/                # Core management components
│   └── ontology_manager.py
├── storage/            # Storage backend implementations
│   ├── base.py        # Abstract storage interface
│   └── file_storage.py
├── importers/          # Ontology importers
│   ├── base.py        # Abstract importer interface
│   └── prov_importer.py
├── modules/            # Pluggable modules (coming soon)
├── servers/            # API servers (coming soon)
├── models/             # Data models (coming soon)
└── utils/              # Utility functions
```

## Configuration

### Storage Configuration

```python
# File storage
config = {
    'storage_type': 'file',
    'storage_config': {
        'storage_dir': '/path/to/storage'
    }
}

# Database storage (coming soon)
config = {
    'storage_type': 'database',
    'storage_config': {
        'db_url': 'postgresql://user:pass@localhost/ontologies'
    }
}
```

### Caching Configuration

```python
config = {
    'cache_dir': './ontology_cache',
    'cache_ttl': 3600  # Cache time-to-live in seconds
}
```

### Logging Configuration

```python
config = {
    'log_level': 'INFO'  # DEBUG, INFO, WARNING, ERROR, CRITICAL
}
```

## API Reference

### OntologyManager Methods

- `import_ontology(source, importer_type='prov', ...)`: Import an ontology
- `import_prov_o(force_refresh=False)`: Import PROV-O ontology
- `get_ontology(ontology_id, version=None)`: Retrieve an ontology
- `store_ontology(ontology_id, content, metadata=None)`: Store an ontology
- `list_ontologies(filter_criteria=None)`: List available ontologies
- `delete_ontology(ontology_id, version=None)`: Delete an ontology
- `extract_classes(ontology_id)`: Extract classes from an ontology
- `extract_properties(ontology_id)`: Extract properties
- `extract_individuals(ontology_id)`: Extract individuals
- `get_versions(ontology_id)`: Get available versions
- `create_version(ontology_id, content, version_info=None)`: Create a version
- `get_metadata(ontology_id, version=None)`: Get ontology metadata
- `update_metadata(ontology_id, metadata, version=None)`: Update metadata
- `backup_ontology(ontology_id, backup_path)`: Create a backup
- `restore_ontology(ontology_id, backup_path)`: Restore from backup
- `clear_cache()`: Clear all caches
- `shutdown()`: Clean shutdown

## Examples

See `example_usage.py` for comprehensive examples of all features.

## Integration with Existing Systems

### OntExtract Integration

OntServe can be used as a drop-in replacement for OntExtract's ontology handling:

```python
# In OntExtract
from OntServe import OntologyManager

manager = OntologyManager({
    'storage_type': 'file',
    'cache_dir': 'OntExtract/ontology_cache'
})

# Import and use PROV-O for provenance tracking
result = manager.import_prov_o()
```

### proethica Integration

OntServe provides MCP-compatible endpoints (coming soon) for proethica:

```python
# In proethica
from OntServe.servers import MCPServer

server = MCPServer(ontology_manager)
server.run(port=5001)
```


