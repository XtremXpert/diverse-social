#!/bin/bash
set -e

# Jitsi Meet Self-Hosted Installation Script
# For Odoo social_calling module - Loi 25 compliant

echo "=== Jitsi Meet Installer ==="
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "Docker not found. Installing..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    echo "Docker installed. Please log out and back in, then re-run this script."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "Docker Compose not found. Installing..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# Create config directory
CONFIG_DIR="${HOME}/.jitsi-meet-cfg"
mkdir -p ${CONFIG_DIR}/web
mkdir -p ${CONFIG_DIR}/prosody
mkdir -p ${CONFIG_DIR}/jicofo
mkdir -p ${CONFIG_DIR}/jvb

# Create Docker network
docker network inspect meet.jitsi &>/dev/null || docker network create meet.jitsi

# Generate secure passwords if not set
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    
    # Generate random passwords
    JICOFO_PASS=$(openssl rand -hex 16)
    JICOFO_SECRET=$(openssl rand -hex 16)
    JVB_PASS=$(openssl rand -hex 16)
    
    sed -i "s/CHANGE_ME_JICOFO_PASS/${JICOFO_PASS}/g" .env
    sed -i "s/CHANGE_ME_JICOFO_SECRET/${JICOFO_SECRET}/g" .env
    sed -i "s/CHANGE_ME_JVB_PASS/${JVB_PASS}/g" .env
    
    echo ""
    echo "=== IMPORTANT ==="
    echo "Edit .env and set:"
    echo "  - JITSI_DOMAIN (your domain, e.g., meet.yourdomain.com)"
    echo "  - DOCKER_HOST_ADDRESS (your server public IP)"
    echo ""
    echo "Then run: docker-compose up -d"
    echo ""
    exit 0
fi

echo "Starting Jitsi Meet..."
docker-compose up -d

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Jitsi Meet is running at:"
echo "  - HTTP:  http://localhost:${HTTP_PORT:-8000}"
echo "  - HTTPS: https://localhost:${HTTPS_PORT:-8443}"
echo ""
echo "To use with Odoo:"
echo "  1. Update 'jitsi_server' field in Odoo to: ${JITSI_DOMAIN:-meet.yourdomain.com}"
echo "  2. If using self-signed cert, accept it in browser first"
echo ""
echo "Create a user for room creation:"
echo "  docker-compose exec prosody prosodyctl --config /config/prosody.cfg.lua register focus auth.meet.jitsi focuspassword"
echo ""
echo "View logs: docker-compose logs -f"
echo ""
