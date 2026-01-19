from fastapi import APIRouter
from app.api.v1.endpoints import auth, yarns, fabrics, processes, garments, inventory, sales, panels, production, discounts, ads, reports

api_router = APIRouter()

# Authentication
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])

# Module I: Raw Material & Processing
api_router.include_router(yarns.router, prefix="/yarns", tags=["Yarn Management"])
api_router.include_router(processes.router, prefix="/processes", tags=["Process Management"])
api_router.include_router(fabrics.router, prefix="/fabrics", tags=["Fabric Management"])

# Module II: Garment & Sales
api_router.include_router(garments.router, prefix="/garments", tags=["Garment Master Data"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["Inventory Management"])
api_router.include_router(panels.router, prefix="/panels", tags=["Panel Management"])
api_router.include_router(sales.router, prefix="/sales", tags=["Sales Management"])
api_router.include_router(production.router, prefix="/production", tags=["Production Management"])

# Module III: Financial & Marketing
api_router.include_router(discounts.router, prefix="/discounts", tags=["Discount Management"])
api_router.include_router(ads.router, prefix="/ads", tags=["Paid Ads Management"])

# Reports (All Modules)
api_router.include_router(reports.router, prefix="/reports", tags=["Reports & Analytics"])
