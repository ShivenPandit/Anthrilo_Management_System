# Anthrilo VPS Deployment Guide

This guide makes the repository production-ready for a VPS using Docker Compose.

## 1) VPS prerequisites

- Ubuntu/Debian VPS with sudo access
- Docker Engine + Docker Compose plugin
- Git
- Optional but recommended: nginx + certbot for HTTPS

Install on Ubuntu:

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg git nginx
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
docker --version
docker compose version
```

## 2) Clone and prepare files

```bash
git clone <your-repo-url> anthrilo
cd anthrilo
cp .env.prod.example .env.prod
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local
chmod +x scripts/deploy_vps.sh
```

## 3) Required env values

### 3.1 Root compose env: .env.prod

Set at least:

- NEXT_PUBLIC_API_URL=https://stocknest.cloud
- NEXT_PUBLIC_WS_URL=wss://stocknest.cloud/api/v1/integrations/ws/sales
- ENVIRONMENT=production
- DEBUG=False
- RUN_MIGRATIONS_ON_STARTUP=true

If you use host nginx reverse proxy, keep:

- FRONTEND_BIND=127.0.0.1:3000:3000
- BACKEND_BIND=127.0.0.1:8000:8000

### 3.2 Backend runtime env: backend/.env

Set production values for:

- DATABASE_URL
- SECRET_KEY
- CORS_ORIGINS (include your domain in JSON list format)
- Supabase keys and Unicommerce credentials (if used)
- ENVIRONMENT=production
- DEBUG=False

Example CORS_ORIGINS:

```env
CORS_ORIGINS=["https://stocknest.cloud","https://www.stocknest.cloud"]
```

### 3.3 Frontend runtime env: frontend/.env.local

Set:

- NEXT_PUBLIC_API_URL=https://stocknest.cloud
- NEXT_PUBLIC_WS_URL=wss://stocknest.cloud/api/v1/integrations/ws/sales

## 4) First deployment

```bash
./scripts/deploy_vps.sh
```

What this does:

- Builds fresh backend/frontend images
- Starts Redis, backend, sync_worker, frontend
- Runs Alembic migrations on backend startup
- Prints container status and recent backend logs

## 5) Health checks

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
curl -f http://127.0.0.1:8000/health
```

## 6) Nginx reverse proxy (recommended)

Use the template at deploy/nginx/anthrilo.conf.example and adapt server_name.

```bash
sudo cp deploy/nginx/anthrilo.conf.example /etc/nginx/sites-available/anthrilo
sudo ln -s /etc/nginx/sites-available/anthrilo /etc/nginx/sites-enabled/anthrilo
sudo nginx -t
sudo systemctl reload nginx
```

HTTPS with certbot:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d stocknest.cloud -d www.stocknest.cloud
```

## 7) Update deployment (new commits)

```bash
git pull --ff-only
./scripts/deploy_vps.sh
```

## 8) Useful operations

```bash
# View logs
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f backend
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f sync_worker
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f frontend

# Restart one service
docker compose --env-file .env.prod -f docker-compose.prod.yml restart backend

# Stop stack
docker compose --env-file .env.prod -f docker-compose.prod.yml down
```

## 9) Rollback

```bash
git log --oneline -n 20
git checkout <previous-good-commit>
./scripts/deploy_vps.sh
```

## 10) Important note about localhost fallback

Next.js public env vars are build-time values. If NEXT_PUBLIC_API_URL or NEXT_PUBLIC_WS_URL are wrong while building, the built frontend can point to localhost.

Always verify .env.prod and frontend/.env.local before running deployment.
