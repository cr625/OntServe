# OntExtract Integration with OntServe

This document explains how OntExtract integrates with OntServe to access PROV-O entities and other ontology data from a centralized server.

## Overview

The integration allows OntExtract to:
- Access PROV-O classes and properties from OntServe instead of downloading directly
- Use cached responses for improved performance
- Fall back to direct download when OntServe is unavailable
- Maintain backward compatibility with existing code

## Architecture

```
OntExtract ──→ OntExtract Client ──→ OntServe MCP Server ──→ PostgreSQL Database
    ↓              ↓                      ↓                        ↓
 Local Cache ←─ Response Cache ←─── Entity Storage ←───── PROV-O Concepts
```

## Setup Instructions

### 1. Set up OntServe Database

First, ensure PostgreSQL is running and create the OntServe database:

```bash
# Start PostgreSQL with Docker
cd OntServe/config
docker-compose up -d ontserve-db

# Wait for database to be ready, then import PROV-O
cd ../scripts
python import_prov_o.py
```

### 2. Start OntServe MCP Server

```bash
cd OntServe/servers
export ONTSERVE_DB_URL="postgresql://ontserve_user:ontserve_development_password@localhost:5433/ontserve"
python mcp_server.py
```

The server will start on `http://localhost:8082` by default.

### 3. Configure OntExtract

Set environment variables in your OntExtract environment:

```bash
# Enable OntServe integration
export USE_ONTSERVE=true
export ONTSERVE_URL=http://localhost:8082

# Optional: Configure caching
export ONTSERVE_CACHE_TTL=3600  # 1 hour cache
```

### 4. Verify Integration

Test the integration:

```python
from shared_services.ontology.ontology_importer import OntologyImporter

# Initialize with OntServe support
importer = OntologyImporter()

# This should now use OntServe if available
result = importer.import_prov_o()

if result.get('from_ontserve'):
    print("✓ Successfully using OntServe")
else:
    print("⚠ Fell back to direct download")

# Access experiment concepts
concepts = result.get('experiment_concepts', {})
print(f"Activities: {len(concepts.get('activities', []))}")
print(f"Entities: {len(concepts.get('entities', []))}")
print(f"Agents: {len(concepts.get('agents', []))}")
```

## Client Library Usage

The OntExtract client can also be used independently:

```python
from OntServe.client.ontextract_client import OntExtractClient

# Initialize client
client = OntExtractClient(
    ontserve_url='http://localhost:8082',
    cache_ttl=3600,  # 1 hour cache
    enable_cache=True
)

# Get PROV-O classes
classes = client.get_prov_classes()
for cls in classes:
    print(f"Class: {cls['label']} - {cls['uri']}")

# Get PROV-O properties  
properties = client.get_prov_properties()
for prop in properties:
    print(f"Property: {prop['label']} - {prop['uri']}")

# Search for specific concepts
results = client.search_concepts('Activity')
for result in results:
    print(f"Found: {result['label']}")

# Get domain information
domain_info = client.get_domain_info('prov-o')
if domain_info:
    print(f"Domain: {domain_info['domain']['display_name']}")
    print(f"Total concepts: {domain_info['stats']['total_concepts']}")

# Clean up
client.close()
```

## Features

### Automatic Fallback

If OntServe is unavailable, the system automatically falls back to direct download:

```python
# OntologyImporter will try OntServe first, then fall back
importer = OntologyImporter()
result = importer.import_prov_o()

# Check source
if result.get('from_ontserve'):
    print("Using OntServe")
else:
    print("Using direct download (fallback)")
```

### Caching

Both levels of caching are supported:

1. **OntServe Response Cache**: Client caches responses from OntServe (default: 1 hour)
2. **Local Ontology Cache**: Traditional file-based caching for downloaded ontologies

```python
# Configure caching
client = OntExtractClient(
    cache_ttl=7200,      # 2 hours
    enable_cache=True,
    cache_dir='./ontserve_cache'
)

# Clear cache if needed
client.clear_cache()
```

### Environment Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_ONTSERVE` | `true` | Enable/disable OntServe integration |
| `ONTSERVE_URL` | `http://localhost:8082` | OntServe server URL |
| `ONTSERVE_CACHE_TTL` | `3600` | Cache TTL in seconds |
| `ONTSERVE_DB_URL` | `postgresql://...` | Database connection for OntServe |

## Testing Integration

### 1. Test OntServe Health

```bash
curl http://localhost:8082/health
```

Expected response:
```json
{
  "status": "ok",
  "message": "OntServe MCP server is running", 
  "database_connected": true,
  "domains_loaded": 1
}
```

### 2. Test PROV-O Import

```bash
cd OntExtract
python -c "
from shared_services.ontology.ontology_importer import OntologyImporter
importer = OntologyImporter()
result = importer.import_prov_o()
print('Success:', result.get('success'))
print('From OntServe:', result.get('from_ontserve', False))
print('Concepts:', sum(len(c) for c in result.get('experiment_concepts', {}).values()))
"
```

### 3. Test Client Library

```bash
cd OntServe/client
python ontextract_client.py --test classes
python ontextract_client.py --test properties
python ontextract_client.py --test domain
```

## Troubleshooting

### OntServe Not Available

```
WARNING:ontology_importer:Failed to get PROV-O from OntServe: Failed to connect to OntServe
INFO:ontology_importer:Falling back to direct download...
```

**Solution**: 
1. Check if OntServe is running: `curl http://localhost:8082/health`
2. Verify database is running: `docker ps | grep ontserve-postgres`
3. Check environment variables are set correctly

### PROV-O Not Imported

```
ERROR:Storage error getting domain info: Domain not found: prov-o
```

**Solution**: Run the PROV-O import script:
```bash
cd OntServe/scripts
python import_prov_o.py --force
```

### Client Connection Issues

```
WARNING:Cannot connect to OntServe: Connection refused
```

**Solution**:
1. Verify OntServe URL: `echo $ONTSERVE_URL`
2. Check firewall/port access
3. Try disabling OntServe: `export USE_ONTSERVE=false`

### Cache Issues

If responses seem stale:
```python
from OntServe.client.ontextract_client import OntExtractClient
client = OntExtractClient()
client.clear_cache()
```

## Migration Notes

### Existing OntExtract Code

Existing code using `OntologyImporter` should work without changes:

```python
# This code remains unchanged
importer = OntologyImporter()
result = importer.import_prov_o()
concepts = result['experiment_concepts']
```

The integration is transparent - OntServe is used when available, with automatic fallback.

### Performance Impact

- **First request**: Slight overhead for OntServe connection test
- **Subsequent requests**: Faster due to no download/parsing needed
- **Offline mode**: Same performance as before (fallback to direct download)

## Development

### Adding New Ontologies

To add support for other ontologies in OntServe:

1. Create an import script similar to `import_prov_o.py`
2. Add the domain to the database
3. Import concepts as approved entities
4. Update the client library with domain-specific methods

### Extending the Client

The client library can be extended for other ontologies:

```python
def get_bfo_entities(self, category='all'):
    """Get BFO entities by category."""
    return self.get_entities_by_category(category, domain='bfo')
```

## Files Overview

- `OntServe/scripts/import_prov_o.py` - Import PROV-O into OntServe
- `OntServe/client/ontextract_client.py` - Client library for OntExtract
- `OntExtract/shared_services/ontology/ontology_importer.py` - Enhanced with OntServe integration
- `OntServe/config/schema.sql` - Database schema supporting the integration
- `OntServe/servers/mcp_server.py` - MCP server with real database backend

This integration provides a seamless way for OntExtract to access centralized ontology data while maintaining full backward compatibility and robust fallback mechanisms.
