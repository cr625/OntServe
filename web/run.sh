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
