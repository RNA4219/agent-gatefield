#!/bin/bash
# Production Setup Script for agent-gatefield
# PostgreSQL + pgvector installation and configuration

set -e

echo "=== agent-gatefield Production Setup ==="

# Detect OS
OS=$(uname -s)
case "$OS" in
    Linux*)     PLATFORM="linux";;
    Darwin*)    PLATFORM="macos";;
    MINGW*|MSYS*|CYGWIN*)  PLATFORM="windows";;
    *)          PLATFORM="unknown";;
esac

echo "Platform: $PLATFORM"

# Configuration
DB_NAME="gatefield"
DB_USER="gatefield"
DB_PASSWORD="${POSTGRES_PASSWORD:-gatefield_prod_password}"
DB_PORT="${POSTGRES_PORT:-5432}"

# Step 1: Check PostgreSQL installation
echo ""
echo "Step 1: Checking PostgreSQL installation..."

if command -v psql &> /dev/null; then
    PG_VERSION=$(psql --version | head -1)
    echo "Found: $PG_VERSION"
else
    echo "PostgreSQL not found. Please install PostgreSQL 16+ first."
    echo ""
    echo "Installation options:"
    echo "  - Docker: docker compose up -d"
    echo "  - Linux: sudo apt install postgresql-16"
    echo "  - macOS: brew install postgresql@16"
    echo "  - Windows: winget install PostgreSQL.PostgreSQL.17"
    exit 1
fi

# Step 2: Check pgvector extension
echo ""
echo "Step 2: Checking pgvector extension..."

PGVECTOR_CHECK=$(psql -U postgres -c "SELECT 1 FROM pg_extension WHERE extname='vector'" 2>/dev/null || echo "0")

if [[ "$PGVECTOR_CHECK" == *"1"* ]]; then
    echo "pgvector extension already installed"
else
    echo "pgvector extension not found. Installing..."

    if [[ "$PLATFORM" == "linux" ]]; then
        # Linux: install from package or compile
        if command -v apt-get &> /dev/null; then
            sudo apt-get update
            sudo apt-get install -y postgresql-16-vector || {
                echo "Package not available, compiling from source..."
                # Clone and compile pgvector
                cd /tmp
                git clone --branch v0.7.4 https://github.com/pgvector/pgvector.git
                cd pgvector
                make
                sudo make install
            }
        fi
    elif [[ "$PLATFORM" == "macos" ]]; then
        # macOS: use Homebrew
        brew install pgvector || {
            echo "Compiling from source..."
            cd /tmp
            git clone --branch v0.7.4 https://github.com/pgvector/pgvector.git
            cd pgvector
            make
            make install
        }
    elif [[ "$PLATFORM" == "windows" ]]; then
        echo ""
        echo "For Windows, pgvector requires manual compilation or pre-built DLLs."
        echo "Options:"
        echo "  1. Use Docker with pgvector/pgvector image (recommended)"
        echo "  2. Download pre-built DLLs from:"
        echo "     https://github.com/pgvector/pgvector/releases"
        echo "  3. Compile using Visual Studio (see pgvector docs)"
        echo ""
        echo "For now, the system will use mock mode for testing."
        echo "To enable real PostgreSQL:"
        echo "  pip install psycopg2-binary pgvector"
        echo "  Copy vector.dll to PostgreSQL lib directory"
        echo "  Copy vector.control and vector--0.7.4.sql to share/extension"
    fi
fi

# Step 3: Create database and user
echo ""
echo "Step 3: Creating database and user..."

# Check if database exists
DB_EXISTS=$(psql -U postgres -lqt | cut -d \| -f 1 | grep -w "$DB_NAME" || echo "")

if [[ -z "$DB_EXISTS" ]]; then
    echo "Creating database: $DB_NAME"
    psql -U postgres -c "CREATE DATABASE $DB_NAME;"
else
    echo "Database $DB_NAME already exists"
fi

# Check if user exists
USER_EXISTS=$(psql -U postgres -c "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -c "1" || echo "0")

if [[ "$USER_EXISTS" == "0" ]]; then
    echo "Creating user: $DB_USER"
    psql -U postgres -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"
    psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
else
    echo "User $DB_USER already exists"
fi

# Step 4: Apply schema
echo ""
echo "Step 4: Applying database schema..."

psql -U "$DB_USER" -d "$DB_NAME" -f src/vector_store/schema.sql || {
    echo "Schema application failed. Trying with postgres user..."
    psql -U postgres -d "$DB_NAME" -f src/vector_store/schema.sql
}

# Step 5: Initialize pgvector extension
echo ""
echo "Step 5: Initializing pgvector extension..."

psql -U "$DB_USER" -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;" || {
    psql -U postgres -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;"
}

# Apply extension init script
if [[ -f "scripts/init-extensions.sql" ]]; then
    psql -U "$DB_USER" -d "$DB_NAME" -f scripts/init-extensions.sql || true
fi

# Step 6: Verify setup
echo ""
echo "Step 6: Verifying setup..."

psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT extname, extversion FROM pg_extension WHERE extname='vector';" || echo "Extension check skipped"
psql -U "$DB_USER" -d "$DB_NAME" -c "\dt" | head -20

# Step 7: Set environment
echo ""
echo "Step 7: Setting environment variables..."

echo ""
echo "Add the following to your .env file or environment:"
echo "  DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:$DB_PORT/$DB_NAME"
echo ""

# Write .env file
cat > .env << EOF
DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@localhost:${DB_PORT}/${DB_NAME}
POSTGRES_USER=${DB_USER}
POSTGRES_PASSWORD=${DB_PASSWORD}
POSTGRES_DB=${DB_NAME}
POSTGRES_PORT=${DB_PORT}
EOF

echo "Created .env file"

# Step 8: Install Python dependencies
echo ""
echo "Step 8: Installing Python dependencies..."

pip install psycopg2-binary pgvector || pip install psycopg2-binary

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To test the connection:"
echo "  python -c \"from src.vector_store import VectorStore; vs = VectorStore('postgresql://$DB_USER:$DB_PASSWORD@localhost/$DB_NAME'); print('Connected!')\""
echo ""
echo "To run the CLI:"
echo "  python -m cli.gate_cli dry-run --run-id test-001"
echo ""