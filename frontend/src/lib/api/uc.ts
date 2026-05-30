import { unicommerceApi } from './index';
import { apiClient } from '@/lib/api-client';

// Unicommerce re-exports kept for backward compatibility

// Sales-related
export const ucSales = {
    getToday: unicommerceApi.getToday,
    getYesterday: unicommerceApi.getYesterday,
    getLast7Days: unicommerceApi.getLast7Days,
    getLast30Days: unicommerceApi.getLast30Days,
    getLast24Hours: unicommerceApi.getLast24Hours,
    getTodayOrders: unicommerceApi.getTodayOrders,
    getYesterdayOrders: unicommerceApi.getYesterdayOrders,
    getLast7DaysOrders: unicommerceApi.getLast7DaysOrders,
    getLast30DaysOrders: unicommerceApi.getLast30DaysOrders,
    getCustomOrders: unicommerceApi.getCustomOrders,
    getSalesReport: unicommerceApi.getSalesReport,
    getDailySalesReport: unicommerceApi.getDailySalesReport,
    getReturnReport: unicommerceApi.getReturnReport,
    getCancellationReport: unicommerceApi.getCancellationReport,
    getReportProgress: unicommerceApi.getReportProgress,
    getChannelRevenue: unicommerceApi.getChannelRevenue,
    validateRevenue: unicommerceApi.validateRevenue,
    getBestSkusMonthly: unicommerceApi.getBestSkusMonthly,
    getCodVsPrepaid: unicommerceApi.getCodVsPrepaid,
    getSkuVelocity: unicommerceApi.getSkuVelocity,

    // Route the right endpoint based on period
    getOrders: async (params: { period: string; page: number; page_size: number; from_date?: string; to_date?: string }) => {
        const { period, page, page_size, from_date, to_date } = params;

        // Pick the right endpoint based on the chosen period
        if (period === 'custom' && from_date && to_date) {
            return unicommerceApi.getCustomOrders({ from_date, to_date, page, page_size });
        } else if (period === 'today') {
            return unicommerceApi.getTodayOrders(page, page_size);
        } else if (period === 'yesterday') {
            return unicommerceApi.getYesterdayOrders(page, page_size);
        } else if (period === 'last_7_days') {
            return unicommerceApi.getLast7DaysOrders(page, page_size);
        } else if (period === 'last_30_days') {
            return unicommerceApi.getLast30DaysOrders(page, page_size);
        } else {
            return unicommerceApi.getTodayOrders(page, page_size);
        }
    },

    getSalesBySku: unicommerceApi.getSalesBySku,

    getFabricSales: unicommerceApi.getFabricSales,

    getBundleSkus: unicommerceApi.getBundleSkus,

    getBundleSalesAnalysis: unicommerceApi.getBundleSalesAnalysis,

    syncNow: unicommerceApi.runIncrementalSyncNow,
};

// Catalog-related
export const ucCatalog = {
    searchItems: (params: {
        displayStart: number;
        displayLength: number;
        getInventorySnapshot?: boolean;
        getAggregates?: boolean;
        keyword?: string;
        stockFilter?: 'all' | 'in_stock' | 'out_of_stock';
    }) => {
        // Build the Unicommerce search payload
        const payload: any = {
            getInventorySnapshot: params.getInventorySnapshot ?? false,
            getAggregates: params.getAggregates ?? false,
            stockFilter: params.stockFilter || 'all',
            searchOptions: {
                displayStart: params.displayStart,
                displayLength: params.displayLength,
            },
        };

        if (params.keyword) {
            payload.keyword = params.keyword;
        }

        return apiClient.post('/unicommerce-data/catalog-search', payload);
    },

    // Inventory totals (independent of pagination)
    getInventorySummary: (forceRefresh: boolean = true) => {
        return apiClient.get('/uc/catalog/inventory/summary', {
            params: forceRefresh ? { force_refresh: true } : undefined,
        });
    },
};

// Inventory (used by the stock-analysis page)
export const ucInventory = {
    getSummary: () =>
        apiClient.get('/unicommerce-data/inventory-summary').then((res) => {
            const d = res.data || {};
            return {
                data: {
                    successful: d.successful,
                    summary: {
                        total_skus: d.totalSKUs ?? d.totalProducts ?? 0,
                        in_stock: d.skusWithStock ?? d.inStock ?? d.in_stock ?? 0,
                        out_of_stock: d.skusOutOfStock ?? d.outOfStock ?? d.out_of_stock ?? 0,
                        total_inventory: d.totalRealInventory ?? d.total_inventory ?? 0,
                        total_virtual: d.totalVirtualInventory ?? d.total_virtual ?? 0,
                        categories: d.categories ?? [],
                    },
                },
            };
        }),

    getSnapshot: (params: { page: number; page_size: number; in_stock_only?: boolean; category?: string; enabled_only?: boolean }) => {
        const payload: any = {
            getInventorySnapshot: true,
            stockFilter: params.in_stock_only ? 'in_stock' : 'all',
            searchOptions: {
                displayStart: (params.page - 1) * params.page_size,
                displayLength: params.page_size,
            },
        };
        if (params.category) {
            payload.categoryName = params.category;
        }

        return apiClient.post('/unicommerce-data/catalog-search', payload).then((res) => {
            const elements = res.data?.elements || [];
            const totalRecords = res.data?.totalRecords || elements.length;
            const snapshots = elements.map((el: any) => {
                const snap = el.inventorySnapshots?.[0] || {};
                return {
                    itemTypeSKU: el.skuCode || '',
                    skuCode: el.skuCode || '',
                    name: el.name || el.itemTypeName || '',
                    categoryName: el.categoryName || '',
                    color: el.color || '',
                    size: el.size || '',
                    brand: el.brand || '',
                    costPrice: el.costPrice || el.price || el.mrp || 0,
                    price: el.price ?? el.mrp ?? el.maxRetailPrice ?? el.costPrice ?? 0,
                    mrp: el.mrp ?? el.price ?? el.maxRetailPrice ?? 0,
                    inventory: snap.inventory ?? 0,
                    availableInventory: snap.availableInventory ?? snap.inventory ?? 0,
                    virtualInventory: snap.virtualInventory ?? snap.openSale ?? 0,
                    openSale: snap.openSale ?? 0,
                    badInventory: snap.badInventory ?? 0,
                    putawayPending: snap.putawayPending ?? 0,
                    inventoryBlocked: snap.inventoryBlocked ?? 0,
                };
            });
            // Apply in-stock filter if needed
            const filtered = params.in_stock_only
                ? snapshots.filter((s: any) => s.inventory > 0)
                : snapshots;
            return {
                data: {
                    inventorySnapshots: filtered,
                    items: filtered,          // alias for page compatibility
                    totalCount: totalRecords,
                    totalRecords: totalRecords,
                    totalPages: Math.ceil(totalRecords / params.page_size),
                    total_pages: Math.ceil(totalRecords / params.page_size),
                    method: 'export_job',
                },
            };
        });
    },

    search: (params: { q: string; page: number; page_size: number }) => {
        const payload: any = {
            getInventorySnapshot: true,
            keyword: params.q,
            searchOptions: {
                displayStart: (params.page - 1) * params.page_size,
                displayLength: params.page_size,
            },
        };
        return apiClient.post('/unicommerce-data/catalog-search', payload).then((res) => {
            const elements = res.data?.elements || [];
            const totalRecords = res.data?.totalRecords || elements.length;
            const snapshots = elements.map((el: any) => {
                const snap = el.inventorySnapshots?.[0] || {};
                return {
                    itemTypeSKU: el.skuCode || '',
                    skuCode: el.skuCode || '',
                    name: el.name || el.itemTypeName || '',
                    categoryName: el.categoryName || '',
                    color: el.color || '',
                    size: el.size || '',
                    brand: el.brand || '',
                    costPrice: el.costPrice || el.price || el.mrp || 0,
                    price: el.price ?? el.mrp ?? el.maxRetailPrice ?? el.costPrice ?? 0,
                    mrp: el.mrp ?? el.price ?? el.maxRetailPrice ?? 0,
                    inventory: snap.inventory ?? 0,
                    availableInventory: snap.availableInventory ?? snap.inventory ?? 0,
                    virtualInventory: snap.virtualInventory ?? snap.openSale ?? 0,
                    openSale: snap.openSale ?? 0,
                    badInventory: snap.badInventory ?? 0,
                    putawayPending: snap.putawayPending ?? 0,
                    inventoryBlocked: snap.inventoryBlocked ?? 0,
                };
            });
            return {
                data: {
                    inventorySnapshots: snapshots,
                    items: snapshots,              // alias for page compatibility
                    totalCount: totalRecords,
                    totalRecords: totalRecords,
                    totalPages: Math.ceil(totalRecords / params.page_size),
                    total_pages: Math.ceil(totalRecords / params.page_size),
                    method: 'search' as const,
                },
            };
        });
    },
};
