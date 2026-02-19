'use client';

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { unicommerceApi } from '@/lib/api';
import { PageHeader, LoadingSpinner } from '@/components/ui/Common';
import { DataTable, Column } from '@/components/ui/DataTable';

const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
];

function skuColumns(showRevenue = true): Column<any>[] {
    return [
        {
            key: 'rank',
            header: '#',
            width: '4%',
            render: (value: any) => (
                <span className="font-bold text-slate-500">{value}</span>
            ),
        },
        {
            key: 'sku',
            header: 'SKU Code',
            width: '16%',
            render: (value: string, row: any) => (
                <span className="font-mono text-sm font-semibold text-primary-700 dark:text-primary-300">
                    {value}
                    {row.unpriced && (
                        <span
                            className="ml-1.5 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-400"
                            title="Wholesale/B2B order — pricing not stored in Unicommerce"
                        >
                            W
                        </span>
                    )}
                </span>
            ),
        },
        {
            key: 'name',
            header: 'Product Name',
            width: '24%',
            render: (value: string) => (
                <span className="text-sm max-w-[220px] truncate block">{value || '—'}</span>
            ),
        },
        {
            key: 'quantity',
            header: 'Qty Sold',
            width: '10%',
            render: (value: number) => (
                <span className="font-bold text-emerald-600 dark:text-emerald-400">
                    {value?.toLocaleString('en-IN')}
                </span>
            ),
        },
        ...(showRevenue
            ? [
                {
                    key: 'revenue',
                    header: 'Revenue (₹)',
                    width: '14%',
                    render: (value: number, row: any) => {
                        if (row.unpriced) {
                            return (
                                <span
                                    className="text-orange-500 dark:text-orange-400 text-sm"
                                    title="Price not available — wholesale order"
                                >
                                    N/A <span className="text-[10px]">(wholesale)</span>
                                </span>
                            );
                        }
                        return (
                            <span className="font-semibold text-slate-900 dark:text-slate-100">
                                ₹{(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                                {row.estimated && (
                                    <span
                                        className="ml-1 text-xs text-amber-500"
                                        title="Estimated from MRP"
                                    >
                                        ~
                                    </span>
                                )}
                            </span>
                        );
                    },
                },
                {
                    key: 'avg_price',
                    header: 'Avg Price',
                    width: '11%',
                    render: (value: number, row: any) => {
                        if (row.unpriced) return <span className="text-slate-400">—</span>;
                        return (
                            <span className="text-slate-600 dark:text-slate-400">
                                ₹{(value || 0).toFixed(0)}
                                {row.estimated && (
                                    <span className="ml-1 text-xs text-amber-500">~</span>
                                )}
                            </span>
                        );
                    },
                },
            ]
            : []),
        {
            key: 'order_count',
            header: 'Orders',
            width: '7%',
            render: (value: number) => (
                <span className="font-medium">{(value || 0).toLocaleString('en-IN')}</span>
            ),
        },
        {
            key: 'channels',
            header: 'Top Channel',
            width: '14%',
            render: (value: Record<string, number>) => {
                if (!value) return <span>—</span>;
                const top = Object.entries(value).sort((a, b) => b[1] - a[1])[0];
                return top ? (
                    <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                        {top[0].replace(/_/g, ' ')}
                    </span>
                ) : (
                    <span>—</span>
                );
            },
        },
    ];
}

export default function SkuVelocityPage() {
    const now = new Date();
    const [month, setMonth] = useState(now.getMonth() + 1);
    const [year, setYear] = useState(now.getFullYear());
    const [limit, setLimit] = useState(25);
    const [minQty, setMinQty] = useState(1);
    const [b2cOnly, setB2cOnly] = useState(false);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const queryClient = useQueryClient();

    const { data, isLoading, error } = useQuery({
        queryKey: ['sku-velocity', month, year, limit, minQty, b2cOnly],
        queryFn: async () => {
            const response = await unicommerceApi.getSkuVelocity({
                month,
                year,
                limit,
                min_qty: minQty,
                b2c_only: b2cOnly,
            });
            return response.data;
        },
        staleTime: 5 * 60 * 1000,
    });

    const handleForceRefresh = async () => {
        setIsRefreshing(true);
        try {
            await unicommerceApi.getSkuVelocity({
                month,
                year,
                limit,
                min_qty: minQty,
                b2c_only: b2cOnly,
                force_refresh: true,
            });
            await queryClient.invalidateQueries({
                queryKey: ['sku-velocity', month, year, limit, minQty, b2cOnly],
            });
        } finally {
            setIsRefreshing(false);
        }
    };

    const fastMovers = (data?.fast_movers || []).map((s: any, i: number) => ({
        ...s,
        rank: i + 1,
    }));
    const slowMovers = (data?.slow_movers || []).map((s: any, i: number) => ({
        ...s,
        rank: i + 1,
    }));

    const isBusy = isLoading || isRefreshing;

    return (
        <div className="space-y-6">
            <PageHeader
                title="SKU Velocity"
                description="Monthly fast-moving and slow-moving SKUs from Unicommerce"
            />

            {/* Controls */}
            <div className="card">
                <div className="flex flex-wrap gap-4 items-end">
                    {/* Month */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Month
                        </label>
                        <select
                            value={month}
                            onChange={(e) => setMonth(Number(e.target.value))}
                            className="input w-auto"
                        >
                            {monthNames.map((m, i) => (
                                <option key={i} value={i + 1}>
                                    {m}
                                </option>
                            ))}
                        </select>
                    </div>

                    {/* Year */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Year
                        </label>
                        <select
                            value={year}
                            onChange={(e) => setYear(Number(e.target.value))}
                            className="input w-auto"
                        >
                            {[2024, 2025, 2026].map((y) => (
                                <option key={y} value={y}>
                                    {y}
                                </option>
                            ))}
                        </select>
                    </div>

                    {/* Top N */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Top / Bottom N
                        </label>
                        <select
                            value={limit}
                            onChange={(e) => setLimit(Number(e.target.value))}
                            className="input w-auto"
                        >
                            {[10, 25, 50, 100].map((n) => (
                                <option key={n} value={n}>
                                    {n} SKUs
                                </option>
                            ))}
                        </select>
                    </div>

                    {/* Min Qty for slow movers */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Min Qty (slow)
                        </label>
                        <select
                            value={minQty}
                            onChange={(e) => setMinQty(Number(e.target.value))}
                            className="input w-auto"
                        >
                            {[1, 2, 5, 10].map((n) => (
                                <option key={n} value={n}>
                                    ≥ {n}
                                </option>
                            ))}
                        </select>
                    </div>

                    {/* B2C Only toggle */}
                    <div className="flex items-center gap-2 pb-1">
                        <button
                            onClick={() => setB2cOnly(!b2cOnly)}
                            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${b2cOnly
                                    ? 'bg-primary-600'
                                    : 'bg-slate-300 dark:bg-slate-600'
                                }`}
                        >
                            <span
                                className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${b2cOnly ? 'translate-x-6' : 'translate-x-1'
                                    }`}
                            />
                        </button>
                        <label
                            className="text-sm font-medium text-gray-700 dark:text-gray-300 cursor-pointer"
                            onClick={() => setB2cOnly(!b2cOnly)}
                        >
                            B2C Only{' '}
                            <span className="text-xs text-slate-500">(hide wholesale)</span>
                        </label>
                    </div>

                    {/* Refresh */}
                    <button
                        onClick={handleForceRefresh}
                        disabled={isBusy}
                        className="btn btn-secondary ml-auto disabled:opacity-60"
                        title="Clear cache and re-fetch all orders for this month"
                    >
                        {isRefreshing ? '⟳ Refreshing...' : '⟳ Refresh Data'}
                    </button>
                </div>
            </div>

            {/* Summary badges */}
            {data?.success && !isBusy && (
                <div className="flex flex-wrap gap-3">
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 dark:bg-slate-800 px-3 py-1 text-sm text-slate-600 dark:text-slate-300">
                        <span className="font-semibold text-slate-800 dark:text-slate-100">
                            {data.total_skus?.toLocaleString('en-IN')}
                        </span>{' '}
                        unique SKUs sold
                    </span>
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 dark:bg-slate-800 px-3 py-1 text-sm text-slate-600 dark:text-slate-300">
                        <span className="font-semibold text-slate-800 dark:text-slate-100">
                            {data.total_orders?.toLocaleString('en-IN')}
                        </span>{' '}
                        total orders
                    </span>
                    {data._cached && (
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 dark:bg-slate-700 px-3 py-1 text-xs text-slate-500 dark:text-slate-400">
                            Cached data
                        </span>
                    )}
                </div>
            )}

            {/* Error */}
            {error && (
                <div className="card bg-rose-50 dark:bg-rose-900/20">
                    <p className="text-rose-600 dark:text-rose-400">
                        Error: {(error as any)?.message || 'Failed to load data'}
                    </p>
                </div>
            )}

            {isBusy ? (
                <LoadingSpinner message="Fetching monthly sales data from all channels… (this may take a few minutes on first load)" />
            ) : (
                <>
                    {/* ── Fast Movers ─────────────────────────────────── */}
                    <div className="card">
                        <div className="flex items-center justify-between mb-4">
                            <div className="flex items-center gap-3">
                                <span className="text-2xl">🚀</span>
                                <div>
                                    <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
                                        Fast Moving SKUs
                                    </h2>
                                    <p className="text-xs text-slate-500 dark:text-slate-400">
                                        Top {limit} by quantity sold — {monthNames[month - 1]} {year}
                                        {b2cOnly && (
                                            <span className="ml-2 text-primary-600 dark:text-primary-400">
                                                (B2C only)
                                            </span>
                                        )}
                                    </p>
                                </div>
                            </div>
                            <span className="inline-flex items-center rounded-full bg-emerald-100 dark:bg-emerald-900/40 px-3 py-1 text-sm font-semibold text-emerald-700 dark:text-emerald-400">
                                {fastMovers.length} SKUs
                            </span>
                        </div>

                        <div className="mb-3 flex items-center gap-2">
                            <div className="h-1.5 flex-1 rounded-full bg-gradient-to-r from-emerald-400 to-teal-500 opacity-60" />
                        </div>

                        <DataTable
                            data={fastMovers}
                            columns={skuColumns(true)}
                            emptyMessage="No sales data found for the selected period."
                        />
                    </div>

                    {/* ── Slow Movers ─────────────────────────────────── */}
                    <div className="card">
                        <div className="flex items-center justify-between mb-4">
                            <div className="flex items-center gap-3">
                                <span className="text-2xl">🐢</span>
                                <div>
                                    <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
                                        Slow Moving SKUs
                                    </h2>
                                    <p className="text-xs text-slate-500 dark:text-slate-400">
                                        Bottom {limit} by quantity sold (min {minQty} unit
                                        {minQty !== 1 ? 's' : ''}) — {monthNames[month - 1]} {year}
                                        {b2cOnly && (
                                            <span className="ml-2 text-primary-600 dark:text-primary-400">
                                                (B2C only)
                                            </span>
                                        )}
                                    </p>
                                </div>
                            </div>
                            <span className="inline-flex items-center rounded-full bg-rose-100 dark:bg-rose-900/40 px-3 py-1 text-sm font-semibold text-rose-700 dark:text-rose-400">
                                {slowMovers.length} SKUs
                            </span>
                        </div>

                        <div className="mb-3 flex items-center gap-2">
                            <div className="h-1.5 flex-1 rounded-full bg-gradient-to-r from-rose-400 to-pink-500 opacity-60" />
                        </div>

                        <DataTable
                            data={slowMovers}
                            columns={skuColumns(true)}
                            emptyMessage={
                                `No SKUs found with at least ${minQty} unit${minQty !== 1 ? 's' : ''} sold in ${monthNames[month - 1]} ${year}.`
                            }
                        />
                    </div>
                </>
            )}
        </div>
    );
}
