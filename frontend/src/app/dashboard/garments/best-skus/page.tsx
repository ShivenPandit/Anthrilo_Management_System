'use client';

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { unicommerceApi } from '@/lib/api';
import { PageHeader, LoadingSpinner } from '@/components/ui/Common';
import { DataTable, Column } from '@/components/ui/DataTable';

export default function BestSkusPage() {
    const now = new Date();
    const [month, setMonth] = useState(now.getMonth() + 1);
    const [year, setYear] = useState(now.getFullYear());
    const [limit, setLimit] = useState(25);
    const [b2cOnly, setB2cOnly] = useState(false);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const queryClient = useQueryClient();

    const { data, isLoading, error } = useQuery({
        queryKey: ['best-skus-monthly', month, year, limit, b2cOnly],
        queryFn: async () => {
            const response = await unicommerceApi.getBestSkusMonthly({ month, year, limit, b2c_only: b2cOnly });
            return response.data;
        },
        staleTime: 5 * 60 * 1000,
    });

    const handleForceRefresh = async () => {
        setIsRefreshing(true);
        try {
            await unicommerceApi.getBestSkusMonthly({ month, year, limit, b2c_only: b2cOnly, force_refresh: true });
            await queryClient.invalidateQueries({ queryKey: ['best-skus-monthly', month, year, limit, b2cOnly] });
        } finally {
            setIsRefreshing(false);
        }
    };

    const skus = (data?.skus || []).map((s: any, i: number) => ({ ...s, rank: i + 1 }));
    const hasEstimated = skus.some((s: any) => s.estimated);
    const hasUnpriced = skus.some((s: any) => s.unpriced);
    const unpricedCount = data?.unpriced_in_top ?? 0;

    const columns: Column<any>[] = [
        {
            key: 'rank', header: '#', width: '4%',
            render: (value: any) => <span className="font-bold text-slate-500">{value}</span>,
        },
        {
            key: 'sku', header: 'SKU Code', width: '16%',
            render: (value: string, row: any) => (
                <span className="font-mono text-sm font-semibold text-primary-700 dark:text-primary-300">
                    {value}
                    {row.unpriced && (
                        <span
                            className="ml-1.5 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-400"
                            title="Wholesale/B2B order — pricing not stored in Unicommerce (invoiced externally)"
                        >W</span>
                    )}
                </span>
            ),
        },
        {
            key: 'name', header: 'Product Name', width: '22%',
            render: (value: string) => <span className="text-sm max-w-[200px] truncate block">{value || '-'}</span>,
        },
        {
            key: 'quantity', header: 'Qty Sold', width: '8%',
            render: (value: number) => <span className="font-bold text-emerald-600 dark:text-emerald-400">{value?.toLocaleString('en-IN')}</span>,
        },
        {
            key: 'revenue', header: 'Revenue (₹)', width: '14%',
            render: (value: number, row: any) => {
                if (row.unpriced) {
                    return (
                        <span className="text-orange-500 dark:text-orange-400 text-sm" title="Price not available in Unicommerce — wholesale order billed externally">
                            N/A <span className="text-[10px]">(wholesale)</span>
                        </span>
                    );
                }
                return (
                    <span className="font-semibold text-slate-900 dark:text-slate-100">
                        ₹{(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                        {row.estimated && (
                            <span className="ml-1 text-xs text-amber-500" title="Revenue estimated from MRP — channel does not report selling price">~</span>
                        )}
                    </span>
                );
            },
        },
        {
            key: 'orders', header: 'Orders', width: '10%',
            render: (value: number) => <span className="font-medium">{value}</span>,
        },
        {
            key: 'avg_price', header: 'Avg Price', width: '11%',
            render: (value: number, row: any) => {
                if (row.unpriced) return <span className="text-slate-400">—</span>;
                return (
                    <span className="text-slate-600 dark:text-slate-400">
                        ₹{(value || 0).toFixed(0)}
                        {row.estimated && <span className="ml-1 text-xs text-amber-500">~</span>}
                    </span>
                );
            },
        },
        {
            key: 'channels', header: 'Top Channel', width: '10%',
            render: (value: Record<string, number>) => {
                if (!value) return <span>-</span>;
                const top = Object.entries(value).sort((a, b) => b[1] - a[1])[0];
                return top ? (
                    <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                        {top[0].replace(/_/g, ' ')}
                    </span>
                ) : <span>-</span>;
            },
        },
    ];

    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'];

    return (
        <div className="space-y-6">
            <PageHeader title="Best Performing SKUs" description="Monthly top-selling SKUs from Unicommerce" />

            {/* Controls */}
            <div className="card">
                <div className="flex flex-wrap gap-4 items-end">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Month</label>
                        <select value={month} onChange={(e) => setMonth(Number(e.target.value))} className="input w-auto">
                            {monthNames.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Year</label>
                        <select value={year} onChange={(e) => setYear(Number(e.target.value))} className="input w-auto">
                            {[2024, 2025, 2026].map((y) => <option key={y} value={y}>{y}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Top N</label>
                        <select value={limit} onChange={(e) => setLimit(Number(e.target.value))} className="input w-auto">
                            {[10, 25, 50, 100].map((n) => <option key={n} value={n}>Top {n}</option>)}
                        </select>
                    </div>
                    {/* B2C Only toggle */}
                    <div className="flex items-center gap-2 pb-1">
                        <button
                            onClick={() => setB2cOnly(!b2cOnly)}
                            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${b2cOnly ? 'bg-primary-600' : 'bg-slate-300 dark:bg-slate-600'}`}
                        >
                            <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${b2cOnly ? 'translate-x-6' : 'translate-x-1'}`} />
                        </button>
                        <label className="text-sm font-medium text-gray-700 dark:text-gray-300 cursor-pointer" onClick={() => setB2cOnly(!b2cOnly)}>
                            B2C Only <span className="text-xs text-slate-500">(hide wholesale)</span>
                        </label>
                    </div>
                    <button
                        onClick={handleForceRefresh}
                        disabled={isRefreshing || isLoading}
                        className="btn btn-secondary ml-auto disabled:opacity-60"
                        title="Clear cache and re-fetch all orders for this month"
                    >
                        {isRefreshing ? '⟳ Refreshing...' : '⟳ Refresh Data'}
                    </button>
                </div>
            </div>

            {/* Notices */}
            {hasUnpriced && !b2cOnly && (
                <div className="card bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800">
                    <p className="text-sm text-orange-800 dark:text-orange-300">
                        <span className="font-semibold">W = Wholesale/B2B:</span> {unpricedCount} SKU{unpricedCount !== 1 ? 's' : ''} in this list
                        are sold through bulk B2B SHOPIFY orders where Unicommerce stores no unit prices
                        (invoicing is handled externally). Revenue shows <strong>N/A</strong> for these.
                        Toggle <strong>B2C Only</strong> above to hide them and see retail-only rankings.
                    </p>
                </div>
            )}
            {hasEstimated && (
                <div className="card bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
                    <p className="text-sm text-amber-800 dark:text-amber-300">
                        <span className="font-semibold">~ Estimated revenue:</span> Some SKUs (e.g. Amazon Flex) do not report
                        individual selling prices. Revenue for those SKUs is estimated from MRP and may be higher than actual realized amount.
                    </p>
                </div>
            )}

            {/* Error */}
            {error && (
                <div className="card bg-rose-50 dark:bg-rose-900/20">
                    <p className="text-rose-600 dark:text-rose-400">Error: {(error as any)?.message || 'Failed to load data'}</p>
                </div>
            )}

            {/* Table */}
            <div className="card">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-slate-900 dark:text-white font-semibold">
                        Top {limit} SKUs — {monthNames[month - 1]} {year}
                        {b2cOnly && <span className="ml-2 text-xs font-normal text-primary-600 dark:text-primary-400">(B2C only)</span>}
                    </h2>
                    <div className="flex items-center gap-3">
                        {data?.total_orders && (
                            <span className="text-xs text-slate-500">{data.total_orders.toLocaleString('en-IN')} orders fetched</span>
                        )}
                        {data?._cached && (
                            <span className="text-xs text-slate-400 dark:text-slate-500">Cached data</span>
                        )}
                    </div>
                </div>
                {isLoading || isRefreshing ? (
                    <LoadingSpinner message="Fetching monthly sales data from all channels... (this may take a few minutes on first load)" />
                ) : (
                    <DataTable
                        data={skus}
                        columns={columns}
                        emptyMessage="No sales data found for the selected period."
                    />
                )}
            </div>
        </div>
    );
}
