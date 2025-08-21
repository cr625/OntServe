# Enhanced Visualization Installation Instructions

## Directory Structure Overview

```
OntServe/                          # ← Install dependencies HERE (project root)
├── requirements-enhanced.txt      # ← Enhanced requirements file
├── importers/
│   └── owlready_importer.py      # ← Enhanced importer code
├── web/                          # ← Web application subfolder
│   ├── requirements.txt          # ← Basic web requirements
│   └── run.sh                    # ← Web server startup script
└── setup-venv.sh                 # ← Virtual environment setup
```

## Why Install in Main OntServe Folder?

1. **Module Structure**: The enhanced importer (`owlready_importer.py`) is in `OntServe/importers/`, not in the web subfolder
2. **Import Paths**: The web application imports from parent modules: `from ..importers.owlready_importer import OwlreadyImporter`
3. **Virtual Environment**: The project's virtual environment is set up at the root level
4. **Requirements Location**: The `requirements-enhanced.txt` file is in the main folder

## Step-by-Step Installation

### 1. Navigate to OntServe Root Directory
```bash
cd /path/to/your/OntServe  # ← The main OntServe folder
```

### 2. Set Up Virtual Environment (if not already done)
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Linux/Mac
# OR
venv\Scripts\activate     # On Windows
```

### 3. Install Enhanced Dependencies
```bash
# Install from the enhanced requirements file
pip install -r requirements-enhanced.txt

# Install Java JDK for Owlready2 reasoners
# Ubuntu/Debian:
sudo apt-get install openjdk-11-jdk

# macOS:
brew install openjdk@11

# CentOS/RHEL:
sudo yum install java-11-openjdk-devel
```

### 4. Verify Installation
```bash
# Test the enhanced system
python test_enhanced_visualization.py
```

### 5. Start the Web Server
```bash
# Navigate to web subfolder for server startup
cd web
./run.sh
```

## Alternative: Use Existing Setup Script

If you have the existing setup script, you can modify it:

```bash
# From OntServe root directory
./setup-venv.sh

# Then install enhanced requirements
source venv/bin/activate
pip install -r requirements-enhanced.txt
```

## Troubleshooting

### Virtual Environment Issues
```bash
# If you get import errors, check your current directory:
pwd
# Should show: /path/to/OntServe (not /path/to/OntServe/web)

# Check virtual environment is active:
which python
# Should show: /path/to/OntServe/venv/bin/python
```

### Dependency Conflicts
```bash
# If there are conflicts with existing web requirements:
pip install -r web/requirements.txt
pip install -r requirements-enhanced.txt

# Or create fresh environment:
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-enhanced.txt
```

### Java Not Found
```bash
# Check Java installation:
java -version
javac -version

# Set JAVA_HOME if needed:
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64  # Linux
export JAVA_HOME=/usr/local/opt/openjdk@11           # macOS
```

## Quick Start Commands

```bash
# Complete setup from scratch:
cd OntServe
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-enhanced.txt
sudo apt-get install openjdk-11-jdk  # Install Java
python test_enhanced_visualization.py  # Test system
cd web && ./run.sh  # Start server
```

## Important Notes

- **Don't install in web/ folder**: The web folder is just for the Flask application
- **Use project root**: All enhanced ontology processing happens at the OntServe root level
- **Virtual environment**: Always activate the venv before installing dependencies
- **Java requirement**: Required for Owlready2 reasoners (HermiT, Pellet)
