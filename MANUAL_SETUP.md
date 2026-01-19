# Manual Setup Guide (Without Docker)

## Prerequisites

1. **Python 3.11+**
   - Download from [python.org](https://www.python.org/downloads/)
   - Verify: `python --version`

2. **PostgreSQL 15+**
   - Download from [postgresql.org](https://www.postgresql.org/download/windows/)
   - Remember the password you set during installation

3. **Redis** (Optional but recommended)
   - Download from [redis.io](https://redis.io/download/)
   - For Windows: Use [Memurai](https://www.memurai.com/) or [WSL](https://docs.microsoft.com/en-us/windows/wsl/install)

4. **Node.js 18+**
   - Download from [nodejs.org](https://nodejs.org/)
   - Verify: `node --version`

## Step 1: Database Setup

### Create PostgreSQL Database

Open PowerShell or Command Prompt:

```powershell
# Connect to PostgreSQL (use your postgres password)
psql -U postgres

# In PostgreSQL prompt, run:
CREATE USER anthrilo_user WITH PASSWORD 'anthrilo_pass_dev';
CREATE DATABASE anthrilo_db OWNER anthrilo_user;
GRANT ALL PRIVILEGES ON DATABASE anthrilo_db TO anthrilo_user;
\q
```

### Start Redis (Optional)

If you installed Memurai:
```powershell
# Redis should start automatically with Windows
# Or start manually from Services
```

If using WSL:
```powershell
wsl
sudo service redis-server start
```

## Step 2: Backend Setup

```powershell
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\activate

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start the backend server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The backend will be running at:
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Step 3: Frontend Setup

Open a **new PowerShell window**:

```powershell
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```

The frontend will be running at:
- **Application**: http://localhost:3000

## Step 4: Verify Installation

1. **Check Backend**:
   - Open http://localhost:8000/docs
   - You should see the Swagger UI with all API endpoints

2. **Check Frontend**:
   - Open http://localhost:3000
   - You should see the Anthrilo landing page

3. **Test Reports**:
   - Navigate to http://localhost:3000/dashboard/reports
   - All report pages should load (initially with empty data)

## Common Issues & Solutions

### Issue: PostgreSQL connection error

**Error**: `could not connect to server`

**Solution**:
```powershell
# Check if PostgreSQL is running
Get-Service -Name postgresql*

# Start PostgreSQL if stopped
Start-Service postgresql-x64-15  # Adjust version number
```

### Issue: Port already in use

**Error**: `Address already in use`

**Solution**:
```powershell
# Find process using port 8000 or 3000
netstat -ano | findstr :8000
netstat -ano | findstr :3000

# Kill the process (replace PID with actual number)
taskkill /PID <PID> /F
```

### Issue: Redis connection error

**Solution**: Redis is optional for development. If you don't have Redis, you can comment out Redis-related code or the backend will run without caching.

### Issue: Python package installation fails

**Solution**:
```powershell
# Try installing packages one by one
pip install fastapi uvicorn sqlalchemy alembic psycopg2-binary python-dotenv pydantic pydantic-settings

# Skip optional packages like prophet if they fail
```

## Development Workflow

### Backend Development

```powershell
# Activate virtual environment (if not already active)
cd backend
.\venv\Scripts\activate

# Run backend
uvicorn app.main:app --reload

# Create new migration (after model changes)
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Run tests
pytest
```

### Frontend Development

```powershell
# Run development server
cd frontend
npm run dev

# Build for production
npm run build

# Run linting
npm run lint
```

## Stopping Services

### Stop Backend
- Press `Ctrl+C` in the backend terminal
- Deactivate virtual environment: `deactivate`

### Stop Frontend
- Press `Ctrl+C` in the frontend terminal

### Stop PostgreSQL (if needed)
```powershell
Stop-Service postgresql-x64-15
```

### Stop Redis (if needed)
```powershell
# If using Memurai, stop from Services app
# If using WSL:
wsl
sudo service redis-server stop
```

## Quick Start Commands (After Initial Setup)

### Terminal 1 - Backend:
```powershell
cd backend
.\venv\Scripts\activate
uvicorn app.main:app --reload
```

### Terminal 2 - Frontend:
```powershell
cd frontend
npm run dev
```

## Environment Files Created

✅ `backend/.env` - Backend configuration
✅ `frontend/.env.local` - Frontend configuration

These files have been created with development defaults. Update them if needed.

## Next Steps

1. **Add Sample Data**: Use the API docs (http://localhost:8000/docs) to create sample:
   - Yarns
   - Fabrics
   - Garments
   - Inventory items

2. **Explore Reports**: Navigate through the reports dashboard at http://localhost:3000/dashboard/reports

3. **Review API**: Check all available endpoints at http://localhost:8000/docs

## Production Deployment

For production deployment with Docker, install Docker Desktop and use `docker-compose.yml`.
