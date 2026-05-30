import { apiClient } from '@/lib/api-client';
import type {
  Garment, Inventory, Panel, Sale, ProductionPlan,
  Supplier, PurchaseOrder, GateEntry, MRN,
  KnitOrder, YarnIssue, GreyFabricReceipt,
  ProcessingOrder, GreyFabricIssue, FinishedFabricReceipt,
  CuttingOrder, CuttingCheck, StitchingOrder, GarmentFinishing, BarcodeLabel,
  InventoryTransaction,
} from '@/types';

// Export all reports API
export * from './reports';

// Garment API
export const garmentApi = {
  getAll: (params?: { category?: string; is_active?: boolean }) =>
    apiClient.get<Garment[]>('/garments', { params }),
  getById: (id: number) => apiClient.get<Garment>(`/garments/${id}`),
  getBySku: (sku: string) => apiClient.get<Garment>(`/garments/sku/${sku}`),
  create: (data: Partial<Garment>) => apiClient.post<Garment>('/garments', data),
  update: (id: number, data: Partial<Garment>) =>
    apiClient.put<Garment>(`/garments/${id}`, data),
  delete: (id: number) => apiClient.delete(`/garments/${id}`),
};

// Inventory API
export const inventoryApi = {
  getAll: () => apiClient.get<Inventory[]>('/inventory'),
  getByGarment: (garmentId: number) =>
    apiClient.get<Inventory[]>(`/inventory/garment/${garmentId}`),
  getLowStock: (threshold: number = 10) =>
    apiClient.get<Inventory[]>(`/inventory/low-stock?threshold=${threshold}`),
  create: (data: Partial<Inventory>) => apiClient.post<Inventory>('/inventory', data),
  update: (id: number, data: Partial<Inventory>) =>
    apiClient.put<Inventory>(`/inventory/${id}`, data),
};

// Panel API
export const panelApi = {
  getAll: (params?: { is_active?: boolean; panel_type?: string }) =>
    apiClient.get<Panel[]>('/panels', { params }),
  getById: (id: number) => apiClient.get<Panel>(`/panels/${id}`),
  create: (data: Partial<Panel>) => apiClient.post<Panel>('/panels', data),
};

// Sales API
export const salesApi = {
  getAll: (params?: {
    start_date?: string;
    end_date?: string;
    panel_id?: number;
  }) => apiClient.get<Sale[]>('/sales', { params }),
  getDaily: (date: string) => apiClient.get<Sale[]>(`/sales/daily/${date}`),
  create: (data: Partial<Sale>) => apiClient.post<Sale>('/sales', data),
};

// Production API
export const productionApi = {
  getAllPlans: (params?: { status?: string }) =>
    apiClient.get<ProductionPlan[]>('/production/plans', { params }),
  getPlan: (id: number) => apiClient.get<ProductionPlan>(`/production/plans/${id}`),
  createPlan: (data: Partial<ProductionPlan>) =>
    apiClient.post<ProductionPlan>('/production/plans', data),
};

// Unicommerce integration API
export const unicommerceApi = {
  // Summary endpoints (dashboard cards)
  getToday: () => apiClient.get('/unicommerce-data/sales', { params: { period: 'today', lightweight: true } }),
  getYesterday: () => apiClient.get('/unicommerce-data/sales', { params: { period: 'yesterday', lightweight: true } }),
  getLast7Days: () => apiClient.get('/unicommerce-data/sales', { params: { period: 'last_7_days', lightweight: true } }),
  getLast30Days: () => apiClient.get('/unicommerce-data/sales', { params: { period: 'last_30_days', lightweight: true } }),
  getLast24Hours: () => apiClient.get('/unicommerce-data/sales', { params: { period: 'today', lightweight: true } }), // Alias

  // Canonical DB-first endpoints
  getDbSales: (params?: { period?: string; from_date?: string; to_date?: string; lightweight?: boolean }) =>
    apiClient.get('/unicommerce-data/sales', { params }),
  getDbOrders: (params?: { period?: string; from_date?: string; to_date?: string; page?: number; page_size?: number }) =>
    apiClient.get('/unicommerce-data/orders', { params }),
  getDbInventory: (params?: { skus?: string; warehouse?: string }) =>
    apiClient.get('/unicommerce-data/inventory', { params }),
  getDbFirstParityCheck: (params: { from_date: string; to_date: string; closed_window_mode?: boolean; revenue_drift_threshold_pct?: number; orders_drift_threshold_pct?: number }) =>
    apiClient.get('/integrations/unicommerce/db-first-parity-check', { params }),

  // Paginated order lists (12 per page by default)
  getTodayOrders: (page: number = 1, pageSize: number = 12) =>
    apiClient.get('/unicommerce-data/orders', { params: { period: 'today', page, page_size: pageSize } }),
  getYesterdayOrders: (page: number = 1, pageSize: number = 12) =>
    apiClient.get('/unicommerce-data/orders', { params: { period: 'yesterday', page, page_size: pageSize } }),
  getLast7DaysOrders: (page: number = 1, pageSize: number = 12) =>
    apiClient.get('/unicommerce-data/orders', { params: { period: 'last_7_days', page, page_size: pageSize } }),
  getLast30DaysOrders: (page: number = 1, pageSize: number = 12) =>
    apiClient.get('/unicommerce-data/orders', { params: { period: 'last_30_days', page, page_size: pageSize } }),
  getCustomOrders: (params: { from_date: string; to_date: string; page?: number; page_size?: number }) =>
    apiClient.get('/unicommerce-data/orders', { params: { period: 'custom', ...params } }),

  // Sales reports
  getSalesReport: (params?: { from_date?: string; to_date?: string; period?: string }) =>
    apiClient.get('/unicommerce-data/sales', { params }),

  // Daily sales breakdown by channel (single date or range)
  getDailySalesReport: (params: { date?: string; from_date?: string; to_date?: string; progress_id?: string }) =>
    apiClient.get('/unicommerce-data/daily-sales-report', { params }),

  // Returns report — channel + SKU breakdown
  getReturnReport: (params: {
    date?: string;
    from_date?: string;
    to_date?: string;
    period?: 'daily' | 'weekly' | 'monthly' | 'custom';
    return_type?: string;
    progress_id?: string;
  }) => apiClient.get('/unicommerce-data/return-report', { params }),

  // Cancellation report — channel + SKU + item-level breakdown
  getCancellationReport: (params: {
    date?: string;
    from_date?: string;
    to_date?: string;
    period?: 'daily' | 'weekly' | 'monthly' | 'custom';
    progress_id?: string;
  }) => apiClient.get('/unicommerce-data/cancellation-report', { params }),

  // Long-running report progress
  getReportProgress: (progressId: string) =>
    apiClient.get(`/unicommerce-data/report-progress/${progressId}`),

  // Best performing SKUs for a given month
  getBestSkusMonthly: (params?: { month?: number; year?: number; limit?: number; force_refresh?: boolean; b2c_only?: boolean }) =>
    apiClient.get('/unicommerce-data/best-skus-monthly', { params }),

  // SKU velocity — fast & slow movers for a given month
  getSkuVelocity: (params?: { month?: number; year?: number; limit?: number; min_qty?: number; b2c_only?: boolean; force_refresh?: boolean }) =>
    apiClient.get('/unicommerce-data/sku-velocity', { params }),

  // COD vs prepaid breakdown
  getCodVsPrepaid: (params?: {
    period?: 'daily' | 'weekly' | 'monthly' | 'custom';
    date?: string;
    from_date?: string;
    to_date?: string;
    month?: number;
    year?: number;
  }) =>
    apiClient.get('/unicommerce-data/cod-vs-prepaid', { params }),

  // Channel revenue split
  getChannelRevenue: (period: string = 'last_30_days') =>
    apiClient.get('/unicommerce-data/channel-revenue', { params: { period } }),

  // Sales Activity Report
  getSalesActivity: (params: { from_date: string; to_date: string; channels?: string[]; progress_id?: string }) => {
    const query = new URLSearchParams();
    query.set('from_date', params.from_date);
    query.set('to_date', params.to_date);
    if (params.progress_id) {
      query.set('progress_id', params.progress_id);
    }
    for (const channel of params.channels || []) {
      if (channel) {
        query.append('channels', channel);
      }
    }
    return apiClient.get(`/unicommerce-data/sales-activity?${query.toString()}`);
  },

  // Sales Activity selectable channels for date range
  getSalesActivityChannels: (params: { from_date: string; to_date: string }) =>
    apiClient.get('/unicommerce-data/sales-activity/channels', { params }),

  // SKU sales breakdown
  getSalesBySku: (params: { period: string; from_date?: string; to_date?: string }) =>
    apiClient.get('/unicommerce-data/sales-by-sku', { params }),

  // Fabric sales report
  getFabricSales: (params: { month?: number; year?: number; from_date?: string; to_date?: string; force_refresh?: boolean }) =>
    apiClient.get('/unicommerce-data/fabric-sales', { params }),

  // Bundle SKU catalog
  getBundleSkus: (params?: { force_refresh?: boolean, page?: number, limit?: number, search?: string, category?: string, enabled_only?: boolean }) =>
    apiClient.get('/unicommerce-data/bundle-skus', { params }),

  // Bundle sales analysis
  getBundleSalesAnalysis: (params?: {
    period?: string;
    from_date?: string;
    to_date?: string;
    force_refresh?: boolean;
  }) => apiClient.get('/unicommerce-data/bundle-sales-analysis', { params }),

  // Revenue validation
  validateRevenue: () => apiClient.get('/unicommerce-data/validate'),

  // Cache helpers
  clearCache: () => apiClient.post('/unicommerce-data/clear-cache'),
  getCacheStats: () => apiClient.get('/unicommerce-data/cache-stats'),
  checkCacheStatus: () => apiClient.get('/unicommerce-data/cache-check'),

  // Manual ingestion trigger (runs incremental profile and waits for completion)
  runIncrementalSyncNow: () =>
    apiClient.post('/integrations/unicommerce/sync/profile/incremental', null, {
      params: { run_in_background: true },
    }),
  getSyncStatus: () =>
    apiClient.get('/integrations/unicommerce/sync/status'),

  // System recovery status
  getSystemSyncStatus: () => apiClient.get('/system/sync-status'),
  triggerRecoverySync: (payload?: { entities?: string[]; from_date?: string; to_date?: string; force?: boolean }) =>
    apiClient.post('/system/recover-sync', payload || {}),

  // Legacy endpoints (kept for backward compat)
  searchOrders: (params: { from_date: string; to_date: string; display_start?: number; display_length?: number }) =>
    apiClient.get('/unicommerce-data/search-orders', { params }),
  getOrderItems: (orderCode: string) =>
    apiClient.get(`/unicommerce-data/order-items/${orderCode}`),
};

// Procurement

export const supplierApi = {
  getAll: (params?: { search?: string; supplier_type?: string; is_active?: boolean }) =>
    apiClient.get<Supplier[]>('/suppliers', { params }),
  getById: (id: number) => apiClient.get<Supplier>(`/suppliers/${id}`),
  create: (data: Partial<Supplier>) => apiClient.post<Supplier>('/suppliers', data),
  update: (id: number, data: Partial<Supplier>) =>
    apiClient.put<Supplier>(`/suppliers/${id}`, data),
  delete: (id: number) => apiClient.delete(`/suppliers/${id}`),
};

export const purchaseOrderApi = {
  getAll: (params?: { status?: string; department?: string; supplier_id?: number; from_date?: string; to_date?: string; skip?: number; limit?: number }) =>
    apiClient.get<PurchaseOrder[]>('/purchase-orders', { params }),
  getPending: () => apiClient.get<PurchaseOrder[]>('/purchase-orders/pending'),
  getById: (id: number) => apiClient.get<PurchaseOrder>(`/purchase-orders/${id}`),
  create: (data: any) => apiClient.post<PurchaseOrder>('/purchase-orders', data),
  update: (id: number, data: any) =>
    apiClient.put<PurchaseOrder>(`/purchase-orders/${id}`, data),
  cancel: (id: number) => apiClient.post(`/purchase-orders/${id}/cancel`),
};

export const gateEntryApi = {
  getAll: (params?: { supplier_id?: number; status?: string; from_date?: string; to_date?: string; skip?: number; limit?: number }) =>
    apiClient.get<GateEntry[]>('/gate-entries', { params }),
  getById: (id: number) => apiClient.get<GateEntry>(`/gate-entries/${id}`),
  create: (data: any) => apiClient.post<GateEntry>('/gate-entries', data),
  update: (id: number, data: any) =>
    apiClient.put<GateEntry>(`/gate-entries/${id}`, data),
  close: (id: number) => apiClient.post(`/gate-entries/${id}/close`),
};

export const mrnApi = {
  getAll: (params?: { status?: string; supplier_id?: number; from_date?: string; to_date?: string; skip?: number; limit?: number }) =>
    apiClient.get<MRN[]>('/mrns', { params }),
  getByPo: (poId: number) => apiClient.get<MRN[]>(`/mrns/by-po/${poId}`),
  getById: (id: number) => apiClient.get<MRN>(`/mrns/${id}`),
  create: (data: any) => apiClient.post<MRN>('/mrns', data),
  update: (id: number, data: any) => apiClient.put<MRN>(`/mrns/${id}`, data),
  confirm: (id: number) => apiClient.post<MRN>(`/mrns/${id}/confirm`),
};

// Yarn Store

export const yarnStoreApi = {
  getBalance: (params?: { yarn_id?: number }) =>
    apiClient.get('/yarn-store/balance', { params }),
  getBalanceById: (yarnId: number) =>
    apiClient.get(`/yarn-store/balance/${yarnId}`),
  getLedger: (params?: { yarn_id?: number; from_date?: string; to_date?: string; skip?: number; limit?: number }) =>
    apiClient.get<InventoryTransaction[]>('/yarn-store/ledger', { params }),
  adjust: (data: { yarn_id: number; transaction_type: string; quantity: number; reference_number: string; transaction_date: string }) =>
    apiClient.post('/yarn-store/adjustment', data),
};

// Knitting

export const knittingApi = {
  getOrders: (params?: { status?: string; knitter_supplier_id?: number; from_date?: string; to_date?: string; skip?: number; limit?: number }) =>
    apiClient.get<KnitOrder[]>('/knitting/orders', { params }),
  getOrder: (id: number) => apiClient.get<KnitOrder>(`/knitting/orders/${id}`),
  createOrder: (data: any) => apiClient.post<KnitOrder>('/knitting/orders', data),
  updateOrder: (id: number, data: any) =>
    apiClient.put<KnitOrder>(`/knitting/orders/${id}`, data),
  // Yarn issue
  issueYarn: (data: any) => apiClient.post<YarnIssue>('/knitting/yarn-issues', data),
  getYarnIssues: (params?: { knit_order_id?: number }) =>
    apiClient.get<YarnIssue[]>('/knitting/yarn-issues', { params }),
  // Grey fabric receipt
  receiveGreyFabric: (data: any) =>
    apiClient.post<GreyFabricReceipt>('/knitting/grey-fabric-receipt', data),
  getGreyFabricReceipts: (params?: { knit_order_id?: number }) =>
    apiClient.get<GreyFabricReceipt[]>('/knitting/grey-fabric-receipts', { params }),
  // Yarn return
  returnYarn: (issueId: number, data: any) =>
    apiClient.post(`/knitting/yarn-return/${issueId}`, data),
};

// Processing / Dyeing

export const processingApi = {
  getOrders: (params?: { status?: string; process_type?: string; from_date?: string; to_date?: string; skip?: number; limit?: number }) =>
    apiClient.get<ProcessingOrder[]>('/processing/orders', { params }),
  getOrder: (id: number) => apiClient.get<ProcessingOrder>(`/processing/orders/${id}`),
  createOrder: (data: any) => apiClient.post<ProcessingOrder>('/processing/orders', data),
  updateOrder: (id: number, data: any) =>
    apiClient.put<ProcessingOrder>(`/processing/orders/${id}`, data),
  // Grey fabric issue
  issueGreyFabric: (data: any) =>
    apiClient.post<GreyFabricIssue>('/processing/grey-fabric-issue', data),
  getGreyFabricIssues: (params?: { processing_order_id?: number }) =>
    apiClient.get<GreyFabricIssue[]>('/processing/grey-fabric-issues', { params }),
  // Finished fabric receipt
  receiveFinishedFabric: (data: any) =>
    apiClient.post<FinishedFabricReceipt>('/processing/finished-fabric-receipt', data),
  getFinishedFabricReceipts: (params?: { processing_order_id?: number }) =>
    apiClient.get<FinishedFabricReceipt[]>('/processing/finished-fabric-receipts', { params }),
  // Store views
  getGreyFabricStore: () => apiClient.get('/processing/grey-fabric-store'),
  getFinishedFabricStore: () => apiClient.get('/processing/finished-fabric-store'),
  getFabricLedger: (params?: { fabric_id?: number; from_date?: string; to_date?: string }) =>
    apiClient.get('/processing/fabric-ledger', { params }),
};

// Product Master

export const productMasterApi = {
  getAll: (params?: {
    skip?: number; limit?: number; search?: string;
    sort_by?: string; sort_order?: string;
    collection?: string; season?: string; fabric_type?: string; type?: string;
  }) =>
    apiClient.get('/products', { params }),
  getById: (id: number) => apiClient.get(`/products/${id}`),
  create: (data: Record<string, any>) => apiClient.post('/products', data),
  update: (id: number, data: Record<string, any>) => apiClient.put(`/products/${id}`, data),
  delete: (id: number) => apiClient.delete(`/products/${id}`),
  import: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post('/products/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  getFilterOptions: () => apiClient.get('/products/meta/filter-options'),
};

export const shopifyMasterDataApi = {
  getAll: (params?: { skip?: number; limit?: number; search?: string }) =>
    apiClient.get('/shopify-master-data', { params }),
  import: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post('/shopify-master-data/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
};

// Garment Production

export const garmentProductionApi = {
  // Cutting
  getCuttingOrders: (params?: { status?: string; garment_id?: number; from_date?: string; to_date?: string; skip?: number; limit?: number }) =>
    apiClient.get<CuttingOrder[]>('/garment-production/cutting-orders', { params }),
  getCuttingOrder: (id: number) =>
    apiClient.get<CuttingOrder>(`/garment-production/cutting-orders/${id}`),
  createCuttingOrder: (data: any) =>
    apiClient.post<CuttingOrder>('/garment-production/cutting-orders', data),
  updateCuttingOrder: (id: number, data: any) =>
    apiClient.put<CuttingOrder>(`/garment-production/cutting-orders/${id}`, data),
  // Cutting check
  createCuttingCheck: (data: any) =>
    apiClient.post<CuttingCheck>('/garment-production/cutting-check', data),
  // Stitching
  getStitchingOrders: (params?: { status?: string; skip?: number; limit?: number }) =>
    apiClient.get<StitchingOrder[]>('/garment-production/stitching-orders', { params }),
  getStitchingOrder: (id: number) =>
    apiClient.get<StitchingOrder>(`/garment-production/stitching-orders/${id}`),
  createStitchingOrder: (data: any) =>
    apiClient.post<StitchingOrder>('/garment-production/stitching-orders', data),
  updateStitchingOrder: (id: number, data: any) =>
    apiClient.put<StitchingOrder>(`/garment-production/stitching-orders/${id}`, data),
  // Finishing
  recordFinishing: (data: any) =>
    apiClient.post<GarmentFinishing>('/garment-production/finishing', data),
  getFinishingStages: (stitchingOrderId: number) =>
    apiClient.get<GarmentFinishing[]>(`/garment-production/finishing/${stitchingOrderId}`),
  // Barcodes
  generateBarcodes: (data: { garment_finishing_id: number; garment_id: number; sizes: Record<string, number>; mrp: number; batch_number?: string }) =>
    apiClient.post<BarcodeLabel[]>('/garment-production/barcodes/batch', data),
  getBarcodes: (params?: { garment_id?: number; is_printed?: boolean; batch_number?: string; skip?: number; limit?: number }) =>
    apiClient.get<BarcodeLabel[]>('/garment-production/barcodes', { params }),
  markPrinted: (barcodeIds: number[]) =>
    apiClient.post('/garment-production/barcodes/mark-printed', barcodeIds),
};
