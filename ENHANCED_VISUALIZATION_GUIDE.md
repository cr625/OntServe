# Enhanced Ontology Visualization Guide

This guide explains how to use the enhanced ontology visualization system in OntServe with Owlready2 reasoning and Cytoscape.js interactive graphs.

## Overview

The enhanced visualization system provides:

- **Advanced Ontology Processing** with Owlready2 reasoning
- **Interactive Graph Visualization** using Cytoscape.js
- **Multiple Layout Algorithms** (hierarchical, force-directed, circular)
- **Real-time Filtering and Search** with semantic similarity
- **Export Capabilities** (PNG images, data formats)
- **Consistency Checking** and inference visualization
- **ProEthica and OntExtract Integration**

## Key Features

### 1. Owlready2 Enhanced Processing

#### Reasoning Capabilities
- **HermiT and Pellet Reasoners**: Automatic inference of implicit relationships
- **Consistency Checking**: Validation of ontology logical consistency
- **Restriction Analysis**: Complex OWL restriction extraction and display
- **Property Chain Reasoning**: Transitive and functional property inference

#### Benefits Over Previous Implementation
```python
# Before (RDFLib only)
classes = extract_basic_classes(graph)

# After (Owlready2 + RDFLib)
result = owlready_importer.import_from_url(url, use_reasoner=True)
# Includes:
# - Inferred subclass relationships
# - Consistency validation  
# - Restriction analysis
# - Enhanced metadata
```

### 2. Cytoscape.js Interactive Visualization

#### Layout Algorithms
- **Dagre (Hierarchical)**: Best for ontology class hierarchies
- **COSE (Force-directed)**: Good for exploring relationships
- **FCOSE (Fast COSE)**: Optimized for large ontologies
- **Breadth First**: Tree-like exploration
- **Circular**: Radial visualization
- **Grid**: Systematic arrangement

#### Interactive Features
- **Click to Focus**: Click nodes to see details and highlight connections
- **Search and Filter**: Real-time text search with highlighting
- **Zoom and Pan**: Smooth navigation with mouse/touch
- **Entity Details Panel**: Rich information display on selection
- **Export to PNG**: High-resolution image export

### 3. Enhanced Integration Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   OntExtract    │    │    OntServe      │    │   ProEthica     │
│                 │    │                  │    │                 │
│ PROV-O Tracking │───▶│ Enhanced Importer│◀───│ Ethics Ontology │
│ Temporal Data   │    │ + Owlready2      │    │ Decision Support│
│                 │    │ + Reasoning      │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Cytoscape.js    │
                    │  Visualization   │
                    │  • Multi-layout  │
                    │  • Interactive   │
                    │  • Export ready  │
                    └──────────────────┘
```

## Installation and Setup

### 1. Install Enhanced Dependencies

```bash
# Install enhanced requirements
pip install -r requirements-enhanced.txt

# Install Java JDK for reasoners (Ubuntu/Debian)
sudo apt-get install openjdk-11-jdk

# Or on macOS with Homebrew
brew install openjdk@11

# Or on CentOS/RHEL
sudo yum install java-11-openjdk-devel
```

### 2. Verify Installation

```bash
# Test the enhanced system
cd OntServe
python test_enhanced_visualization.py
```

### 3. Start the Web Server

```bash
cd OntServe/web
./run.sh
```

## Usage Examples

### 1. Import with Enhanced Processing

```python
from OntServe.importers.owlready_importer import OwlreadyImporter
from OntServe.storage.file_storage import FileStorage

# Create enhanced importer
storage = FileStorage()
importer = OwlreadyImporter(storage_backend=storage)

# Import with reasoning
result = importer.import_from_url(
    "https://example.org/ontology.ttl",
    ontology_id="my-ontology",
    name="My Enhanced Ontology"
)

print(f"Reasoning applied: {result['metadata']['reasoning_applied']}")
print(f"Consistency: {result['metadata']['consistency_check']}")
print(f"Inferred relationships: {result['metadata']['inferred_relationships']}")
```

### 2. Generate Visualization Data

```python
# Get Cytoscape.js compatible data
viz_data = importer.get_visualization_data("my-ontology")

# Data structure:
{
    'nodes': [{'data': {...}, 'classes': '...'}],
    'edges': [{'data': {...}, 'classes': '...'}],
    'layout_options': {...},
    'style_options': [...]
}
```

### 3. Access via Web Interface

Visit: `http://localhost:5003/editor/ontology/<ontology-id>/visualize`

**Features Available:**
- Layout selector (7 different algorithms)
- Entity type filtering (classes, properties, individuals)
- Search with highlighting
- Inferred relationship toggle
- Interactive zoom and pan controls
- Entity details panel
- PNG export functionality

## Integration with Existing Systems

### OntExtract Integration

**Use Case**: Visualize PROV-O experiment tracking

```python
# In OntExtract application
from OntServe.importers.owlready_importer import OwlreadyImporter

# Import PROV-O with reasoning for experiment tracking
importer = OwlreadyImporter()
prov_result = importer.import_from_url("https://www.w3.org/ns/prov.ttl")

# Get enhanced PROV concepts for experiment classification
enhanced_data = importer.get_visualization_data("prov-o")
prov_concepts = [node for node in enhanced_data['nodes'] 
                if 'prov' in node['data']['namespace']]
```

**Benefits for OntExtract:**
- Better understanding of PROV-O structure
- Visual exploration of provenance relationships
- Enhanced experiment classification
- Interactive debugging of provenance chains

### ProEthica Integration

**Use Case**: Visualize ethical decision-making ontologies

```python
# In ProEthica application  
from OntServe.importers.owlready_importer import OwlreadyImporter

# Import ethics ontology with reasoning
importer = OwlreadyImporter()
ethics_result = importer.import_from_file(
    "proethica_ontology.ttl",
    use_reasoner=True
)

# Visualize ethical concepts and relationships
viz_data = importer.get_visualization_data("proethica-ontology")
```

**Benefits for ProEthica:**
- Interactive exploration of ethical principles
- Visual validation of ontology consistency
- Better understanding of role-obligation relationships
- Export capability for documentation

### Migration from Neo4j

**Previous Neo4j approach issues:**
- Complex setup and maintenance
- Query complexity for visualization
- Performance issues with large ontologies
- Limited layout options

**New approach advantages:**
- No database server required for visualization
- Client-side interactivity
- Multiple layout algorithms
- Better performance
- Easier deployment

**Migration steps:**

1. **Replace Neo4j queries** with Owlready2 processing:
   ```python
   # Before (Neo4j)
   cypher_query = "MATCH (n:Class)-[:SUBCLASS_OF]->(m:Class) RETURN n, m"
   
   # After (Owlready2)
   viz_data = importer.get_visualization_data(ontology_id)
   # Automatically includes subclass relationships
   ```

2. **Update visualization templates** to use Cytoscape.js instead of Neo4j browser

3. **Leverage enhanced reasoning** for better relationship discovery

## Configuration Options

### Owlready2 Reasoner Configuration

```python
importer = OwlreadyImporter(storage_backend=storage)

# Configure reasoner options
importer.use_reasoner = True
importer.reasoner_type = 'hermit'  # or 'pellet'
importer.validate_consistency = True
importer.include_inferred = True
importer.extract_restrictions = True
```

### Visualization Layout Configuration

```javascript
// In visualization template
const layoutConfigs = {
    'dagre': {
        name: 'dagre',
        rankDir: 'TB',
        spacingFactor: 1.2,
        nodeSep: 50,
        rankSep: 100
    },
    'cose': {
        name: 'cose', 
        nodeRepulsion: 400000,
        idealEdgeLength: 80,
        edgeElasticity: 200
    }
    // ... other layouts
};
```

### Color and Style Configuration

```javascript
// Node styling based on ontology namespaces
const nodeStyles = {
    'ns-bfo': { backgroundColor: '#8E24AA' },
    'ns-prov': { backgroundColor: '#F57F17' }, 
    'ns-proethica': { backgroundColor: '#D32F2F' }
};
```

## Performance Considerations

### Large Ontology Handling

- **Automatic Layout Selection**: System chooses optimal layout based on node count
- **Lazy Loading**: Only load visible portions for very large ontologies  
- **Reasoning Cache**: Cache reasoning results to avoid recomputation
- **Client-side Filtering**: Fast filtering without server round-trips

### Memory Usage

```python
# Monitor memory usage with large ontologies
import psutil
process = psutil.Process()
print(f"Memory usage: {process.memory_info().rss / 1024 / 1024:.1f} MB")
```

## Troubleshooting

### Common Issues

1. **Java Not Found Error**
   ```
   Error: Java not found for Owlready2 reasoners
   Solution: Install JDK 8+ and set JAVA_HOME
   ```

2. **Reasoning Timeout**
   ```python
   # Disable reasoning for very large/complex ontologies
   importer.use_reasoner = False
   ```

3. **Visualization Performance Issues**
   ```javascript
   // Use simpler layout for large graphs
   if (nodeCount > 1000) {
       layoutName = 'grid';
   }
   ```

### Debug Mode

```python
# Enable detailed logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Test specific components
python test_enhanced_visualization.py
```

## Future Enhancements

### Planned Features

1. **WebVOWL Integration**: Option to export to WebVOWL format
2. **Collaborative Editing**: Multi-user ontology editing with conflict resolution
3. **Version Comparison**: Visual diff between ontology versions
4. **SPARQL Query Builder**: Visual query construction interface
5. **Plugin Architecture**: Extensible visualization components

### Integration Roadmap

1. **Phase 1**: Core enhanced visualization (✅ Complete)
2. **Phase 2**: OntExtract/ProEthica integration testing
3. **Phase 3**: Advanced reasoning features (SWRL rules)
4. **Phase 4**: Collaborative features and version control

## API Reference

### OwlreadyImporter Class

```python
class OwlreadyImporter(BaseImporter):
    def import_from_url(url, ontology_id=None, use_reasoner=True) -> dict
    def import_from_file(path, ontology_id=None, use_reasoner=True) -> dict
    def get_visualization_data(ontology_id) -> dict
    def extract_classes(ontology_id) -> list
    def extract_properties(ontology_id) -> list
    def extract_individuals(ontology_id) -> list
```

### Visualization Data Format

```json
{
    "nodes": [
        {
            "data": {
                "id": "class_uri",
                "label": "Class Label", 
                "type": "class",
                "is_inferred": false,
                "restrictions": 2,
                "namespace": "ontology_ns"
            },
            "classes": "class-node ns-ontology"
        }
    ],
    "edges": [
        {
            "data": {
                "source": "child_uri",
                "target": "parent_uri", 
                "type": "subClassOf",
                "is_inferred": false
            },
            "classes": "explicit"
        }
    ],
    "layout_options": {...},
    "style_options": [...]
}
```

## Support and Contributing

### Getting Help

1. Check the test suite: `python test_enhanced_visualization.py`
2. Review logs in `OntServe/logs/`
3. Consult the CLAUDE.md files in each project

### Contributing

1. Follow the existing code structure
2. Add tests for new features
3. Update documentation
4. Ensure compatibility with OntExtract and ProEthica

---

**Enhanced Ontology Visualization System**  
*Part of the OntServe unified ontology management platform*  
*Compatible with OntExtract and ProEthica*
