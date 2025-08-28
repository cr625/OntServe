# OntServe URI Resolution API

## Overview
OntServe provides multiple URI resolution endpoints to resolve ontology entity URIs and retrieve their information in TTL or JSON format. This is particularly useful for handling ProEthica ontology references.

## Endpoints

### 1. Path-based Resolution (Recommended for simplicity)
```
GET /ontology/<ontology_path>/<entity_name>
```

Examples:
- `/ontology/intermediate/Honesty`
- `/ontology/core/Principle`

### 2. Query Parameter Resolution (For full URIs)
```
GET /resolve?uri=<full_uri>
OPTIONS /resolve  (for CORS preflight)
```

Example:
- `/resolve?uri=http://proethica.org/ontology/intermediate#Honesty`

Note: The `#` character should be URL-encoded as `%23` when used in query parameters.

## Content Negotiation
The endpoint supports content negotiation via the `Accept` header:

- **Default (TTL format)**: No `Accept` header or `text/turtle`
- **JSON format**: `Accept: application/json`

## Examples

### 1. Get Entity in TTL Format (Default)

**Path-based (Simplest):**
```bash
curl "http://localhost:5003/ontology/intermediate/Honesty"
```

**Query parameter:**
```bash
curl "http://localhost:5003/resolve?uri=http://proethica.org/ontology/intermediate%23Honesty"
```

**Response:**
```turtle
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix proethica_intermediate: <http://proethica.org/ontology/proethica_intermediate#> .

<http://proethica.org/ontology/intermediate#Honesty> a owl:Class ;
    rdfs:label "Honesty" ;
    rdfs:comment "The ethical commitment to truthfulness, transparency..." ;
    rdfs:subClassOf <http://proethica.org/ontology/intermediate#FundamentalPrinciple> .
```

### 2. Get Entity in JSON Format

**Path-based:**
```bash
curl -H "Accept: application/json" "http://localhost:5003/ontology/intermediate/Honesty"
```

**Query parameter:**
```bash
curl -H "Accept: application/json" "http://localhost:5003/resolve?uri=http://proethica.org/ontology/intermediate%23Honesty"
```

**Response:**
```json
{
  "uri": "http://proethica.org/ontology/intermediate#Honesty",
  "label": "Honesty",
  "type": "class",
  "definition": "The ethical commitment to truthfulness, transparency...",
  "ontology": "proethica-intermediate",
  "ontology_base_uri": "http://proethica.org/ontology/proethica_intermediate#",
  "properties": {
    "generated_definition": {
      "confidence": 0.96,
      "content": "...",
      "generated_at": "2025-08-28 11:50:03.058090",
      "reasoning": "..."
    }
  }
}
```

### 3. Test with ProEthica Core Ontology
```bash
curl "http://localhost:5003/ontology/core/Principle"
```

## CORS Support
The endpoint includes full CORS support:
- `Access-Control-Allow-Origin: *`
- `Access-Control-Allow-Methods: GET, OPTIONS`
- `Access-Control-Allow-Headers: Accept, Content-Type`

## Error Handling
If an entity is not found, the endpoint returns a 404 with error details:

```json
{
  "error": "Entity not found",
  "uri": "http://proethica.org/ontology/intermediate#NonExistent"
}
```

## Development Helper

### Using Path-based Resolution (Recommended)
```python
# Simple path construction
ontology = "intermediate"
entity = "Honesty"
url = f"http://localhost:5003/ontology/{ontology}/{entity}"
```

### Using Query Parameter Resolution
```python
from urllib.parse import quote
uri = "http://proethica.org/ontology/intermediate#Honesty"
# Only need to encode the # character
encoded_uri = uri.replace("#", "%23")
url = f"http://localhost:5003/resolve?uri={encoded_uri}"
```

## Integration with ProEthica Domain
When you set up the redirect on the `proethica.org` domain, you can configure it to forward requests.

**Option 1: Simple Path Redirect (Recommended)**
Configure your domain to redirect:
- `http://proethica.org/ontology/intermediate/Honesty` → `http://your-server:5003/ontology/intermediate/Honesty`

**Option 2: Full URI Redirect**
For URIs with fragments:
- `http://proethica.org/ontology/intermediate#Honesty` → `http://your-server:5003/resolve?uri=http://proethica.org/ontology/intermediate%23Honesty`

This creates a seamless URI resolution system where ProEthica URIs are automatically resolvable.

## Available Ontologies
Currently available in OntServe:
- `proethica-core`: 19 entities (formal tuple components)
- `proethica-intermediate`: 124 entities (populated with NSPE concepts)

## Future Enhancements
- Bulk resolution endpoint for multiple URIs
- Caching for improved performance
- Support for RDF/XML and other serialization formats
- Content-based URI guessing for partial matches