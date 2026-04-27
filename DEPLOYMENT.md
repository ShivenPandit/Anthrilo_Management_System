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

Advanced update modes:

```bash
# Update and rebuild images (default behavior)
ACTION=update ./scripts/deploy_vps.sh

# Fast restart without rebuild
ACTION=restart ./scripts/deploy_vps.sh

# Update without image rebuild
ACTION=update NO_BUILD=1 ./scripts/deploy_vps.sh

# After update, force cache reset + warm critical dashboards (enabled by default)
RUN_POST_DEPLOY_FIXES=1 ./scripts/deploy_vps.sh

# Trigger full historical backfill in background after deploy
RUN_FULL_BACKFILL=1 BACKFILL_FROM_DATE=2024-01-01 BACKFILL_TO_DATE=2026-04-27 ./scripts/deploy_vps.sh

# Trigger repair rebuild (sales + returns + inventory) in background after deploy
RUN_REPAIR_REBUILD=1 REPAIR_FROM_DATE=2024-01-01 REPAIR_TO_DATE=2026-04-27 REPAIR_ENTITIES=sales,returns,inventory REPAIR_TRUNCATE_PERIOD=1 REPAIR_FULL_INVENTORY_DISCOVERY=1 ./scripts/deploy_vps.sh
```

By default, deploy script now does the following in order:

- Starts or updates Docker services
- Waits for backend health on `/health`
- Resets Unicommerce cache using `/api/v1/integrations/unicommerce/cache/reset?warm=true`
- Optionally triggers `/api/v1/integrations/unicommerce/sync/profile/full_backfill`
- Optionally triggers `/api/v1/integrations/unicommerce/sync/repair/rebuild`

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

## 9) Repair/Rebuild Runbook (DB-first)

Use repair/rebuild when DB-first parity drifts from export snapshots, after major sync bugs, or during controlled historical rebuilds.

### 9.1 Safety-first execution steps

1. Start with reconciliation only:
   - `python scripts/reconcile_sales_export_vs_db.py --from-date 2026-04-01 --to-date 2026-04-07 --closed-window-mode --thresholds revenue=1,orders=1,items=1`
2. Run repair in dry-run mode (no writes/truncates):
   - `curl -X POST "http://127.0.0.1:8000/api/v1/integrations/unicommerce/sync/repair/rebuild?from_date=2026-04-01&to_date=2026-04-07&entities=sales,returns,inventory&truncate_period=false&truncate_inventory=false&full_inventory_discovery=false&dry_run=true&run_in_background=false"`
3. Execute real repair without truncate first:
   - keep `truncate_period=false` and `truncate_inventory=false`.
4. Reconcile again; only use truncate mode if drift still persists and root cause is understood.

Validation rules:
- Always validate closed windows only (current IST day is excluded by default).
- Never use today for parity pass/fail decisions.
- Business timezone for parity and reconciliation is IST (`Asia/Kolkata`).
- Expected closed-window drift should remain under 1% for revenue/orders/items.

### 9.2 Staged rollout strategy

- Week 1: repair only 7-day windows (`from_date=today-7`) and verify reconciliation daily.
- Month 1: expand to 30-day windows once week-level drift remains under threshold.
- Full history: run larger windows or full range only after 30-day parity is stable.

### 9.3 Truncate mode warning

`truncate_period=true` deletes `sales_orders` and `sales_returns` rows in the selected window before rebuild.  
`truncate_inventory=true` clears all `inventory_snapshots` before inventory rebuild.  
Use truncate only in low-traffic windows with rollback/recovery plans.

### 9.4 Progress tracking

When `run_in_background=true`, the repair endpoint returns a `progress_key`. Poll:

```bash
curl "http://127.0.0.1:8000/api/v1/integrations/unicommerce/sync/repair/rebuild/progress?progress_key=<progress_key>"
```

## 10) Rollback

```bash
git log --oneline -n 20
git checkout <previous-good-commit>
./scripts/deploy_vps.sh
```

## 11) Important note about localhost fallback

Next.js public env vars are build-time values. If NEXT_PUBLIC_API_URL or NEXT_PUBLIC_WS_URL are wrong while building, the built frontend can point to localhost.

Always verify .env.prod and frontend/.env.local before running deployment.
