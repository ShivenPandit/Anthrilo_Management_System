# VPS Backend Table to Module Mapping and API Migration Plan

Date: 2026-04-14
Branch: Rishabh

## 1) Live database snapshot from running backend

Total tables: 33

Tables:
- activity_logs
- alembic_version
- cache_metadata
- discounts
- export_jobs
- export_rows
- fabrics
- garments
- inventory
- inventory_snapshots
- login_history
- order_sync_jobs
- paid_ads
- panels
- permissions
- processes
- product_master
- production_activities
- production_plans
- role_permissions
- roles
- sales
- sales_orders
- sales_returns
- sync_checkpoints
- sync_logs
- unicommerce_orders
- user_permissions
- user_roles
- user_sessions
- users
- webhook_events
- yarns

## 2) Table groups by business domain

### Security and admin
- users
- roles
- permissions
- user_roles
- user_permissions
- user_sessions
- login_history
- activity_logs

### Core garment and inventory (internal ERP)
- garments
- inventory
- fabrics
- yarns
- processes
- panels
- sales
- production_plans
- production_activities
- discounts
- paid_ads
- product_master

### DB-first commerce cache and sync layer (legacy/unicommerce-oriented)
- sales_orders
- sales_returns
- inventory_snapshots
- export_jobs
- export_rows
- unicommerce_orders
- sync_logs
- sync_checkpoints
- order_sync_jobs
- webhook_events
- cache_metadata

## 3) Dashboard and report page mapping

## Legend
- Source type Internal DB only: does not require Unicommerce fetch path
- Source type DB-first plus Unicommerce fallback: reads VPS DB first, but can still trigger Unicommerce sync/fallback when data is missing

| Frontend page group | Frontend call path | Backend endpoint group | Main tables used | Source type |
|---|---|---|---|---|
| Dashboard home and warmup, sales summary cards | ucSales.getToday/getYesterday/getLast7Days | /api/v1/unicommerce-data/sales | sales_orders primary, export_rows/export_jobs fallback | DB-first plus Unicommerce fallback |
| Sales transactions page | ucSales.getOrders and period summaries | /api/v1/unicommerce-data/orders and /sales | sales_orders primary | DB-first plus Unicommerce fallback |
| Sales daily report page | ucSales.getDailySalesReport and getReportProgress | /api/v1/unicommerce-data/daily-sales-report | sales_orders primary, export_rows fallback | DB-first plus Unicommerce fallback |
| Sales returns page | ucSales.getReturnReport and getReportProgress | /api/v1/unicommerce-data/return-report | sales_returns primary, export_rows fallback | DB-first plus Unicommerce fallback |
| Sales cancellation page | ucSales.getCancellationReport and getReportProgress | /api/v1/unicommerce-data/cancellation-report | sales_orders primary, export_rows fallback | DB-first plus Unicommerce fallback |
| Sales activity and channel reports | unicommerceApi.getSalesActivity and getChannelRevenue | /api/v1/unicommerce-data/sales-activity and /channel-revenue | sales_orders primary | DB-first plus Unicommerce fallback |
| Bundle and SKU analysis pages | getSalesBySku, getBundleSkus, getBundleSalesAnalysis | /api/v1/unicommerce-data/sales-by-sku, /bundle-skus, /bundle-sales-analysis | sales_orders, product_master, export_rows item master | DB-first plus Unicommerce fallback |
| COD vs prepaid, top sellers, sku velocity, best skus | getCodVsPrepaid, getSkuVelocity, getBestSkusMonthly | /api/v1/unicommerce-data/cod-vs-prepaid, /sku-velocity, /best-skus-monthly | sales_orders primary | DB-first plus Unicommerce fallback |
| Garments inventory summary in sales modules | ucInventory.getSummary and search | /api/v1/unicommerce-data/inventory-summary and /catalog-search | inventory_snapshots primary, export_rows fallback | DB-first plus Unicommerce fallback |
| Fabric report page | apiClient.get /reports/fabric/* | /api/v1/reports/fabric/* | fabrics | Internal DB only |
| Production report page | apiClient.get /reports/production/* | /api/v1/reports/production/* | production_plans, production_activities, garments | Internal DB only |
| General report hooks useReports.ts | /reports/sales, /reports/inventory, /reports/raw-materials | /api/v1/reports/* | sales, panels, yarns, fabrics, production tables | Internal DB only |
| Raw materials yarn forecasting page | rawMaterialsReports.getYarnForecasting | currently points to /reports/yarn/forecasting in frontend helper | expected yarns plus production_plans | Internal DB endpoint exists, but frontend helper path mismatch |

## 4) Pages that are fully internal DB today

These are internal DB only (no Unicommerce fallback path needed):
- reports fabric pages using /api/v1/reports/fabric/*
- reports production pages using /api/v1/reports/production/*
- classic reports hooks using /api/v1/reports/*
- core CRUD modules such as garments, inventory, sales, panels, procurement, manufacturing endpoints under /api/v1 except unicommerce-data and integrations endpoints

## 5) Pages with Unicommerce fallback risk

All pages using /api/v1/unicommerce-data/* are in this category.

Risk behavior:
- Backend first checks normalized DB tables such as sales_orders and inventory_snapshots
- If coverage is empty or insufficient, backend can trigger orchestrator sync methods that call Unicommerce export APIs
- Additional fallback path reads archived export_rows when normalized tables are empty

## 6) How to disable fallback safely

## Phase 1: Introduce explicit kill switch flags
Add flags in settings and env:
- UNICOMMERCE_FALLBACK_ENABLED false
- UNICOMMERCE_BOOTSTRAP_SYNC_ENABLED false
- UNICOMMERCE_SCHEDULER_ENABLED false for final cutover

## Phase 2: Stop bootstrap sync triggers in unicommerce-data endpoints
In unicommerce_data endpoints, gate all should_bootstrap blocks behind UNICOMMERCE_BOOTSTRAP_SYNC_ENABLED.
If disabled, return DB result as-is and include clear metadata such as data_source and stale indicators.

## Phase 3: Stop raw export fallback reads in service
In unicommerce_data_service:
- Keep normalized table reads
- Disable _raw_sales_rows_from_job and raw export fallback branches when UNICOMMERCE_FALLBACK_ENABLED is false
- Return explicit no_data states instead of pulling export_rows

## Phase 4: Redirect frontend to canonical VPS endpoints
Create and migrate to domain-first endpoint families:
- /api/v1/sales-analytics/* from internal sales_orders canonical model
- /api/v1/inventory-analytics/* from internal inventory snapshots or canonical inventory balances
- /api/v1/order-reports/* from internal order tables
Then update frontend wrappers in lib/api/index and lib/api/uc to use the new families.

## Phase 5: Decommission legacy unicommerce layer
After 2 to 4 weeks of validation:
- disable scheduler tasks
- remove orchestrator sync routes from active navigation
- keep migration or archival jobs read-only
- eventually retire export_jobs and export_rows if no longer required

## 7) Answer to periodic fetch question

Yes, backend currently has periodic fetch logic from Unicommerce.

Where it is implemented:
- app startup and shutdown hooks in backend app main module
- scheduler logic in unicommerce_sync_orchestrator
- scheduler jobs: sales, returns, inventory
- sales and returns jobs fetch windows from recent lookback and call export-based fetch methods

Operational behavior:
- If scheduler is enabled, it runs on configured intervals and fetches recent windows automatically.
- Not strictly fixed to last 24 hours by default. Window size is controlled by lookback settings.
- In current docker compose, sync_worker has scheduler enabled and backend has scheduler disabled.

## 8) Recommended immediate actions

1. Fix endpoint mismatch for yarn forecasting helper
- frontend reports helper currently calls /reports/yarn/forecasting but backend route is /reports/raw-materials/yarn-forecasting

2. Add migration-safe flags before API redirection
- implement the three flags in config and environment

3. Build one canonical order report endpoint from internal tables
- migrate one report page first and validate parity

4. Disable bootstrap sync on staging first
- verify no dashboard breakage

5. Cut production over in controlled phases
- monitor data_source metadata and report freshness
