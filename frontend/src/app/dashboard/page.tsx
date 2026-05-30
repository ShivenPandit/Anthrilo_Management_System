'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { unicommerceApi } from '@/lib/api';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useWebSocket } from '@/lib/hooks/useWebSocket';
import { useEffect, useRef, useState, useMemo, lazy, Suspense, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ShoppingCart, DollarSign, TrendingUp, Package,
  Zap,
  BarChart3, Boxes, Receipt, Store,
  RefreshCw, X, Bell, FileText, Factory,
} from 'lucide-react';
import { KPIStatCard } from '@/components/dashboard/KPIStatCard';
import { ChartCard } from '@/components/dashboard/ChartCard';
import { ComparisonCard } from '@/components/dashboard/ComparisonCard';
import { InsightsPanel } from '@/components/dashboard/InsightsPanel';
import { ChartSkeleton } from '@/components/dashboard/charts/ChartSkeleton';
import { getClosedWindowLast7DaysIst, getDayBeforeYesterdayIst, getYesterdayIst, toIstYmd } from '@/lib/ist-date';

// -- Lazy-loaded Charts (React.lazy avoids next/dynamic _next/undefined chunk bug) --
const RevenueTrendChart = lazy(() => import('@/components/dashboard/charts/RevenueTrendChart'));
const OrdersTrendChart = lazy(() => import('@/components/dashboard/charts/OrdersTrendChart'));
const ChannelBarChart = lazy(() => import('@/components/dashboard/charts/ChannelBarChart'));
const ChannelDonutChart = lazy(() => import('@/components/dashboard/charts/ChannelDonutChart'));

// -- Helpers --
const formatCurrency = (v: number) =>
  v >= 100000 ? `${(v / 100000).toFixed(1)}L` : v >= 1000 ? `${(v / 1000).toFixed(1)}K` : v.toLocaleString('en-IN');

const parseBackendUtcTimestamp = (isoValue?: string | null): Date | null => {
  if (!isoValue) return null;
  const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/.test(isoValue);
  const normalized = hasTimezone ? isoValue : `${isoValue}Z`;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

// ---
export default function DashboardPage() {
  const queryClient = useQueryClient();
  const router = useRouter();

  const prefetchRoute = useCallback((href: string) => {
    try {
      router.prefetch(href);
    } catch {
      // Ignore prefetch errors; links still navigate normally.
    }
  }, [router]);

  // WebSocket
  const { isConnected: wsConnected, lastUpdate: wsLastUpdate, newOrderNotification, dismissNotification, requestRefresh } = useWebSocket();
  const [showToast, setShowToast] = useState(false);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (newOrderNotification) {
      setShowToast(true);
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
      toastTimerRef.current = setTimeout(() => {
        setShowToast(false);
        dismissNotification();
      }, 15000);
    }
    return () => { if (toastTimerRef.current) clearTimeout(toastTimerRef.current); };
  }, [newOrderNotification, dismissNotification]);

  const closedWindow = useMemo(() => getClosedWindowLast7DaysIst(), []);
  // CRITICAL: Use IST (Asia/Kolkata, UTC+5:30) for all KPI queries, not UTC or browser local time.
  // Database stores timestamps as UTC but queries filter by business date in IST.
  // Using wrong timezone causes day-offset bugs: users see yesterday's data labeled as today.
  const todayDate = useMemo(() => toIstYmd(new Date()), []);
  const yesterdayDate = useMemo(() => getYesterdayIst(), []);
  const dayBeforeDate = useMemo(() => getDayBeforeYesterdayIst(), []);

  // A) KPI source: single day only (today)
  const { data: kpiData, isLoading: loadingKpi, isFetching: fetchingKpi } = useQuery({
    queryKey: ['dashboard-kpi-sales', 'today'],
    queryFn: async () =>
      (
        await unicommerceApi.getDbSales({ period: 'today', lightweight: true })
      ).data,
    refetchInterval: 60 * 1000,
    staleTime: 0,
    gcTime: 5 * 60 * 1000,
    refetchOnWindowFocus: true,
  });

  // B) Trend source: closed 7-day window only
  const { data: trendData, isLoading: loadingTrend } = useQuery({
    queryKey: ['dashboard-trend-sales', closedWindow.fromDate, closedWindow.toDate],
    queryFn: async () =>
      (
        await unicommerceApi.getDbSales({
          period: 'custom',
          from_date: closedWindow.fromDate,
          to_date: closedWindow.toDate,
          lightweight: true,
        })
      ).data,
    refetchInterval: 60 * 1000,
    staleTime: 0,
    gcTime: 5 * 60 * 1000,
    refetchOnWindowFocus: true,
  });

  // C) Comparison source: two independent daily calls
  const { data: yesterdayCompareData, isLoading: loadingYesterdayCompare } = useQuery({
    queryKey: ['dashboard-compare-yesterday', yesterdayDate],
    queryFn: async () =>
      (
        await unicommerceApi.getDbSales({
          period: 'custom',
          from_date: yesterdayDate,
          to_date: yesterdayDate,
          lightweight: true,
        })
      ).data,
    refetchInterval: 60 * 1000,
    staleTime: 0,
    gcTime: 5 * 60 * 1000,
    refetchOnWindowFocus: true,
  });

  const { data: dayBeforeCompareData, isLoading: loadingDayBeforeCompare } = useQuery({
    queryKey: ['dashboard-compare-day-before', dayBeforeDate],
    queryFn: async () =>
      (
        await unicommerceApi.getDbSales({
          period: 'custom',
          from_date: dayBeforeDate,
          to_date: dayBeforeDate,
          lightweight: true,
        })
      ).data,
    refetchInterval: 60 * 1000,
    staleTime: 0,
    gcTime: 5 * 60 * 1000,
    refetchOnWindowFocus: true,
  });

  const { data: systemSyncStatus } = useQuery({
    queryKey: ['system-sync-status'],
    queryFn: async () => (await unicommerceApi.getSystemSyncStatus()).data,
    refetchInterval: 60 * 1000,
    staleTime: 0,
    gcTime: 5 * 60 * 1000,
    refetchOnWindowFocus: true,
  });

  const { mutateAsync: syncNow, isPending: syncingNow } = useMutation({
    mutationFn: async () => (await unicommerceApi.runIncrementalSyncNow()).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard-db-sales'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-kpi-sales'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-trend-sales'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-compare-yesterday'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-compare-day-before'] });
      if (wsConnected) requestRefresh();
    },
  });

  // -- Derived Values --
  const todayOrders = kpiData?.summary?.valid_orders || 0;
  const todayRevenue = kpiData?.summary?.total_revenue || 0;
  const todayItems = kpiData?.summary?.total_items || 0;
  const avgOrderValue = kpiData?.summary?.avg_order_value || (todayOrders > 0 ? todayRevenue / todayOrders : 0);
  const yesterdayOrders = yesterdayCompareData?.summary?.valid_orders || 0;
  const yesterdayRevenue = yesterdayCompareData?.summary?.total_revenue || 0;
  const yesterdayItems = yesterdayCompareData?.summary?.total_items || 0;
  const dayBeforeOrders = dayBeforeCompareData?.summary?.valid_orders || 0;
  const dayBeforeRevenue = dayBeforeCompareData?.summary?.total_revenue || 0;
  const dayBeforeItems = dayBeforeCompareData?.summary?.total_items || 0;
  const isLoading = loadingKpi || loadingTrend || loadingYesterdayCompare || loadingDayBeforeCompare;
  const recoveryProgress = systemSyncStatus?.recovery_progress ?? 0;
  const recoveryChunk = systemSyncStatus?.current_chunk;
  const recoveryComplete = systemSyncStatus?.mode === 'recovery' && recoveryProgress >= 100 && !recoveryChunk;

  const dataHealthBadge = useMemo(() => {
    if (recoveryComplete) {
      return { label: 'Recovery complete', dotClass: 'bg-emerald-500' };
    }
    if (systemSyncStatus?.mode === 'recovery') {
      return { label: 'Recovery in progress', dotClass: 'bg-amber-500 animate-pulse' };
    }
    if (Array.isArray(systemSyncStatus?.alerts) && systemSyncStatus.alerts.length > 0) {
      return { label: 'Sync lag', dotClass: 'bg-rose-500 animate-pulse' };
    }
    if (!kpiData) {
      return { label: 'Healthy', dotClass: 'bg-emerald-500' };
    }

    if (kpiData.fallback_used) {
      return { label: 'Using fallback', dotClass: 'bg-amber-500 animate-pulse' };
    }

    const lastSyncedAt = kpiData.last_synced_at;
    if (lastSyncedAt) {
      const parsed = parseBackendUtcTimestamp(lastSyncedAt);
      if (parsed) {
        const lagMinutes = (Date.now() - parsed.getTime()) / 60000;
        if (lagMinutes > 12 * 60) {
          return { label: 'Sync lag', dotClass: 'bg-rose-500 animate-pulse' };
        }
      }
    }

    return { label: 'Healthy', dotClass: 'bg-emerald-500' };
  }, [kpiData, systemSyncStatus, recoveryComplete]);

  const recoveryHint = useMemo(() => {
    if (!systemSyncStatus) return null;

    if (systemSyncStatus.mode === 'recovery') {
      const gapDays = systemSyncStatus.sync_gap_days;
      const progress = recoveryProgress;
      const chunk = recoveryChunk;
      const gapLabel = typeof gapDays === 'number' ? `${gapDays.toFixed(1)} days` : 'missing days';
      if (recoveryComplete) {
        return `Recovery complete: synced ${gapLabel} (${progress}%)`;
      }
      return `Data recovering: syncing ${gapLabel} (${progress}%)${chunk ? ` · ${chunk}` : ''}`;
    }

    const lastUpdated = systemSyncStatus.last_successful_sync;
    if (lastUpdated) {
      const parsed = parseBackendUtcTimestamp(lastUpdated);
      if (parsed) {
        const minutes = Math.max(0, Math.round((Date.now() - parsed.getTime()) / 60000));
        const hours = Math.floor(minutes / 60);
        const label = hours > 0 ? `${hours}h ${minutes % 60}m ago` : `${minutes}m ago`;
        return `Last updated ${label}`;
      }
    }
    return null;
  }, [systemSyncStatus, recoveryComplete, recoveryProgress, recoveryChunk]);

  // Growth calculations
  const orderGrowth = yesterdayOrders > 0 ? ((todayOrders - yesterdayOrders) / yesterdayOrders) * 100 : 0;
  const revenueGrowth = yesterdayRevenue > 0 ? ((todayRevenue - yesterdayRevenue) / yesterdayRevenue) * 100 : 0;

  // Daily trend data — use pre-aggregated daily_breakdown from backend summary
  // Defensive: if backend returns per-order entries instead of daily aggregates,
  // re-aggregate client-side (should never happen with fixed backend)
  const dailyTrend = useMemo(() => {
    const breakdown = trendData?.summary?.daily_breakdown;
    if (!breakdown || !Array.isArray(breakdown) || breakdown.length === 0) return [];
    return breakdown
      .filter((d: any) => (d.date || '') < todayDate)
      .sort((a: any, b: any) => (a.date || '').localeCompare(b.date || ''))
      .map((d: any) => ({
        date: (d.date || '').slice(5),              // "2026-02-14" → "02-14"
        fullDate: d.date || '',                      // keep full date for tooltip
        orders: d.orders || 0,
        revenue: Math.round(d.revenue || 0),
        items: d.items || 0,
      }));
  }, [todayDate, trendData]);

  const channelRows = useMemo(() => {
    const breakdown = trendData?.summary?.channel_breakdown || {};
    return Object.entries(breakdown).map(([channel, values]: [string, any]) => ({
      channel,
      revenue: Number(values?.revenue || 0),
      orders: Number(values?.orders || 0),
      items: Number(values?.items || 0),
    }));
  }, [trendData]);

  // Channel chart data (memoized)
  const channelChartData = useMemo(() => {
    if (!channelRows.length) return [];
    return channelRows
      .sort((a: any, b: any) => (b.revenue || 0) - (a.revenue || 0))
      .slice(0, 7)
      .map((ch: any) => ({
        name: ch.channel?.replace(/_/g, ' ')?.replace(/UnicommerceChannel/i, '')?.trim()?.slice(0, 14) || 'Other',
        revenue: Math.round(ch.revenue || 0),
        orders: ch.orders || 0,
      }));
  }, [channelRows]);

  // Channel distribution for donut (memoized)
  const channelDonutData = useMemo(() => {
    if (!channelRows.length) return [];
    return channelRows
      .sort((a: any, b: any) => (b.orders || 0) - (a.orders || 0))
      .slice(0, 6)
      .map((ch: any) => ({
        name: ch.channel?.replace(/_/g, ' ')?.slice(0, 12) || 'Other',
        value: ch.orders || 0,
      }));
  }, [channelRows]);

  // Top channel for insights
  const topChannel = useMemo(() => {
    if (!channelChartData.length) return undefined;
    const totalRevenue = channelChartData.reduce((sum: number, ch: any) => sum + ch.revenue, 0);
    const top = channelChartData[0];
    return totalRevenue > 0
      ? { name: top.name, revenue: top.revenue, percentage: (top.revenue / totalRevenue) * 100 }
      : undefined;
  }, [channelChartData]);

  // Comparison values come from dedicated daily API calls only.
  const ydayRevenue = yesterdayRevenue;
  const ydayOrders = yesterdayOrders;
  const ydayItems = yesterdayItems;
  const dbyRevenue = dayBeforeRevenue;
  const dbyOrders = dayBeforeOrders;
  const dbyItems = dayBeforeItems;

  // Sparkline data from daily breakdown
  const revenueSparkline = useMemo(() => dailyTrend.map((d: any) => d.revenue), [dailyTrend]);
  const ordersSparkline = useMemo(() => dailyTrend.map((d: any) => d.orders), [dailyTrend]);
  const itemsSparkline = useMemo(() => dailyTrend.map((d: any) => d.items), [dailyTrend]);

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['dashboard-kpi-sales'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard-trend-sales'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard-compare-yesterday'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard-compare-day-before'] });
    if (wsConnected) requestRefresh();
  };

  const handleSyncNow = async () => {
    try {
      await syncNow();
      handleRefresh();
    } catch (error) {
      console.error('Manual sync failed', error);
    }
  };

  const quickLinks = [
    { title: 'Master Data', desc: 'Product catalog & SKUs', href: '/dashboard/garments/master', icon: Package, color: 'from-blue-500 to-indigo-500' },
    { title: 'Planning Report', desc: 'Garment production planning', href: '/dashboard/garments/planning-report', icon: FileText, color: 'from-orange-500 to-amber-500' },
    { title: 'Production Planning Raw Data', desc: 'Stitching, cutting and finishing tracker', href: '/dashboard/garments/production-planning-report', icon: Factory, color: 'from-sky-500 to-cyan-500' },
    { title: 'Production Planning & Status Report', desc: 'Date-wise status and balance report', href: '/dashboard/garments/production-planning-status-report', icon: FileText, color: 'from-indigo-500 to-sky-500' },
    { title: 'Sales', desc: 'Transactions & returns', href: '/dashboard/sales/transactions', icon: Receipt, color: 'from-amber-500 to-orange-500' },
    { title: 'Reports', desc: 'Insights & analytics', href: '/dashboard/reports/reports-index', icon: BarChart3, color: 'from-violet-500 to-purple-500' },
    { title: 'Best SKUs', desc: 'Top performing products', href: '/dashboard/garments/best-skus', icon: Zap, color: 'from-rose-500 to-pink-500' },
    { title: 'Channels', desc: 'Panel settlement', href: '/dashboard/reports/panels/settlement', icon: Store, color: 'from-cyan-500 to-blue-500' },
  ];

  return (
    <div className="page-section-gap">
      {/* Toast Notification */}
      <AnimatePresence>
        {showToast && newOrderNotification && (
          <motion.div
            initial={{ opacity: 0, x: 100, y: -20 }}
            animate={{ opacity: 1, x: 0, y: 0 }}
            exit={{ opacity: 0, x: 100 }}
            className="fixed top-4 right-4 z-50 max-w-sm w-full"
          >
            <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
              <div className="bg-gradient-to-r from-emerald-500 to-green-500 px-4 py-2.5 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Bell className="w-4 h-4 text-white" />
                  <span className="text-white font-semibold text-sm">
                    {newOrderNotification.count} New Order{newOrderNotification.count > 1 ? 's' : ''}
                  </span>
                </div>
                <button
                  aria-label="Dismiss notification"
                  title="Dismiss notification"
                  onClick={() => { setShowToast(false); dismissNotification(); }}
                  className="text-white/70 hover:text-white transition-colors"><X className="w-4 h-4" /></button>
              </div>
              <div className="p-4 space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500 dark:text-slate-400">Total Orders</span>
                  <span className="font-bold text-slate-900 dark:text-white">{newOrderNotification.totalOrders}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500 dark:text-slate-400">Revenue</span>
                  <span className="font-bold text-emerald-600 dark:text-emerald-400">
                    {'\u20B9'}{newOrderNotification.totalRevenue.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                  </span>
                </div>
                {newOrderNotification.orders?.slice(0, 3).map((o: any, i: number) => (
                  <div key={i} className="flex justify-between text-xs pt-1 border-t border-slate-100 dark:border-slate-800">
                    <span className="font-mono text-slate-400 truncate max-w-[180px]">
                      {o.saleOrderCode || o.channel || 'Order'}
                    </span>
                    <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                      {'\u20B9'}{(o.sellingPrice || o.revenue || 0).toLocaleString('en-IN')}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="responsive-title text-slate-900 dark:text-white">Dashboard</h1>
          <p className="responsive-subtitle mt-0.5">
            Your business at a glance
          </p>
        </div>
        <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 w-full sm:w-auto">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800">
              <span className={`w-1.5 h-1.5 rounded-full ${dataHealthBadge.dotClass}`} />
              <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                {dataHealthBadge.label}
              </span>
            </div>
            {recoveryHint ? (
              <div className="text-[11px] text-slate-500 dark:text-slate-400">
                {recoveryHint}
              </div>
            ) : null}

          </div>
          <button
            onClick={handleSyncNow}
            className="btn btn-secondary w-auto self-start sm:self-auto !px-3.5 !py-2 !text-sm"
            disabled={syncingNow}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${syncingNow ? 'animate-spin' : ''}`} />
            {syncingNow ? 'Syncing DB...' : 'Sync Now'}
          </button>
          <button
            onClick={handleRefresh}
            className="btn btn-secondary w-auto self-start sm:self-auto !px-3.5 !py-2 !text-sm"
            disabled={fetchingKpi || syncingNow}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${fetchingKpi ? 'animate-spin' : ''}`} />
            {fetchingKpi ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* SECTION 1: Performance Snapshot */}
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3">
          Performance Snapshot
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 md:gap-4 2xl:gap-5">
          <KPIStatCard
            title="Revenue"
            value={todayRevenue}
            prefix={'\u20B9'}
            icon={DollarSign}
            color="green"
            change={revenueGrowth}
            changeLabel="vs yesterday"
            sparklineData={revenueSparkline}
            loading={isLoading}
            formatter={(v) => formatCurrency(v)}
            delay={0}
            tooltip="Total revenue from all sale orders created today across every channel."
          />
          <KPIStatCard
            title="Orders"
            value={todayOrders}
            icon={ShoppingCart}
            color="blue"
            change={orderGrowth}
            changeLabel="vs yesterday"
            sparklineData={ordersSparkline}
            loading={isLoading}
            delay={80}
            tooltip="Number of sale orders placed today across all marketplace and D2C channels."
          />
          <KPIStatCard
            title="Avg Order Value"
            value={avgOrderValue}
            prefix={'\u20B9'}
            icon={TrendingUp}
            color="amber"
            loading={isLoading}
            formatter={(v) => v.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
            delay={160}
            tooltip="Average revenue generated per order. Higher AOV means customers spend more per purchase."
          />
          <KPIStatCard
            title="Items Sold"
            value={todayItems}
            icon={Package}
            color="purple"
            sparklineData={itemsSparkline}
            loading={isLoading}
            delay={240}
            tooltip="Total individual items (units) sold across all orders today."
          />
        </div>
      </section>

      {/* SECTION 2: Trend Over Time */}
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3">
          Trend Over Time
        </h2>
        {/* Revenue — primary metric, full width */}
        <ChartCard title="Revenue Trend" subtitle="Daily revenue — last 7 days" downloadable={false}>
          <Suspense fallback={<ChartSkeleton />}><RevenueTrendChart data={dailyTrend} /></Suspense>
        </ChartCard>
        {/* Orders & Items — secondary, below */}
        <div className="mt-4">
          <ChartCard title="Orders & Items" subtitle="Daily volume — last 7 days" downloadable={false}>
            <Suspense fallback={<ChartSkeleton />}><OrdersTrendChart data={dailyTrend} /></Suspense>
          </ChartCard>
        </div>
      </section>

      {/* SECTION 3: Channel Contribution */}
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3">
          Channel Contribution
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 md:gap-4 2xl:gap-5">
          <ChartCard title="Revenue by Channel" subtitle="Top channels — last 7 days" downloadable={false}>
            <Suspense fallback={<ChartSkeleton />}><ChannelBarChart data={channelChartData} /></Suspense>
          </ChartCard>
          <ChartCard title="Order Distribution" subtitle="Orders split by channel" downloadable={false}>
            <Suspense fallback={<ChartSkeleton />}><ChannelDonutChart data={channelDonutData} /></Suspense>
          </ChartCard>
        </div>
      </section>

      {/* SECTION 4: Comparison & Insights */}
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3">
          Comparison & Insights
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 md:gap-4 2xl:gap-5">
          <ComparisonCard
            title="Yesterday vs Day Before"
            leftLabel="Yesterday"
            rightLabel="Day Before"
            loading={loadingTrend && !trendData}
            metrics={[
              {
                label: 'Revenue',
                today: ydayRevenue,
                yesterday: dbyRevenue,
                formatter: (v: number) => `₹${formatCurrency(v)}`,
              },
              {
                label: 'Orders',
                today: ydayOrders,
                yesterday: dbyOrders,
              },
              {
                label: 'Items',
                today: ydayItems,
                yesterday: dbyItems,
              },
            ]}
          />

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: 'easeOut', delay: 0.1 }}
            className="rounded-2xl border border-slate-200/60 dark:border-slate-800
              bg-white dark:bg-slate-900 shadow-[var(--shadow-soft)] p-4 sm:p-5 lg:p-6 2xl:p-7"
          >
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-4">
              Insights
            </h3>
            <InsightsPanel
              todayRevenue={ydayRevenue}
              yesterdayRevenue={dbyRevenue}
              todayOrders={ydayOrders}
              yesterdayOrders={dbyOrders}
              todayItems={ydayItems}
              yesterdayItems={dbyItems}
              topChannel={topChannel}
              totalChannels={channelRows.length}
              loading={loadingTrend && !trendData}
              comparisonLabel="day before yesterday"
            />
          </motion.div>
        </div>
      </section>

      {/* Quick Navigation */}
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3">
          Quick Access
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-6 gap-3 md:gap-4 2xl:gap-5">
          {quickLinks.map((link, i) => (
            <Link
              key={link.href}
              href={link.href}
              prefetch
              onMouseEnter={() => prefetchRoute(link.href)}
              onFocus={() => prefetchRoute(link.href)}
            >
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: i * 0.04 }}
                className="card-interactive p-4 group text-center"
              >
                <div className={`w-10 h-10 mx-auto rounded-xl bg-gradient-to-br ${link.color} flex items-center justify-center mb-3
                  group-hover:scale-110 transition-transform duration-200`}>
                  <link.icon className="w-5 h-5 text-white" strokeWidth={1.8} />
                </div>
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">
                  {link.title}
                </p>
                <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-0.5">{link.desc}</p>
              </motion.div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
