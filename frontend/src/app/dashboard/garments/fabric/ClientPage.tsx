'use client';

import { useState, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ucSales } from '@/features/sales/api';
import { PageHeader, ProgressLoader } from '@/components/ui/Common';
import { DataTable, Column } from '@/components/ui/DataTable';

type FilterMode = 'monthly' | 'custom';

export default function FabricPage() {
    const now = new Date();
    const [filterMode, setFilterMode] = useState<FilterMode>('monthly');
    const [month, setMonth] = useState(now.getMonth() + 1);
    const [year, setYear] = useState(now.getFullYear());
    const [fromDate, setFromDate] = useState('');
    const [toDate, setToDate] = useState('');
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [currentPage, setCurrentPage] = useState(1);
    const pageSize = 25;
    const queryClient = useQueryClient();

    const queryParams = useMemo(() => {
        if (filterMode === 'custom' && fromDate && toDate) {
            return { from_date: fromDate, to_date: toDate };
        }
        return { month, year };
    }, [filterMode, month, year, fromDate, toDate]);

    const queryKey = useMemo(() => {
        if (filterMode === 'custom' && fromDate && toDate) {
            return ['fabric-sales', 'custom', fromDate, toDate];
        }
        return ['fabric-sales', 'monthly', month, year];
    }, [filterMode, month, year, fromDate, toDate]);

    const { data, isLoading, error } = useQuery({
        queryKey,
        queryFn: async () => {
            const response = await ucSales.getFabricSales(queryParams);
            return response.data;
        },
        staleTime: 5 * 60 * 1000,
        enabled: filterMode === 'monthly' || (!!fromDate && !!toDate),
    });

    const handleForceRefresh = async () => {
        setIsRefreshing(true);
        try {
            await ucSales.getFabricSales({ ...queryParams, force_refresh: true });
            await queryClient.invalidateQueries({ queryKey });
        } finally {
            setIsRefreshing(false);
        }
    };

    const allItems = (data?.items || []).map((item: any, i: number) => ({ ...item, rank: i + 1 }));
    const summary = data?.summary || {};

    // Pagination
    const totalItems = allItems.length;
    const totalPages = Math.ceil(totalItems / pageSize);
    const paginatedItems = allItems.slice((currentPage - 1) * pageSize, currentPage * pageSize);

    // Reset to page 1 when data changes
    const dataKey = JSON.stringify(queryKey);
    const [prevDataKey, setPrevDataKey] = useState(dataKey);
    if (dataKey !== prevDataKey) {
        setPrevDataKey(dataKey);
        setCurrentPage(1);
    }

    const columns: Column<any>[] = [
        {
            key: 'rank', header: '#', width: '6%',
            render: (value: any) => <span className="font-bold text-slate-500">{value}</span>,
        },
        {
            key: 'soiCode', header: 'Sale Order Item Code', width: '30%',
            render: (value: string) => (
                <span className="font-mono text-sm font-semibold text-primary-700 dark:text-primary-300">
                    {value || '-'}
                </span>
            ),
        },
        {
            key: 'sku', header: 'SKU Code', width: '30%',
            render: (value: string) => (
                <span className="font-mono text-sm text-slate-700 dark:text-slate-300">
                    {value || '-'}
                </span>
            ),
        },
        {
            key: 'orderCode', header: 'Order Code', width: '24%',
            render: (value: string) => (
                <span className="text-sm text-slate-600 dark:text-slate-400">
                    {value || '-'}
                </span>
            ),
        },
    ];

    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'];

    const periodLabel = filterMode === 'custom' && fromDate && toDate
        ? `${fromDate} to ${toDate}`
        : `${monthNames[month - 1]} ${year}`;

    return (
        <div className="space-y-6">
            <PageHeader title="Fabric" description="Fabric category items from Unicommerce" />

            {/* Controls */}
            <div className="card">
                <div className="flex flex-wrap gap-4 items-end">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Filter</label>
                        <div className="flex rounded-lg overflow-hidden border border-slate-300 dark:border-slate-600">
                            <button
                                onClick={() => setFilterMode('monthly')}
                                className={`px-3 py-2 text-sm font-medium transition-colors ${filterMode === 'monthly'
                                    ? 'bg-primary-600 text-white'
                                    : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'
                                    }`}
                            >
                                Monthly
                            </button>
                            <button
                                onClick={() => setFilterMode('custom')}
                                className={`px-3 py-2 text-sm font-medium transition-colors ${filterMode === 'custom'
                                    ? 'bg-primary-600 text-white'
                                    : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'
                                    }`}
                            >
                                Custom
                            </button>
                        </div>
                    </div>

                    {filterMode === 'monthly' ? (
                        <>
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
                        </>
                    ) : (
                        <>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">From</label>
                                <input
                                    type="date"
                                    value={fromDate}
                                    onChange={(e) => setFromDate(e.target.value)}
                                    className="input w-auto"
                                    max={toDate || undefined}
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">To</label>
                                <input
                                    type="date"
                                    value={toDate}
                                    onChange={(e) => setToDate(e.target.value)}
                                    className="input w-auto"
                                    min={fromDate || undefined}
                                    max={new Date().toISOString().split('T')[0]}
                                />
                            </div>
                        </>
                    )}

                    <button
                        onClick={handleForceRefresh}
                        disabled={isRefreshing || isLoading || (filterMode === 'custom' && (!fromDate || !toDate))}
                        className="btn btn-secondary ml-auto disabled:opacity-60"
                    >
                        {isRefreshing ? '⟳ Refreshing...' : '⟳ Refresh Data'}
                    </button>
                </div>
            </div>

            {/* Summary Cards */}
            {data?.success && (
                <div className="grid grid-cols-2 gap-4">
                    <div className="card text-center">
                        <p className="text-sm text-slate-500 dark:text-slate-400 mb-1">Total Orders</p>
                        <p className="text-2xl font-bold text-slate-900 dark:text-white">
                            {(summary.total_orders || 0).toLocaleString('en-IN')}
                        </p>
                    </div>
                    <div className="card text-center">
                        <p className="text-sm text-slate-500 dark:text-slate-400 mb-1">Total Items</p>
                        <p className="text-2xl font-bold text-slate-900 dark:text-white">
                            {(summary.total_items || 0).toLocaleString('en-IN')}
                        </p>
                    </div>
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
                        Fabric Items — {periodLabel}
                    </h2>
                    <div className="flex items-center gap-3">
                        {data?.total_items_count != null && (
                            <span className="text-xs text-slate-500">{data.total_items_count} items</span>
                        )}
                        {data?._cached && (
                            <span className="text-xs text-slate-400 dark:text-slate-500">Cached</span>
                        )}
                    </div>
                </div>
                <ProgressLoader loading={isLoading || isRefreshing} stages={[
                    { at: 0, label: 'Initializing export job…' },
                    { at: 15, label: 'Fetching fabric orders…' },
                    { at: 40, label: 'Parsing sale order items…' },
                    { at: 70, label: 'Building fabric report…' },
                    { at: 90, label: 'Finalizing…' },
                ]} />
                {!(isLoading || isRefreshing) && (
                    <>
                        <DataTable
                            data={paginatedItems}
                            columns={columns}
                            emptyMessage="No fabric data found for the selected period."
                        />
                        {totalPages > 1 && (
                            <div className="flex items-center justify-between mt-4 pt-4 border-t border-slate-200 dark:border-slate-700">
                                <p className="text-sm text-slate-500 dark:text-slate-400">
                                    Showing {(currentPage - 1) * pageSize + 1}–{Math.min(currentPage * pageSize, totalItems)} of {totalItems}
                                </p>
                                <div className="flex items-center gap-1">
                                    <button onClick={() => setCurrentPage(1)} disabled={currentPage === 1}
                                        className="px-2 py-1 text-sm rounded hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed">««</button>
                                    <button onClick={() => setCurrentPage((p) => Math.max(1, p - 1))} disabled={currentPage === 1}
                                        className="px-2 py-1 text-sm rounded hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed">«</button>
                                    {Array.from({ length: totalPages }, (_, i) => i + 1)
                                        .filter((p) => p === 1 || p === totalPages || Math.abs(p - currentPage) <= 1)
                                        .reduce((acc: (number | string)[], p, idx, arr) => {
                                            if (idx > 0 && (p as number) - (arr[idx - 1] as number) > 1) acc.push('...');
                                            acc.push(p);
                                            return acc;
                                        }, [])
                                        .map((p, idx) =>
                                            typeof p === 'string' ? (
                                                <span key={`e-${idx}`} className="px-1 text-slate-400">…</span>
                                            ) : (
                                                <button key={p} onClick={() => setCurrentPage(p)}
                                                    className={`px-3 py-1 text-sm rounded font-medium transition-colors ${currentPage === p
                                                        ? 'bg-primary-600 text-white'
                                                        : 'hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300'
                                                        }`}>{p}</button>
                                            )
                                        )}
                                    <button onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))} disabled={currentPage === totalPages}
                                        className="px-2 py-1 text-sm rounded hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed">»</button>
                                    <button onClick={() => setCurrentPage(totalPages)} disabled={currentPage === totalPages}
                                        className="px-2 py-1 text-sm rounded hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed">»»</button>
                                </div>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}
