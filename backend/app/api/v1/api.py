from fastapi import APIRouter
from app.api.v1.endpoints import auth, yarns, fabrics, processes, garments, inventory, sales, panels, production, discounts, ads, reports
from app.api.v1.endpoints import integrations
from app.api.v1.endpoints import unicommerce_data
from app.api.v1.endpoints import production_planning
# Manufacturing Module
from app.api.v1.endpoints import (
    suppliers, purchase_orders, gate_entry, mrns,
    yarn_store, knitting, processing, garment_production,
)
from app.api.v1.endpoints import product_master
from app.api.v1.endpoints import fabric_yarn_master
from app.api.v1.endpoints import shopify_master_data
# Unicommerce API modules
from app.api.v1.endpoints import (
    uc_vendors, uc_grn, uc_catalog, uc_inventory,
    uc_orders, uc_facility, uc_gatepass, uc_returns,
    uc_shipping, uc_invoices, uc_misc, webhooks,
)

api_router = APIRouter()

# Authentication
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])

# Module I: Raw Material & Processing
api_router.include_router(
    yarns.router, prefix="/yarns", tags=["Yarn Management"])
api_router.include_router(
    processes.router, prefix="/processes", tags=["Process Management"])
api_router.include_router(
    fabrics.router, prefix="/fabrics", tags=["Fabric Management"])

# Module II: Garment & Sales
api_router.include_router(
    garments.router, prefix="/garments", tags=["Garment Master Data"])
api_router.include_router(
    inventory.router, prefix="/inventory", tags=["Inventory Management"])
api_router.include_router(
    panels.router, prefix="/panels", tags=["Panel Management"])
api_router.include_router(
    sales.router, prefix="/sales", tags=["Sales Management"])
api_router.include_router(
    production.router, prefix="/production", tags=["Production Management"])

# Module III: Financial & Marketing
api_router.include_router(
    discounts.router, prefix="/discounts", tags=["Discount Management"])
api_router.include_router(ads.router, prefix="/ads",
                          tags=["Ads Management"])

# Procurement Module
api_router.include_router(
    suppliers.router, prefix="/suppliers", tags=["Supplier Master"])
api_router.include_router(
    purchase_orders.router, prefix="/purchase-orders", tags=["Purchase Orders"])
api_router.include_router(
    gate_entry.router, prefix="/gate-entries", tags=["Gate Entry"])
api_router.include_router(
    mrns.router, prefix="/mrns", tags=["MRN"])
api_router.include_router(
    product_master.router, prefix="/products", tags=["Product Master"])
api_router.include_router(
    fabric_yarn_master.router,
    prefix="/procurement/fabric-yarn-master",
    tags=["Fabric & Yarn Master"],
)
api_router.include_router(
    shopify_master_data.router,
    prefix="/shopify-master-data",
    tags=["Shopify Master Data"],
)

# Manufacturing Module
api_router.include_router(
    yarn_store.router, prefix="/yarn-store", tags=["Yarn Store"])
api_router.include_router(
    knitting.router, prefix="/knitting", tags=["Knitting"])
api_router.include_router(
    processing.router, prefix="/processing", tags=["Processing"])
api_router.include_router(
    garment_production.router, prefix="/garment-production", tags=["Garment Production"])
api_router.include_router(
    production_planning.router, prefix="/production-planning", tags=["Garment Production Planning"])

# Reports (All Modules)
api_router.include_router(
    reports.router, prefix="/reports", tags=["Reports & Analytics"])

# External Integrations (Sales Dashboard)
api_router.include_router(
    integrations.router, prefix="/integrations", tags=["External Integrations"])

# DB-first Unicommerce analytics data
api_router.include_router(
    unicommerce_data.router, prefix="/unicommerce-data", tags=["Unicommerce Data (DB-First)"])

# Unicommerce API Integrations (All 101 endpoints)

# Vendors & Purchase Orders
api_router.include_router(
    uc_vendors.router, prefix="/uc/vendors",
    tags=["UC - Vendors & Purchase Orders"])

# GRN (Goods Receipt Notes)
api_router.include_router(
    uc_grn.router, prefix="/uc/grn",
    tags=["UC - GRN"])

# Catalog & Products
api_router.include_router(
    uc_catalog.router, prefix="/uc/catalog",
    tags=["UC - Catalog & Products"])

# Inventory Management (UC)
api_router.include_router(
    uc_inventory.router, prefix="/uc/inventory",
    tags=["UC - Inventory"])

# Sale Orders (UC)
api_router.include_router(
    uc_orders.router, prefix="/uc/orders",
    tags=["UC - Sale Orders"])

# Facility Management
api_router.include_router(
    uc_facility.router, prefix="/uc/facility",
    tags=["UC - Facility"])

# Gatepass
api_router.include_router(
    uc_gatepass.router, prefix="/uc/gatepass",
    tags=["UC - Gatepass"])

# Returns & Reverse Pickup
api_router.include_router(
    uc_returns.router, prefix="/uc/returns",
    tags=["UC - Returns & Reverse Pickup"])

# Shipping, Dispatch, Manifests
api_router.include_router(
    uc_shipping.router, prefix="/uc/shipping",
    tags=["UC - Shipping & Dispatch"])

# Invoices
api_router.include_router(
    uc_invoices.router, prefix="/uc/invoices",
    tags=["UC - Invoices"])

# Picklist, Custom UI, Misc
api_router.include_router(
    uc_misc.router, prefix="/uc/misc",
    tags=["UC - Miscellaneous"])

# Webhooks (real-time event system)
api_router.include_router(
    webhooks.router, prefix="/webhooks",
    tags=["Webhooks"])
