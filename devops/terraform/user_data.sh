#!/bin/bash
# ==========================================
# EC2 User Data Script
# Runs on first boot to configure the server
# ==========================================

set -e

# Configuration from Terraform
DOCKER_IMAGE="${docker_image}"
JWT_SECRET_KEY="${jwt_secret_key}"
ADMIN_PASSWORD_HASH="${admin_password_hash}"
CORS_ORIGINS="${cors_origins}"
DOMAIN_NAME="${domain_name}"

# Logging
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1
echo "Starting EC2 initialization..."

# Update system
apt-get update
apt-get upgrade -y

# Install Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Start Docker
systemctl start docker
systemctl enable docker

# Create application directory
mkdir -p /opt/resume-intelligence/data
chmod 755 /opt/resume-intelligence/data

# Create environment file (NEVER commit this)
cat > /opt/resume-intelligence/.env <<EOF
# Application Configuration
ENVIRONMENT=production
DATABASE_PATH=/opt/resume-intelligence/data/resume_db.sqlite

# Authentication (CHANGE THESE)
JWT_SECRET_KEY=${JWT_SECRET_KEY}
ADMIN_PASSWORD_HASH=${ADMIN_PASSWORD_HASH}
ADMIN_USERNAME=admin

# CORS - Set to your frontend URL
CORS_ORIGINS=${CORS_ORIGINS}

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_UPLOAD_REQUESTS=10
RATE_LIMIT_MATCH_REQUESTS=20

# File Upload Limits
MAX_FILE_SIZE_MB=10
MAX_BATCH_SIZE=20
MAX_PDF_PAGES=50
EOF

chmod 600 /opt/resume-intelligence/.env

# Pull Docker image
docker pull ${DOCKER_IMAGE}

# Run application with Docker
docker run -d \
  --name resume-intelligence \
  --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -v /opt/resume-intelligence/data:/app/backend/data \
  --env-file /opt/resume-intelligence/.env \
  ${DOCKER_IMAGE}

# Install Nginx
apt-get install -y nginx

# Configure Nginx reverse proxy
cat > /etc/nginx/sites-available/resume-intelligence <<'NGINX'
# Upstream: FastAPI application
upstream resume_app {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name _;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
    gzip_min_length 256;

    # Max upload size
    client_max_body_size 50M;

    # Proxy to FastAPI
    location / {
        proxy_pass http://resume_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_read_timeout 120s;
        proxy_connect_timeout 10s;
    }

    # Static files caching
    location /static/ {
        proxy_pass http://resume_app/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    # Health check - no logging
    location /api/health {
        proxy_pass http://resume_app/api/health;
        access_log off;
    }

    # Deny hidden files
    location ~ /\. {
        deny all;
        return 404;
    }
}
NGINX

# Enable site
ln -sf /etc/nginx/sites-available/resume-intelligence /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test and restart Nginx
nginx -t && systemctl restart nginx
systemctl enable nginx

# Configure firewall
apt-get install -y ufw
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Wait for application to start
echo "Waiting for application to start..."
sleep 30

# Health check
for i in {1..10}; do
    if curl -sf http://localhost:8000/api/health > /dev/null; then
        echo "Application is healthy!"
        break
    fi
    echo "Waiting for application... attempt $i"
    sleep 5
done

echo "EC2 initialization complete!"
