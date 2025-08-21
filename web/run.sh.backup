#!/bin/bash

# OntServe Web Interface Startup Script
# Runs on port 8000 to avoid conflicts with proethica (3333) and OntExtract (8765)

echo "Starting OntServe Web Interface..."
echo "================================"
echo "Port: 8000"
echo "Database: OntExtract PostgreSQL (port 5434)"
echo ""

# Change to web directory
cd "$(dirname "$0")"

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install requirements
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Create necessary directories
mkdir -p ../storage/ontologies ../cache

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=development
export DATABASE_URL="postgresql://postgres:PASS@localhost:5434/ontserve_db"

# Run the application
echo ""
echo "Starting Flask application..."
echo "Access the web interface at: http://localhost:8000"
echo ""
python app.py
