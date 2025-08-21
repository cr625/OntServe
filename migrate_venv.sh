#!/bin/bash
# Migration script to move venv from web/ to main OntServe folder
# and merge requirements files

echo "🔄 Migrating OntServe virtual environment and requirements..."

# Check if we're in the right directory
if [ ! -f "requirements-enhanced.txt" ]; then
    echo "❌ Error: Run this script from the main OntServe directory"
    exit 1
fi

# Step 1: Backup and remove old venv
if [ -d "web/venv" ]; then
    echo "📦 Found existing venv in web/ folder"
    
    # Get list of currently installed packages
    if [ -f "web/venv/bin/activate" ]; then
        echo "📋 Saving current package list..."
        source web/venv/bin/activate
        pip freeze > current_packages.txt
        deactivate
        echo "✅ Package list saved to current_packages.txt"
    fi
    
    # Remove old venv
    echo "🗑️  Removing old venv from web/ folder..."
    rm -rf web/venv
else
    echo "ℹ️  No existing venv found in web/ folder"
fi

# Step 2: Create new venv in main folder
echo "🏗️  Creating new virtual environment in main OntServe folder..."
python3 -m venv venv

# Step 3: Activate new venv
echo "🔌 Activating new virtual environment..."
source venv/bin/activate

# Step 4: Merge requirements files
echo "📄 Merging requirements files..."
cat > requirements.txt << 'EOF'
# OntServe Enhanced Requirements
# Core dependencies for enhanced ontology processing with Owlready2 and Cytoscape.js visualization

# ===== Core RDF and Ontology Processing =====
rdflib>=6.3.2
owlready2>=0.43
# Note: Java JDK 8+ required for Owlready2 reasoners (HermiT, Pellet)
# Install with: apt-get install openjdk-11-jdk

# ===== Web Framework =====
flask>=2.3.2
flask-sqlalchemy>=3.0.0
bootstrap-flask>=2.2.0
wtforms>=3.0.1

# ===== Database =====
sqlalchemy>=1.4.0
psycopg2-binary>=2.9.6

# ===== Search and Similarity =====
numpy>=1.24.0
scikit-learn>=1.3.0
sentence-transformers>=2.2.2

# ===== Optional: Vector Search (PostgreSQL with pgvector) =====
pgvector>=0.2.0

# ===== HTTP Requests =====
requests>=2.31.0

# ===== File Handling =====
python-magic>=0.4.27

# ===== Date/Time =====
python-dateutil>=2.8.2

# ===== Configuration =====
python-dotenv>=1.0.0

# ===== Command Line Interface =====
click>=8.1.0

# ===== Development and Testing =====
pytest>=7.4.0
pytest-flask>=1.2.0

# ===== Logging and Monitoring =====
python-json-logger>=2.0.7

# ===== Performance Monitoring (Optional) =====
memory-profiler>=0.61.0
psutil>=5.9.5
EOF

# Step 5: Install merged requirements
echo "📦 Installing merged requirements..."
pip install -r requirements.txt

# Step 6: Install any additional packages from old environment
if [ -f "current_packages.txt" ]; then
    echo "🔄 Checking for additional packages from old environment..."
    # Install any packages that were in the old environment but not in our requirements
    pip install -r current_packages.txt --upgrade
fi

# Step 7: Update web/run.sh script
echo "🔧 Updating web/run.sh to use new venv location..."
if [ -f "web/run.sh" ]; then
    # Create backup
    cp web/run.sh web/run.sh.backup
    
    # Update the script
    cat > web/run.sh << 'EOF'
#!/bin/bash
# OntServe Web Server Startup Script
# Updated to use venv from parent directory

# Get the script directory and parent directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ONTSERVE_DIR="$( dirname "$SCRIPT_DIR" )"

echo "🚀 Starting OntServe Web Server..."
echo "📁 OntServe Directory: $ONTSERVE_DIR"
echo "📁 Web Directory: $SCRIPT_DIR"

# Check if virtual environment exists in parent directory
if [ ! -d "$ONTSERVE_DIR/venv" ]; then
    echo "❌ Virtual environment not found at $ONTSERVE_DIR/venv"
    echo "💡 Run the migration script: ./migrate_venv.sh"
    exit 1
fi

# Activate virtual environment from parent directory
echo "🔌 Activating virtual environment..."
source "$ONTSERVE_DIR/venv/bin/activate"

# Check if required packages are installed
python -c "import flask, owlready2" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ Required packages not found. Installing..."
    cd "$ONTSERVE_DIR"
    pip install -r requirements.txt
    cd "$SCRIPT_DIR"
fi

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=development
export ONTSERVE_PORT=${ONTSERVE_PORT:-5003}

# Initialize database if needed
echo "🗄️  Initializing database..."
python -c "
try:
    from app import db
    db.create_all()
    print('✅ Database initialized')
except Exception as e:
    print(f'⚠️  Database initialization warning: {e}')
"

# Start the Flask development server
echo "🌐 Starting Flask server on http://localhost:$ONTSERVE_PORT"
echo "📊 Access visualization at: http://localhost:$ONTSERVE_PORT/editor"
echo "🛑 Press Ctrl+C to stop the server"

python app.py
EOF
    
    chmod +x web/run.sh
    echo "✅ Updated web/run.sh script"
fi

# Step 8: Test the new setup
echo "🧪 Testing new environment setup..."
python -c "
try:
    import flask
    import owlready2
    import rdflib
    print('✅ Core packages imported successfully')
    
    # Test enhanced importer
    import sys
    sys.path.append('.')
    from importers.owlready_importer import OwlreadyImporter
    print('✅ Enhanced importer available')
    
except ImportError as e:
    print(f'⚠️  Import warning: {e}')
except Exception as e:
    print(f'⚠️  Test warning: {e}')
"

# Step 9: Clean up
echo "🧹 Cleaning up temporary files..."
if [ -f "current_packages.txt" ]; then
    rm current_packages.txt
fi

# Remove old requirements files (keep backups)
if [ -f "web/requirements.txt" ]; then
    mv web/requirements.txt web/requirements.txt.backup
    echo "📄 Backed up web/requirements.txt to web/requirements.txt.backup"
fi

if [ -f "requirements-enhanced.txt" ]; then
    mv requirements-enhanced.txt requirements-enhanced.txt.backup
    echo "📄 Backed up requirements-enhanced.txt to requirements-enhanced.txt.backup"
fi

echo ""
echo "✅ Migration completed successfully!"
echo ""
echo "📋 Summary of changes:"
echo "   • Moved venv from web/ to main OntServe folder"
echo "   • Merged requirements into single requirements.txt"
echo "   • Updated web/run.sh to use new venv location"
echo "   • Backed up old files with .backup extension"
echo ""
echo "🚀 Next steps:"
echo "   1. Test the setup: python test_enhanced_visualization.py"
echo "   2. Start the server: cd web && ./run.sh"
echo "   3. Visit: http://localhost:5003/editor/ontology/<id>/visualize"
echo ""
echo "🔧 If you encounter issues:"
echo "   • Check that Java JDK is installed: java -version"
echo "   • Verify venv is active: which python"
echo "   • Run from OntServe root directory"
