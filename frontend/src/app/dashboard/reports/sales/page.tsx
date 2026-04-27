'use client';

import { useQuery } from '@tanstack/react-query';
import { unicommerceApi } from '@/features/sales/api';
import { useState, useMemo, useEffect } from 'react';
import {
    ReportDateMode,
    resolveReportDateRange,
} from '@/lib/report-date-range';

// Format currency
const formatCurrency = (value: number | undefined | null): string => {
    if (value === undefined || value === null || isNaN(value)) return '₹0';
    if (value >= 10000000) return `₹${(value / 10000000).toFixed(2)} Cr`;
    if (value >= 100000) return `₹${(value / 100000).toFixed(2)} L`;
    if (value >= 1000) return `₹${(value / 1000).toFixed(1)}K`;
    return `₹${value.toFixed(2)}`;
};

// Status badge colors
const statusColors: Record<string, string> = {
    'COMPLETE': 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
    'PROCESSING': 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
    'CANCELLED': 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
    'CANCELED': 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
    'RETURNED': 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
    'PENDING': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300',
    'CREATED': 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
};

// Pagination Component
const Pagination = ({
    currentPage,
    totalPages,
    onPageChange,
    disabled
}: {
    currentPage: number;
    totalPages: number;
    onPageChange: (page: number) => void;
    disabled: boolean;
}) => {
    const pages = useMemo(() => {
        const items: (number | string)[] = [];
        const showEllipsis = totalPages > 7;

        if (!showEllipsis) {
            for (let i = 1; i <= totalPages; i++) items.push(i);
        } else {
            items.push(1);
            if (currentPage > 3) items.push('...');

            const start = Math.max(2, currentPage - 1);
            const end = Math.min(totalPages - 1, currentPage + 1);

            for (let i = start; i <= end; i++) items.push(i);

            if (currentPage < totalPages - 2) items.push('...');
            if (totalPages > 1) items.push(totalPages);
        }

        return items;
    }, [currentPage, totalPages]);

    return (
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-center gap-2">
            <button
                onClick={() => onPageChange(currentPage - 1)}
                disabled={disabled || currentPage <= 1}
                className="w-full sm:w-auto px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
                ← Previous
            </button>

            <div className="flex items-center gap-1 overflow-x-auto max-w-full">
                {pages.map((page, i) => (
                    typeof page === 'number' ? (
                        <button
                            key={i}
                            onClick={() => onPageChange(page)}
                            disabled={disabled}
                            className={`w-9 h-9 sm:w-10 sm:h-10 rounded-lg font-medium transition-colors shrink-0 ${page === currentPage
                                ? 'bg-primary-600 text-white'
                                : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
                                }`}
                        >
                            {page}
                        </button>
                    ) : (
                        <span key={i} className="px-2 text-gray-400">...</span>
                    )
                ))}
            </div>

            <button
                onClick={() => onPageChange(currentPage + 1)}
                disabled={disabled || currentPage >= totalPages}
                className="w-full sm:w-auto px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
                Next →
            </button>
        </div>
    );
};

// Channel Revenue Chart
const ChannelChart = ({ channels }: { channels: any[] }) => {
    if (!channels?.length) return <p className="text-gray-500 text-center py-4">No channel data</p>;

    const maxRevenue = Math.max(...channels.map(c => c.revenue || 0), 1);

    return (
        <div className="space-y-3">
            {channels.slice(0, 8).map((channel, i) => (
                <div key={i} className="flex items-center gap-3">
                    <span className="text-sm text-gray-600 dark:text-gray-400 w-28 truncate font-medium">
                        {channel.channel}
                    </span>
                    <div className="flex-1 bg-gray-100 dark:bg-gray-700 rounded-full h-6 overflow-hidden">
                        <div
                            className="h-full bg-gradient-to-r from-green-500 to-emerald-500 transition-all duration-500 flex items-center justify-end pr-2"
                            style={{ width: `${Math.max((channel.revenue / maxRevenue) * 100, 5)}%` }}
                        >
                            {channel.revenue > maxRevenue * 0.15 && (
                                <span className="text-xs text-white font-medium">
                                    {formatCurrency(channel.revenue)}
                                </span>
                            )}
                        </div>
                    </div>
                    {channel.revenue <= maxRevenue * 0.15 && (
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300 w-20 text-right">
                            {formatCurrency(channel.revenue)}
                        </span>
                    )}
                    <span className="text-xs text-gray-500 w-12 text-right">
                        {channel.percentage?.toFixed(1)}%
                    </span>
                </div>
            ))}
        </div>
    );
};

export default function SalesReportsPage() {
    // State
    const [dateMode, setDateMode] = useState<ReportDateMode>('daily');
    const [anchorDate, setAnchorDate] = useState(() => {
        const date = new Date();
        date.setDate(date.getDate() - 1);
        return date.toISOString().split('T')[0];
    });
    const [latestAnchorApplied, setLatestAnchorApplied] = useState(false);
    const [currentPage, setCurrentPage] = useState(1);
    const [customDates, setCustomDates] = useState({
        from: new Date().toISOString().split('T')[0],
        to: new Date().toISOString().split('T')[0]
    });

    const { data: recentSalesData } = useQuery({
        queryKey: ['salesReports-recent-sales'],
        queryFn: async () => (await unicommerceApi.getLast7Days()).data,
        staleTime: 10 * 60 * 1000,
    });

    const latestAvailableDate = useMemo(() => {
        const breakdown = recentSalesData?.summary?.daily_breakdown;
        if (!Array.isArray(breakdown) || breakdown.length === 0) return '';
        for (let index = breakdown.length - 1; index >= 0; index -= 1) {
            const day = breakdown[index];
            if ((day?.orders || 0) > 0 || (day?.revenue || 0) > 0) {
                return String(day.date || '');
            }
        }
        return '';
    }, [recentSalesData]);

    useEffect(() => {
        if (dateMode !== 'daily' || latestAnchorApplied || !latestAvailableDate) return;
        setAnchorDate(latestAvailableDate);
        setLatestAnchorApplied(true);
    }, [dateMode, latestAnchorApplied, latestAvailableDate]);

    const effectiveRange = useMemo(() => resolveReportDateRange({
        mode: dateMode,
        anchorDate,
        fromDate: customDates.from,
        toDate: customDates.to,
    }), [dateMode, anchorDate, customDates]);

    // Fetch summary data
    const { data: report, isLoading: summaryLoading, error: summaryError, refetch } = useQuery({
        queryKey: ['salesReport', dateMode, effectiveRange.fromDate, effectiveRange.toDate],
        queryFn: async () => {
            const params: any = {
                period: 'custom',
                from_date: effectiveRange.fromDate,
                to_date: effectiveRange.toDate,
            };
            const response = await unicommerceApi.getSalesReport(params);
            return response.data;
        },
        refetchInterval: 5 * 60 * 1000, // 5 minutes
        staleTime: 2 * 60 * 1000,
        retry: 1,
    });

    // Fetch paginated orders
    const { data: ordersData, isLoading: ordersLoading, isFetching: ordersFetching } = useQuery({
        queryKey: ['salesOrders', dateMode, effectiveRange.fromDate, effectiveRange.toDate, currentPage],
        queryFn: async () => {
            const response = await unicommerceApi.getCustomOrders({
                from_date: effectiveRange.fromDate,
                to_date: effectiveRange.toDate,
                page: currentPage,
                page_size: 12
            });
            return response.data;
        },
        refetchInterval: 5 * 60 * 1000,
        staleTime: 1 * 60 * 1000,
    });

    // Extract data
    const summary = useMemo(() => report?.summary ?? {}, [report?.summary]);
    const orders = ordersData?.orders || [];
    const pagination = ordersData?.pagination || { total_pages: 1, current_page: 1 };

    // Derive channel data from summary instead of a separate API call
    const channels = useMemo(() => {
        const breakdown = summary?.channel_breakdown || {};
        const totalRevenue = summary?.total_revenue || 0;
        return Object.entries(breakdown)
            .map(([channel, data]: [string, any]) => ({
                channel,
                orders: data.orders || 0,
                revenue: data.revenue || 0,
                percentage: totalRevenue > 0 ? ((data.revenue || 0) / totalRevenue) * 100 : 0,
            }))
            .sort((a, b) => b.revenue - a.revenue);
    }, [summary]);

    // Reset page when range mode changes
    const handleModeChange = (mode: ReportDateMode) => {
        setDateMode(mode);
        setCurrentPage(1);
    };

    const isLoading = summaryLoading || ordersLoading;

    return (
        <div className="page-section-gap">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                        📊 Sales Analytics
                    </h1>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                        Revenue calculated using <span className="font-semibold text-green-600">sellingPrice</span> only • 100% accurate
                    </p>
                </div>
                <button
                    onClick={() => refetch()}
                    disabled={isLoading}
                    className="w-full sm:w-auto px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center justify-center gap-2 transition-colors"
                >
                    {isLoading ? (
                        <span className="h-4 w-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    ) : (
                        <span>🔄</span>
                    )}
                    Refresh
                </button>
            </div>

            {/* Global Date Range */}
            <div className="card">
                <div className="space-y-3">
                    <div className="tab-strip">
                        {([
                            { id: 'daily', label: 'Daily' },
                            { id: 'weekly', label: 'Weekly' },
                            { id: 'monthly', label: 'Monthly' },
                            { id: 'custom', label: 'Custom' },
                        ] as const).map((filter) => (
                            <button
                                key={filter.id}
                                onClick={() => handleModeChange(filter.id)}
                                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap ${dateMode === filter.id
                                    ? 'bg-primary-600 text-white shadow-lg'
                                    : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
                                    }`}
                            >
                                {filter.label}
                            </button>
                        ))}
                    </div>

                    <div className="flex flex-col lg:flex-row lg:items-center gap-2">
                        {dateMode === 'daily' && (
                            <div className="flex flex-col sm:flex-row sm:items-center gap-2 w-full lg:w-auto">
                                <span className="text-sm text-gray-600 dark:text-gray-400">Report Date</span>
                                <input
                                    type="date"
                                    value={anchorDate}
                                    onChange={(e) => {
                                        setAnchorDate(e.target.value);
                                        setCurrentPage(1);
                                    }}
                                    className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm w-full sm:w-auto"
                                />
                            </div>
                        )}

                        {dateMode === 'custom' && (
                            <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_1fr] gap-2 w-full lg:w-auto">
                                <input
                                    type="date"
                                    value={customDates.from}
                                    onChange={(e) => {
                                        setCustomDates(d => ({ ...d, from: e.target.value }));
                                        setCurrentPage(1);
                                    }}
                                    className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm w-full"
                                />
                                <span className="text-gray-500 self-center text-center">to</span>
                                <input
                                    type="date"
                                    value={customDates.to}
                                    onChange={(e) => {
                                        setCustomDates(d => ({ ...d, to: e.target.value }));
                                        setCurrentPage(1);
                                    }}
                                    className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm w-full"
                                />
                            </div>
                        )}

                        <div className="text-xs text-gray-500 dark:text-gray-400">{effectiveRange.label}</div>
                    </div>
                </div>
            </div>

            {/* Loading State */}
            {summaryLoading && (
                <div className="card py-12 text-center">
                    <div className="inline-flex items-center gap-3 text-gray-600 dark:text-gray-400">
                        <span className="h-8 w-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" />
                        <span className="text-lg">Fetching sales data...</span>
                    </div>
                </div>
            )}

            {/* Error State */}
            {summaryError && !summaryLoading && (
                <div className="card bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800">
                    <div className="flex items-center gap-3 text-red-600 dark:text-red-400">
                        <span className="text-2xl">⚠️</span>
                        <div>
                            <p className="font-semibold">Failed to load report</p>
                            <p className="text-sm">{(summaryError as Error).message}</p>
                        </div>
                    </div>
                </div>
            )}

            {/* Summary Cards */}
            {report?.success && !summaryLoading && (
                <>
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                        <div className="card bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border-blue-200 dark:border-blue-800">
                            <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">Total Orders</p>
                            <p className="text-2xl font-bold text-blue-600 dark:text-blue-400 mt-1">
                                {(summary.total_orders || 0).toLocaleString()}
                            </p>
                        </div>
                        <div className="card bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 border-green-200 dark:border-green-800">
                            <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">Valid Orders</p>
                            <p className="text-2xl font-bold text-green-600 dark:text-green-400 mt-1">
                                {(summary.valid_orders || 0).toLocaleString()}
                            </p>
                        </div>
                        <div className="card bg-gradient-to-br from-emerald-50 to-teal-50 dark:from-emerald-900/20 dark:to-teal-900/20 border-emerald-200 dark:border-emerald-800 col-span-2 md:col-span-1">
                            <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">Total Revenue</p>
                            <p className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-1">
                                {formatCurrency(summary.total_revenue)}
                            </p>
                            <p className="text-xs text-gray-500 mt-1">sellingPrice only</p>
                        </div>
                        <div className="card">
                            <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">Discounts</p>
                            <p className="text-2xl font-bold text-orange-600 dark:text-orange-400 mt-1">
                                {formatCurrency(summary.total_discount)}
                            </p>
                        </div>
                        <div className="card">
                            <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">Refunds</p>
                            <p className="text-2xl font-bold text-red-600 dark:text-red-400 mt-1">
                                {formatCurrency(summary.total_refund)}
                            </p>
                        </div>
                        <div className="card">
                            <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">Avg Order Value</p>
                            <p className="text-2xl font-bold text-purple-600 dark:text-purple-400 mt-1">
                                {formatCurrency(summary.avg_order_value)}
                            </p>
                        </div>
                    </div>

                    {/* Excluded orders warning */}
                    {(summary.excluded_orders || 0) > 0 && (
                        <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg border border-yellow-200 dark:border-yellow-800 text-sm text-yellow-800 dark:text-yellow-200">
                            ⚠️ {summary.excluded_orders.toLocaleString()} orders excluded from revenue (cancelled/returned/refunded)
                        </div>
                    )}

                    {/* Channel Revenue */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <div className="card">
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                                📊 Revenue by Channel
                            </h3>
                            <ChannelChart channels={channels} />
                        </div>

                        {/* Status Breakdown */}
                        <div className="card">
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                                📋 Order Status
                            </h3>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                {Object.entries(summary.status_breakdown || {})
                                    .sort((a, b) => (b[1] as number) - (a[1] as number))
                                    .slice(0, 8)
                                    .map(([status, count], i) => (
                                        <div key={i} className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-800 rounded-lg">
                                            <span className={`px-2 py-1 text-xs font-medium rounded ${statusColors[status] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'}`}>
                                                {status}
                                            </span>
                                            <span className="font-bold text-gray-900 dark:text-gray-100">
                                                {(count as number).toLocaleString()}
                                            </span>
                                        </div>
                                    ))}
                            </div>
                        </div>
                    </div>

                    {/* Orders Table with Pagination */}
                    <div className="card">
                        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-4">
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                                📝 Orders
                            </h3>
                            <div className="text-sm text-gray-500 dark:text-gray-400">
                                Page {pagination.current_page} of {pagination.total_pages}
                                • {pagination.total_orders?.toLocaleString()} total orders
                            </div>
                        </div>

                        {/* Table */}
                        <div className="table-scroll-wrap">
                            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                                <thead className="bg-gray-50 dark:bg-gray-800">
                                    <tr>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Order Code</th>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Channel</th>
                                        <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Status</th>
                                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Selling Price</th>
                                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Net Revenue</th>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Created</th>
                                    </tr>
                                </thead>
                                <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
                                    {ordersLoading ? (
                                        <tr>
                                            <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                                                <span className="inline-block h-6 w-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin mr-2" />
                                                Loading orders...
                                            </td>
                                        </tr>
                                    ) : orders.length === 0 ? (
                                        <tr>
                                            <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                                                No orders found for this period
                                            </td>
                                        </tr>
                                    ) : (
                                        orders.map((order: any, i: number) => (
                                            <tr key={i} className={`hover:bg-gray-50 dark:hover:bg-gray-800 ${!order.include_in_revenue ? 'opacity-60' : ''}`}>
                                                <td className="px-4 py-3 text-sm font-mono text-gray-600 dark:text-gray-400">
                                                    {order.code}
                                                </td>
                                                <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100">
                                                    {order.channel}
                                                </td>
                                                <td className="px-4 py-3 text-sm text-center">
                                                    <span className={`px-2 py-1 text-xs font-medium rounded ${statusColors[order.status] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'}`}>
                                                        {order.status}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3 text-sm text-right text-gray-900 dark:text-gray-100">
                                                    {formatCurrency(order.selling_price)}
                                                </td>
                                                <td className="px-4 py-3 text-sm text-right font-medium">
                                                    <span className={order.include_in_revenue ? 'text-green-600 dark:text-green-400' : 'text-gray-400 line-through'}>
                                                        {formatCurrency(order.net_revenue)}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                                                    {order.created ? new Date(order.created).toLocaleString() : '-'}
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>

                        {/* Pagination Controls */}
                        {pagination.total_pages > 1 && (
                            <div className="mt-6 pt-4 border-t border-gray-200 dark:border-gray-700">
                                <Pagination
                                    currentPage={pagination.current_page}
                                    totalPages={pagination.total_pages}
                                    onPageChange={setCurrentPage}
                                    disabled={ordersFetching}
                                />
                            </div>
                        )}

                        {/* Page revenue */}
                        {ordersData?.page_summary && (
                            <div className="mt-4 text-sm text-gray-500 dark:text-gray-400 text-center">
                                Page revenue: {formatCurrency(ordersData.page_summary.page_revenue)} ({ordersData.page_summary.orders_on_page} orders)
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    );
}
