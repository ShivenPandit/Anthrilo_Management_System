/**
 * Dashboard Panel Components
 * ==========================
 * Reusable panel components for building modern analytics dashboards
 * 
 * Each component clearly documents its data source (Phase 1 or Phase 2)
 */

'use client';

import React from 'react';

// ============================================================================
// LOADING & ERROR STATES
// ============================================================================

export function LoadingPanel() {
    return (
        <div className="card">
            <div className="flex items-center gap-4">
                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600"></div>
                <div className="flex-1">
                    <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/4 mb-2"></div>
                    <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-2/3"></div>
                </div>
            </div>
            <div className="mt-3 text-xs text-gray-500 dark:text-gray-400 space-y-1">
                <p className="flex items-center gap-2">
                    <span className="inline-block w-2 h-2 bg-blue-500 rounded-full animate-pulse"></span>
                    <span>Fetching data from Unicommerce API...</span>
                </p>
                <p className="ml-4">⏱️ First load: 30-120 seconds (depends on data volume)</p>
                <p className="ml-4">⚡ Cached loads: Instant (&lt; 2 seconds, 15 min cache)</p>
            </div>
        </div>
    );
}

export function ErrorPanel({ message }: { message: string }) {
    const isTimeout = message.includes('timeout') || message.includes('timed out') || message.includes('exceeded');

    return (
        <div className="card border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20">
            <div className="flex items-start gap-3">
                <span className="text-3xl">⚠️</span>
                <div className="flex-1">
                    <p className="font-semibold text-red-600 dark:text-red-400 mb-1">Error Loading Data</p>
                    <p className="text-sm text-red-600 dark:text-red-400 mb-3">{message}</p>

                    {isTimeout && (
                        <div className="mt-3 p-3 bg-blue-50 dark:bg-blue-900/30 rounded-lg border border-blue-200 dark:border-blue-800">
                            <p className="text-sm font-semibold text-blue-900 dark:text-blue-100 mb-2">💡 Why this happened:</p>
                            <p className="text-xs text-blue-800 dark:text-blue-200 mb-2">
                                You&apos;re fetching ALL orders (no limits) for complete business accuracy.
                                Large datasets (5000+ orders) may take 3-5 minutes on first load.
                            </p>
                            <p className="text-sm font-semibold text-blue-900 dark:text-blue-100 mb-2">✅ Try these solutions:</p>
                            <ul className="text-xs text-blue-800 dark:text-blue-200 space-y-1 list-disc list-inside">
                                <li>Wait 2-3 minutes and refresh - data is now cached and will load instantly</li>
                                <li>Try a shorter period first (Today/Yesterday) to verify system is working</li>
                                <li>Check your internet connection and Unicommerce API status</li>
                                <li>The wait is worth it - you get 100% accurate data for business decisions!</li>
                            </ul>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

// ============================================================================
// KPI CARD - For Overview Metrics
// ============================================================================

interface KPICardProps {
    title: string;
    value: string | number;
    subtitle?: string;
    icon?: string;
    color?: 'blue' | 'green' | 'purple' | 'orange' | 'red' | 'yellow';
    trend?: {
        value: number;
        isPositive: boolean;
    };
    loading?: boolean;
    /**
     * Documentation field: Indicates data source
     * - 'phase1' = saleOrder/search (order codes, status, counts)
     * - 'phase2' = saleorder/get (revenue, sellingPrice)
     */
    dataSource?: 'phase1' | 'phase2';
}

const colorMap = {
    blue: 'from-blue-500 to-blue-600',
    green: 'from-green-500 to-green-600',
    purple: 'from-purple-500 to-purple-600',
    orange: 'from-orange-500 to-orange-600',
    red: 'from-red-500 to-red-600',
    yellow: 'from-yellow-500 to-yellow-600',
};

export function KPICard({
    title,
    value,
    subtitle,
    icon,
    color = 'blue',
    trend,
    loading = false,
    dataSource,
}: KPICardProps) {
    if (loading) {
        return <LoadingPanel />;
    }

    return (
        <div className="card hover:shadow-xl transition-all duration-300 group">
            <div className="flex items-start justify-between">
                <div className="flex-1">
                    <p className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2">
                        {title}
                    </p>
                    <p className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
                        {value}
                    </p>
                    {subtitle && (
                        <p className="text-xs text-gray-500 dark:text-gray-400">{subtitle}</p>
                    )}
                    {trend && (
                        <div className={`flex items-center gap-1 mt-2 text-sm font-medium ${trend.isPositive
                            ? 'text-green-600 dark:text-green-400'
                            : 'text-red-600 dark:text-red-400'
                            }`}>
                            <span>{trend.isPositive ? '↑' : '↓'}</span>
                            <span>{Math.abs(trend.value)}%</span>
                        </div>
                    )}
                </div>
                {icon && (
                    <div className={`
            p-3 rounded-lg text-white text-2xl 
            bg-gradient-to-br ${colorMap[color]}
            shadow-lg group-hover:scale-110 transition-transform duration-300
          `}>
                        {icon}
                    </div>
                )}
            </div>
            {dataSource && (
                <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                        Source: {dataSource === 'phase1' ? 'Order Search API' : 'Order Details API (Revenue)'}
                    </p>
                </div>
            )}
        </div>
    );
}

// ============================================================================
// REVENUE PANEL - Specifically for Phase 2 Revenue Data
// ============================================================================

interface RevenuePanelProps {
    title: string;
    revenue: number;
    orders: number;
    averageOrderValue: number;
    currency?: string;
    loading?: boolean;
    trend?: {
        value: number;
        isPositive: boolean;
    };
}

export function RevenuePanel({
    title,
    revenue,
    orders,
    averageOrderValue,
    currency = '₹',
    loading = false,
    trend,
}: RevenuePanelProps) {
    if (loading) {
        return <LoadingPanel />;
    }

    return (
        <div className="card border-l-4 border-green-500 dark:border-green-400 hover:shadow-2xl transition-all duration-300">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h3>
                <div className="text-2xl">💰</div>
            </div>

            <div className="space-y-3">
                <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400">Total Revenue</p>
                    <p className="text-3xl font-bold text-green-600 dark:text-green-400">
                        {currency}{revenue.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                    </p>
                    {trend && (
                        <p className={`text-sm mt-1 ${trend.isPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                            }`}>
                            {trend.isPositive ? '↑' : '↓'} {Math.abs(trend.value)}% from previous period
                        </p>
                    )}
                </div>

                <div className="grid grid-cols-2 gap-4 pt-3 border-t border-gray-200 dark:border-gray-700">
                    <div>
                        <p className="text-xs text-gray-600 dark:text-gray-400">Orders</p>
                        <p className="text-xl font-semibold text-gray-900 dark:text-white">{orders}</p>
                    </div>
                    <div>
                        <p className="text-xs text-gray-600 dark:text-gray-400">Avg Order Value</p>
                        <p className="text-xl font-semibold text-gray-900 dark:text-white">
                            {currency}{averageOrderValue.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                        </p>
                    </div>
                </div>
            </div>

            {/* Data Source Documentation */}
            <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                <div className="flex items-start gap-2">
                    <span className="text-xs text-blue-600 dark:text-blue-400 font-mono bg-blue-50 dark:bg-blue-900/30 px-2 py-1 rounded">
                        PHASE 2 DATA
                    </span>
                    <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
                        Revenue calculated from <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">item.sellingPrice</code> using saleorder/get API
                    </p>
                </div>
            </div>
        </div>
    );
}

// ============================================================================
// CHANNEL BREAKDOWN PANEL
// ============================================================================

interface ChannelBreakdownProps {
    channels: Record<string, { orders: number; revenue: number }>;
    currency?: string;
    loading?: boolean;
}

export function ChannelBreakdownPanel({
    channels,
    currency = '₹',
    loading = false,
}: ChannelBreakdownProps) {
    if (loading) {
        return <LoadingPanel />;
    }

    const channelColors = {
        default: 'bg-blue-500',
        amazon: 'bg-orange-500',
        flipkart: 'bg-yellow-500',
        myntra: 'bg-pink-500',
        ajio: 'bg-purple-500',
        meesho: 'bg-red-500'
    };

    const totalRevenue = Object.values(channels).reduce((sum, ch) => sum + ch.revenue, 0);
    const sortedChannels = Object.entries(channels).sort((a, b) => b[1].revenue - a[1].revenue);

    return (
        <div className="card hover:shadow-xl transition-all duration-300">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Channel Breakdown</h3>
                <span className="text-2xl">📊</span>
            </div>

            <div className="space-y-4">
                {sortedChannels.map(([channel, data]) => {
                    const percentage = totalRevenue > 0 ? (data.revenue / totalRevenue) * 100 : 0;
                    const colorKey = channel.toLowerCase() as keyof typeof channelColors;
                    const color = channelColors[colorKey] || channelColors.default;

                    return (
                        <div key={channel} className="space-y-2">
                            <div className="flex items-center justify-between text-sm">
                                <span className="font-medium text-gray-700 dark:text-gray-300">
                                    {channel}
                                </span>
                                <span className="text-gray-600 dark:text-gray-400">
                                    {percentage.toFixed(1)}%
                                </span>
                            </div>
                            <div className="flex items-center gap-3">
                                <div className="flex-1 bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
                                    <div
                                        className={`h-full ${color} transition-all duration-500`}
                                        style={{ width: `${percentage}%` }}
                                    />
                                </div>
                            </div>
                            <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400">
                                <span>{data.orders} orders</span>
                                <span className="font-semibold text-gray-900 dark:text-white">
                                    {currency}{data.revenue.toLocaleString('en-IN')}
                                </span>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Data Source Documentation */}
            <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                <p className="text-xs text-gray-500 dark:text-gray-400">
                    <span className="font-mono text-blue-600 dark:text-blue-400">Phase 2:</span> Revenue from sellingPrice
                </p>
            </div>
        </div>
    );
}

// ============================================================================
// STATUS BREAKDOWN PANEL
// ============================================================================

interface StatusBreakdownProps {
    statuses: Record<string, number>;
    loading?: boolean;
}

export function StatusBreakdownPanel({ statuses, loading = false }: StatusBreakdownProps) {
    if (loading) {
        return <LoadingPanel />;
    }

    const statusConfig: Record<string, { color: string; icon: string; label: string }> = {
        CREATED: { color: 'bg-blue-500', icon: '🆕', label: 'Created' },
        PENDING: { color: 'bg-yellow-500', icon: '⏳', label: 'Pending' },
        APPROVED: { color: 'bg-green-500', icon: '✅', label: 'Approved' },
        PROCESSING: { color: 'bg-purple-500', icon: '⚙️', label: 'Processing' },
        SHIPPED: { color: 'bg-indigo-500', icon: '📦', label: 'Shipped' },
        DELIVERED: { color: 'bg-green-600', icon: '✓', label: 'Delivered' },
        CANCELLED: { color: 'bg-red-500', icon: '❌', label: 'Cancelled' },
        RETURNED: { color: 'bg-orange-500', icon: '↩️', label: 'Returned' },
    };

    const totalOrders = Object.values(statuses).reduce((sum, count) => sum + count, 0);
    const sortedStatuses = Object.entries(statuses).sort((a, b) => b[1] - a[1]);

    return (
        <div className="card hover:shadow-xl transition-all duration-300">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Order Status</h3>
                <span className="text-2xl">📋</span>
            </div>

            <div className="grid grid-cols-2 gap-3">
                {sortedStatuses.map(([status, count]) => {
                    const config = statusConfig[status] || {
                        color: 'bg-gray-500',
                        icon: '•',
                        label: status
                    };
                    const percentage = totalOrders > 0 ? (count / totalOrders) * 100 : 0;

                    return (
                        <div
                            key={status}
                            className="p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 transition-colors"
                        >
                            <div className="flex items-center gap-2 mb-1">
                                <span className="text-lg">{config.icon}</span>
                                <span className="text-xs font-medium text-gray-600 dark:text-gray-400">
                                    {config.label}
                                </span>
                            </div>
                            <div className="flex items-baseline gap-2">
                                <span className="text-2xl font-bold text-gray-900 dark:text-white">{count}</span>
                                <span className="text-xs text-gray-500 dark:text-gray-400">
                                    ({percentage.toFixed(0)}%)
                                </span>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Data Source Documentation */}
            <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                <p className="text-xs text-gray-500 dark:text-gray-400">
                    <span className="font-mono text-blue-600 dark:text-blue-400">Phase 1:</span> Order counts from search API
                </p>
            </div>
        </div>
    );
}

// ============================================================================
// FETCH INFO PANEL - Shows API Performance
// ============================================================================

interface FetchInfoPanelProps {
    fetchInfo: {
        total_available: number;
        fetched_count: number;
        failed_codes: number;
        phase1_time_seconds: number;
        phase2_time_seconds: number;
        total_time_seconds: number;
        retry_recovered?: number;
        phase1_dedup?: number;
        phase2_dedup?: number;
        reconciliation_passed?: boolean;
    };
    loading?: boolean;
}

export function FetchInfoPanel({ fetchInfo, loading = false }: FetchInfoPanelProps) {
    if (loading) {
        return <LoadingPanel />;
    }

    // Determine if data was likely cached (very fast response)
    const wasCached = fetchInfo.total_time_seconds < 2;
    const performanceRating = fetchInfo.total_time_seconds < 5 ? 'Excellent' :
        fetchInfo.total_time_seconds < 15 ? 'Good' :
            fetchInfo.total_time_seconds < 30 ? 'Moderate' : 'Slow';

    const failureRate = fetchInfo.total_available > 0
        ? ((fetchInfo.failed_codes / fetchInfo.total_available) * 100).toFixed(1)
        : '0';

    return (
        <div className="card bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border-blue-200 dark:border-blue-800">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <span className="text-2xl">⚡</span>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white">API Performance & Data Quality</h3>
                </div>
                <div className="flex items-center gap-2">
                    {wasCached && (
                        <div className="flex items-center gap-1 px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded-md text-xs font-semibold">
                            <span>💾</span>
                            <span>Cached</span>
                        </div>
                    )}
                    {fetchInfo.reconciliation_passed !== undefined && (
                        <div className={`flex items-center gap-1 px-2 py-1 rounded-md text-xs font-semibold ${fetchInfo.reconciliation_passed
                                ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                                : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                            }`}>
                            <span>{fetchInfo.reconciliation_passed ? '✓' : '✗'}</span>
                            <span>Reconciliation</span>
                        </div>
                    )}
                </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div>
                    <p className="text-xs text-gray-600 dark:text-gray-400">Total Available</p>
                    <p className="text-xl font-bold text-gray-900 dark:text-white">{fetchInfo.total_available}</p>
                </div>
                <div>
                    <p className="text-xs text-gray-600 dark:text-gray-400">Fetched</p>
                    <p className="text-xl font-bold text-green-600 dark:text-green-400">{fetchInfo.fetched_count}</p>
                </div>
                <div>
                    <p className="text-xs text-gray-600 dark:text-gray-400">Failed</p>
                    <p className={`text-xl font-bold ${fetchInfo.failed_codes > 0 ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'}`}>
                        {fetchInfo.failed_codes}
                        {fetchInfo.failed_codes > 0 && (
                            <span className="text-xs ml-1">({failureRate}%)</span>
                        )}
                    </p>
                </div>
                <div>
                    <p className="text-xs text-gray-600 dark:text-gray-400">Retry Recovered</p>
                    <p className="text-xl font-bold text-blue-600 dark:text-blue-400">
                        {fetchInfo.retry_recovered ?? 0}
                    </p>
                </div>
                <div>
                    <p className="text-xs text-gray-600 dark:text-gray-400">Rating</p>
                    <p className="text-xl font-bold text-blue-600 dark:text-blue-400">{performanceRating}</p>
                </div>
            </div>

            <div className="mt-4 pt-4 border-t border-blue-200 dark:border-blue-800">
                <div className="grid grid-cols-3 md:grid-cols-5 gap-4 text-xs">
                    <div>
                        <p className="text-gray-600 dark:text-gray-400">Phase 1</p>
                        <p className="font-semibold text-gray-900 dark:text-white">{fetchInfo.phase1_time_seconds.toFixed(2)}s</p>
                    </div>
                    <div>
                        <p className="text-gray-600 dark:text-gray-400">Phase 2</p>
                        <p className="font-semibold text-gray-900 dark:text-white">{fetchInfo.phase2_time_seconds.toFixed(2)}s</p>
                    </div>
                    <div>
                        <p className="text-gray-600 dark:text-gray-400">Total</p>
                        <p className="font-semibold text-gray-900 dark:text-white">{fetchInfo.total_time_seconds.toFixed(2)}s</p>
                    </div>
                    {(fetchInfo.phase1_dedup ?? 0) > 0 && (
                        <div>
                            <p className="text-gray-600 dark:text-gray-400">P1 Dedup</p>
                            <p className="font-semibold text-orange-600 dark:text-orange-400">{fetchInfo.phase1_dedup}</p>
                        </div>
                    )}
                    {(fetchInfo.phase2_dedup ?? 0) > 0 && (
                        <div>
                            <p className="text-gray-600 dark:text-gray-400">P2 Dedup</p>
                            <p className="font-semibold text-orange-600 dark:text-orange-400">{fetchInfo.phase2_dedup}</p>
                        </div>
                    )}
                </div>
            </div>

            <div className="mt-4 pt-4 border-t border-blue-200 dark:border-blue-800">
                <p className="text-xs text-gray-600 dark:text-gray-400">
                    <span className="font-semibold">Two-Phase API v2:</span> Date-chunked identifier collection + batched detail resolution with retry & deduplication
                    {wasCached && <span className="text-green-600 dark:text-green-400"> • Data served from 15-min cache</span>}
                </p>
            </div>
        </div>
    );
}
