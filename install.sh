#!/bin/bash

# OntServe Installation Script
# This script sets up OntServe with PostgreSQL and all dependencies

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 OntServe Installation Script${NC}"
echo "================================"
echo ""

# Function to print colored messages
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Check system requirements
echo "Checking system requirements..."

# Check Python version
if command -v python3.12 &> /dev/null; then
    PYTHON_CMD=python3.12
    print_status "Python 3.12 found"
elif command -v python3.11 &> /dev/null; then
    PYTHON_CMD=python3.11
    print_status "Python 3.11 found"
elif command -v python3.10 &> /dev/null; then
    PYTHON_CMD=python3.10
    print_status "Python 3.10 found"
else
    print_error "Python 3.10+ is required"
    echo "Please install Python 3.10 or higher:"
    echo "  Ubuntu/Debian: sudo apt install python3.12 python3.12-venv python3.12-dev"
    echo "  Mac: brew install python@3.12"
    exit 1
fi

# Check PostgreSQL
if ! command -v psql &> /dev/null; then
    print_error "PostgreSQL not found"
    echo ""
    echo "Please install PostgreSQL 14+ with pgvector extension:"
    echo ""
    echo "Ubuntu/WSL:"
    echo "  sudo sh -c 'echo \"deb http://apt.postgresql.org/pub/repos/apt \$(lsb_release -cs)-pgdg main\" > /etc/apt/sources.list.d/pgdg.list'"
    echo "  wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -"
    echo "  sudo apt update"
    echo "  sudo apt install -y postgresql-17 postgresql-17-pgvector"
    echo ""
    echo "Mac:"
    echo "  brew install postgresql@17"
    echo "  brew install pgvector"
    echo ""
    exit 1
fi
print_status "PostgreSQL found"

# Check Java (for owlready2 reasoners)
if ! command -v java &> /dev/null; then
    print_warning "Java not found (optional, needed for reasoning)"
    echo "  To enable reasoning, install Java:"
    echo "  Ubuntu/Debian: sudo apt install openjdk-11-jdk"
    echo "  Mac: brew install openjdk@11"
    echo ""
    read -p "Continue without reasoning support? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    print_status "Java found (reasoning enabled)"
fi

echo ""
echo "Setting up OntServe..."
echo ""

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv venv
    print_status "Virtual environment created"
else
    print_status "Virtual environment already exists"
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip --quiet
print_status "Pip upgraded"

# Install dependencies
echo "Installing Python dependencies (this may take a few minutes)..."
pip install -r requirements.txt --quiet
print_status "Dependencies installed"

# Database setup
echo ""
echo "Database Configuration"
echo "====================="
echo ""
echo "We need to set up the PostgreSQL database for OntServe."
echo "Make sure PostgreSQL is running: sudo systemctl status postgresql"
echo ""

# Get database configuration
read -p "PostgreSQL host [localhost]: " DB_HOST
DB_HOST=${DB_HOST:-localhost}

read -p "PostgreSQL port [5432]: " DB_PORT
DB_PORT=${DB_PORT:-5432}

read -p "PostgreSQL superuser (for database creation) [postgres]: " DB_SUPERUSER
DB_SUPERUSER=${DB_SUPERUSER:-postgres}

echo "Enter PostgreSQL superuser password (or press Enter if no password):"
read -s DB_SUPERUSER_PASS

# Generate secure passwords
ONTSERVE_DB_PASS=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
print_status "Generated secure password for ontserve_user"

# Create database and user
echo ""
echo "Creating OntServe database and user..."

export PGPASSWORD=$DB_SUPERUSER_PASS

# Check if database exists
if psql -h $DB_HOST -p $DB_PORT -U $DB_SUPERUSER -lqt | cut -d \| -f 1 | grep -qw ontserve; then
    print_warning "Database 'ontserve' already exists"
    read -p "Drop and recreate it? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        psql -h $DB_HOST -p $DB_PORT -U $DB_SUPERUSER <<EOF
DROP DATABASE IF EXISTS ontserve;
DROP USER IF EXISTS ontserve_user;
EOF
    else
        echo "Using existing database..."
        read -p "Enter password for ontserve_user: " -s ONTSERVE_DB_PASS
        echo
    fi
fi

# Create database and user
psql -h $DB_HOST -p $DB_PORT -U $DB_SUPERUSER <<EOF
-- Create user if not exists
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'ontserve_user') THEN
        CREATE USER ontserve_user WITH PASSWORD '$ONTSERVE_DB_PASS';
    END IF;
END
\$\$;

-- Create database if not exists
SELECT 'CREATE DATABASE ontserve OWNER ontserve_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ontserve')\gexec

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE ontserve TO ontserve_user;
EOF

# Create pgvector extension
psql -h $DB_HOST -p $DB_PORT -U $DB_SUPERUSER -d ontserve <<EOF
CREATE EXTENSION IF NOT EXISTS vector;
EOF

unset PGPASSWORD

print_status "Database 'ontserve' created with pgvector extension"

# Create .env file
echo ""
echo "Creating configuration file..."

cat > .env <<EOF
# OntServe Configuration
# Generated on $(date)

# Database
ONTSERVE_DB_URL=postgresql://ontserve_user:${ONTSERVE_DB_PASS}@${DB_HOST}:${DB_PORT}/ontserve

# Server Ports
ONTSERVE_WEB_PORT=5003
ONTSERVE_MCP_PORT=8083

# Flask Configuration
FLASK_ENV=development
SECRET_KEY=$(openssl rand -hex 32)

# File Storage
UPLOAD_FOLDER=./uploads
MAX_CONTENT_LENGTH=50

# Logging
LOG_LEVEL=INFO
LOG_FILE=ontserve.log
EOF

print_status "Configuration file created (.env)"

# Create necessary directories
mkdir -p uploads logs
print_status "Created upload and log directories"

# Initialize database schema
echo ""
echo "Initializing database schema..."
cd web
export ONTSERVE_DB_URL="postgresql://ontserve_user:${ONTSERVE_DB_PASS}@${DB_HOST}:${DB_PORT}/ontserve"

python -c "
from app import create_app, db
import sys
try:
    app = create_app()
    with app.app_context():
        db.create_all()
        print('✓ Database schema initialized')
except Exception as e:
    print(f'✗ Error: {e}')
    sys.exit(1)
"
cd ..

# Import sample data
echo ""
read -p "Import PROV-O sample ontology? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Importing PROV-O ontology..."
    if [ -f "scripts/import_prov_o.py" ]; then
        python scripts/import_prov_o.py
        print_status "PROV-O ontology imported"
    else
        print_warning "Import script not found at scripts/import_prov_o.py"
    fi
fi

# Create start scripts
echo ""
echo "Creating start scripts..."

# Create web server start script
cat > start-web.sh <<'EOF'
#!/bin/bash
source venv/bin/activate
cd web
python app.py
EOF
chmod +x start-web.sh

# Create MCP server start script
cat > start-mcp.sh <<'EOF'
#!/bin/bash
source venv/bin/activate
python servers/mcp_server.py
EOF
chmod +x start-mcp.sh

# Create combined start script
cat > start-all.sh <<'EOF'
#!/bin/bash
echo "Starting OntServe services..."

# Start MCP server in background
./start-mcp.sh &
MCP_PID=$!
echo "MCP Server started (PID: $MCP_PID)"

# Start web server
./start-web.sh
EOF
chmod +x start-all.sh

print_status "Start scripts created"

# Save credentials
echo ""
echo "Saving credentials..."

cat > credentials.txt <<EOF
OntServe Installation Credentials
=================================
Generated on: $(date)

Database Connection:
-------------------
Host: $DB_HOST
Port: $DB_PORT
Database: ontserve
Username: ontserve_user
Password: $ONTSERVE_DB_PASS

Connection String:
postgresql://ontserve_user:${ONTSERVE_DB_PASS}@${DB_HOST}:${DB_PORT}/ontserve

Web Interface:
--------------
URL: http://localhost:5003
Secret Key: (stored in .env)

MCP API:
--------
URL: http://localhost:8083

IMPORTANT: Keep this file secure and do not commit to version control!
EOF

chmod 600 credentials.txt
print_status "Credentials saved to credentials.txt (keep this secure!)"

# Installation complete
echo ""
echo -e "${GREEN}✅ Installation Complete!${NC}"
echo ""
echo "To start OntServe:"
echo ""
echo "  Option 1 - Start both services:"
echo "    ./start-all.sh"
echo ""
echo "  Option 2 - Start services separately:"
echo "    Terminal 1: ./start-web.sh    # Web interface on http://localhost:5003"
echo "    Terminal 2: ./start-mcp.sh    # MCP API on http://localhost:8083"
echo ""
echo "Default URLs:"
echo "  Web Interface: http://localhost:5003"
echo "  MCP API: http://localhost:8083"
echo ""
echo "Your database credentials are saved in: credentials.txt"
echo "Configuration settings are in: .env"
echo ""
echo "For production deployment, see DEPLOYMENT_PLAN.md"