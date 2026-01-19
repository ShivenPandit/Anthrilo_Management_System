# Quick Start Guide

## Prerequisites

1. **Python 3.11+** - [Download](https://www.python.org/downloads/)
2. **PostgreSQL 15+** - [Download](https://www.postgresql.org/download/windows/)
3. **Node.js 18+** - [Download](https://nodejs.org/)
4. **Redis** (optional) - [Memurai](https://www.memurai.com/) or WSL

## Setup PostgreSQL Database

```powershell
# Connect to PostgreSQL
psql -U postgres

# Create database and user
CREATE USER anthrilo_user WITH PASSWORD 'anthrilo_pass_dev';
CREATE DATABASE anthrilo_db OWNER anthrilo_user;
GRANT ALL PRIVILEGES ON DATABASE anthrilo_db TO anthrilo_user;
\q
```

## Quick Setup

### Option 1: Using PowerShell Script (Recommended)

```powershell
.\setup.ps1
```

This will create environment files and show you the next steps.

### Option 2: Manual Setup

1. **Create environment files:**
   ```powershell
   Copy-Item backend\.env.example backend\.env
   Copy-Item frontend\.env.local.example frontend\.env.local
   ```

2. **Setup Backend** (Terminal 1):
   ```powershell
   cd backend
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   alembic upgrade head
   uvicorn app.main:app --reload
   ```

3. **Setup Frontend** (Terminal 2):
   ```powershell
   cd frontend
   npm install
   npm run dev
   ```


## Accessing the Application

- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8000
- **API Documentation:** http://localhost:8000/docs
- **Alternative API Docs:** http://localhost:8000/redoc

## Common Development Commands

### Backend (in backend directory with venv activated)

**Create new migration:**
```powershell
alembic revision --autogenerate -m "description"
```

**Apply migrations:**
```powershell
alembic upgrade head
```

**Run tests:**
```powershell
pytest
```

**Access database:**
```powershell
psql -U anthrilo_user -d anthrilo_db
```

### Frontend (in frontend directory)

**Install packages:**
```powershell
npm install <package-name>
```

**Build for production:**
```powershell
npm run build
```

**Run linting:**
```powershell
npm run lint
```

## Stopping Services

**Stop Backend:** Press `Ctrl+C` in backend terminal

**Stop Frontend:** Press `Ctrl+C` in frontend terminal

**Deactivate Python venv:**
```powershell
deactivate
```

## Project Structure

```
.
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── api/            # API endpoints
│   │   ├── core/           # Configuration
│   │   ├── db/             # Database models
│   │   ├── services/       # Business logic
│   │   └── schemas/        # Pydantic schemas
│   ├── alembic/            # Database migrations
│   └── tests/              # Backend tests
├── frontend/               # Next.js frontend
│   └── src/
│       ├── app/            # Next.js app directory
│       ├── components/     # React components
│       ├── lib/            # Utilities
│       └── types/          # TypeScript types
└── MANUAL_SETUP.md         # Detailed setup guide
```

## Troubleshooting

### Port already in use:
```powershell
# Find process using port 3000 or 8000
netstat -ano | findstr :3000
netstat -ano | findstr :8000

# Kill process by PID
taskkill /PID <PID> /F
```

### PostgreSQL connection error:
```powershell
# Check PostgreSQL status
Get-Service -Name postgresql*

# Start PostgreSQL
Start-Service postgresql-x64-15
```

### Reset database:
```powershell
# Drop and recreate database
psql -U postgres
DROP DATABASE anthrilo_db;
CREATE DATABASE anthrilo_db OWNER anthrilo_user;
\q

# Re-run migrations
cd backend
.\venv\Scripts\activate
alembic upgrade head
```

### Python package installation fails:
```powershell
# Upgrade pip first
python -m pip install --upgrade pip

# Try installing core packages only
pip install fastapi uvicorn sqlalchemy alembic psycopg2-binary
```

## For More Details

See [MANUAL_SETUP.md](MANUAL_SETUP.md) for comprehensive setup instructions and troubleshooting.
