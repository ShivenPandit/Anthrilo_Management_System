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

1. Clone the repository
```bash
git clone <repository-url>
cd "Anthrilo Management System"
```

2. Run setup script
```powershell
.\setup.ps1
```

3. Follow the instructions to:
   - Setup PostgreSQL database
   - Start backend server
   - Start frontend server

For detailed instructions, see [QUICKSTART.md](QUICKSTART.md) or [MANUAL_SETUP.md](MANUAL_SETUP.md)

### Access Points

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

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

## Documentation

- [Quick Start Guide](QUICKSTART.md) - Get up and running quickly
- [Manual Setup Guide](MANUAL_SETUP.md) - Detailed installation and configuration
- [Implementation Status](IMPLEMENTATION_STATUS.md) - Current development progress
- [Phase 1 Complete](PHASE_1_COMPLETE.md) - Reports & Analytics implementation

## License

Proprietary - Anthrilo Management System
