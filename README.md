# Anthrilo Management System

Enterprise-grade ERP system for textile manufacturing and garment production management.

## Architecture

- **Frontend**: Next.js 14 + TypeScript + React
- **Backend**: FastAPI + Python 3.11
- **Database**: PostgreSQL 15
- **Cache**: Redis 7 (optional)

## Modules

### I. Raw Material & Processing Module
- Yarn Management (types, composition, percentages)
- Process Management (knitting, dyeing, finishing, printing)
- Fabric Management (jersey, terry, fleece with GSM tracking)
- Reports: Fabric stock sheets, order sheets, cost sheets

### II. Garment & Sales Module
- Garment Master Data (SKU, sizes, MRP, categories)
- Inventory Management (good/virtual stock)
- Sales & Panel Management (daily sales/returns)
- Production Planning & Tracking
- Reports: Slow/fast moving, panel-wise, production plans

### III. Financial & Marketing Module
- Discounts & Rebates Management
- Paid Ads Tracking & ROI Analysis
- Settlement Reports
- Listing Performance Metrics

## Quick Start

### Prerequisites
- **Python 3.11+** - [Download](https://www.python.org/downloads/)
- **PostgreSQL 15+** - [Download](https://www.postgresql.org/download/)
- **Node.js 18+** - [Download](https://nodejs.org/)
- **Redis** (optional) - [Download](https://redis.io/)

### Setup

#### 1️⃣ Database Setup

Create a PostgreSQL database:
```sql
CREATE DATABASE anthrilo_db;
CREATE USER anthrilo_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE anthrilo_db TO anthrilo_user;
```

#### 2️⃣ Backend Setup

```powershell
# Navigate to backend
cd backend

# Install dependencies
pip install uvicorn fastapi pydantic-settings sqlalchemy psycopg2-binary python-dotenv email-validator python-jose[cryptography] passlib[bcrypt]

# Create .env file with:
# DATABASE_URL=postgresql://anthrilo_user:your_password@localhost/anthrilo_db
# SECRET_KEY=your-secret-key-here

# Run database migrations
python -c "from app.db.base import Base; from app.db.session import engine; Base.metadata.create_all(bind=engine)"

# Start backend server
python -m uvicorn app.main:app --reload
```

Backend will run on: **http://127.0.0.1:8000**

#### 3️⃣ Frontend Setup

```powershell
# Navigate to frontend (in new terminal)
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

Frontend will run on: **http://localhost:3000**

### 🚀 Quick Access

- **Frontend Application**: http://localhost:3000
- **Backend API**: http://127.0.0.1:8000
- **API Documentation (Swagger)**: http://127.0.0.1:8000/docs
- **API Documentation (ReDoc)**: http://127.0.0.1:8000/redoc

## Database Migrations

```powershell
# Activate virtual environment
cd backend
.\venv\Scripts\activate

# Create a new migration
alembic revision --autogenerate -m "description"

# Run migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

## Testing

```powershell
# Backend tests
cd backend
.\venv\Scripts\activate
pytest

# Frontend tests
cd frontend
npm test
```

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── api/              # API routes
│   │   ├── core/             # Core config, security
│   │   ├── db/               # Database models & migrations
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── services/         # Business logic & reports
│   │   └── main.py           # FastAPI app
│   ├── alembic/              # Database migrations
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/              # Next.js app directory
│   │   ├── components/       # React components
│   │   ├── lib/              # Utilities & API client
│   │   └── types/            # TypeScript types
│   ├── public/
│   └── package.json
└── README.md

```

## Current Status

| Module | Completion |
|--------|------------|
| Raw Material & Processing | 95% |
| Garment & Sales | 100% ✅ |
| Financial & Marketing | 95% |
| **Reports & Analytics** | **100%** ✅ |
| Database Layer | 100% ✅ |
| API Layer | 100% ✅ |
| **Frontend UI** | **95%** ✅ |
| **Dark Mode** | **100%** ✅ |
| **Overall** | **95%** ✅ |

## License

Proprietary - Anthrilo Management System
