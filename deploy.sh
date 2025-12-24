#!/bin/bash
# Deploy Google Calendar MCP to cloud server
# Usage: ./deploy.sh

set -e

SERVER="root@157.173.109.132"
APP_DIR="~/apps/google-calendar-mcp"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Google Calendar MCP Deployment ==="
echo ""

# Check if .env exists
if [ ! -f "$LOCAL_DIR/.env" ]; then
    echo "ERROR: .env file not found!"
    echo "Copy .env.example to .env and fill in values"
    exit 1
fi

echo "Step 1: Creating directories on server..."
ssh $SERVER "mkdir -p $APP_DIR/{credentials/work,credentials/personal,data}"

echo "Step 2: Copying files to server..."
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
    --exclude '.venv' --exclude '.env' --exclude 'credentials/*' \
    "$LOCAL_DIR/" "$SERVER:$APP_DIR/"

echo "Step 3: Copying .env file..."
scp "$LOCAL_DIR/.env" "$SERVER:$APP_DIR/.env"

echo "Step 4: Creating database (if not exists)..."
ssh $SERVER "docker exec travel-postgres psql -U travel -tc \"SELECT 1 FROM pg_database WHERE datname = 'google_calendar_mcp'\" | grep -q 1 || docker exec travel-postgres psql -U travel -c 'CREATE DATABASE google_calendar_mcp'"

echo "Step 5: Initializing database schema..."
ssh $SERVER "docker exec -i travel-postgres psql -U travel -d google_calendar_mcp < $APP_DIR/src/google_calendar/db/schema.sql" || echo "Schema may already exist"

echo "Step 6: Building and starting container..."
ssh $SERVER "cd $APP_DIR && docker compose build && docker compose up -d"

echo "Step 7: Checking container health..."
sleep 5
ssh $SERVER "docker ps | grep google-calendar-mcp"
ssh $SERVER "curl -s http://localhost:8005/health" || echo "Health check pending..."

echo ""
echo "=== Deployment complete ==="
echo ""
echo "To migrate data from local SQLite:"
echo "  python scripts/migrate_sqlite_to_postgres.py > gc_data.sql"
echo "  scp gc_data.sql $SERVER:$APP_DIR/"
echo "  ssh $SERVER 'docker exec -i travel-postgres psql -U travel -d google_calendar_mcp < $APP_DIR/gc_data.sql'"
echo ""
echo "To authorize accounts, visit:"
echo "  https://mcp-serv.duckdns.org/mcp/calendar/oauth/start/work"
echo "  https://mcp-serv.duckdns.org/mcp/calendar/oauth/start/personal"
echo ""
echo "To view logs:"
echo "  ssh $SERVER 'docker logs -f google-calendar-mcp'"
