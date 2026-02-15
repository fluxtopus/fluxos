#!/bin/bash
# Quick setup script for inkPass
# Sets up the environment and runs initial migrations

set -e

echo "================================"
echo "inkPass Quick Setup"
echo "================================"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}Creating .env file from .env.example...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✓ .env file created${NC}"
    echo -e "${YELLOW}⚠ Please edit .env and update the secrets before production use!${NC}"
    echo ""
else
    echo -e "${GREEN}✓ .env file already exists${NC}"
    echo ""
fi

# Start services
echo -e "${BLUE}Starting Docker services...${NC}"
docker compose up -d

echo -e "${GREEN}✓ Services started${NC}"
echo ""

# Wait for database
echo -e "${BLUE}Waiting for database to be ready...${NC}"
sleep 5

# Run migrations
echo -e "${BLUE}Running database migrations...${NC}"
docker compose exec api alembic upgrade head

echo -e "${GREEN}✓ Migrations complete${NC}"
echo ""

# Show service status
echo -e "${BLUE}Service Status:${NC}"
docker compose ps
echo ""

echo "================================"
echo -e "${GREEN}Setup Complete!${NC}"
echo "================================"
echo ""
echo "inkPass is now running:"
echo "  - API: http://localhost:8002"
echo "  - API Docs: http://localhost:8002/docs"
echo "  - Health: http://localhost:8002/health"
echo ""
echo "Next steps:"
echo "  1. Run health check: ./scripts/health_check.sh"
echo "  2. Run demo: ./scripts/demo_api.sh"
echo "  3. View logs: docker compose logs -f api"
echo ""
