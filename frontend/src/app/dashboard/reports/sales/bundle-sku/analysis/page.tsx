'use client';

import { useState, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ucSales } from '@/features/sales/api';
import { DataTable, Column } from '@/components/ui/DataTable';
import { PageHeader, ProgressLoader, StatCard } from '@/components/ui/Common';
import { ChartCard } from '@/components/dashboard';
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend,
} from 'recharts';
import {
  ReportDateMode,
  getTodayYmd,
  getYesterdayYmd,
  resolveReportDateRange,
} from '@/lib/report-date-range';

/* Constants */
const COLORS = ['#6366f1', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#f43f5e', '#ec4899', '#14b8a6', '#a855f7', '#ef4444'];
const PAGE_SIZE = 15;

/* Helpers */
function fmtINR(v: number) {
  return `₹${v.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
}
function fmtNum(v: number) {
  return v.toLocaleString('en-IN');
}
function fmtAxisINR(v: number): string {
  if (v === 0) return '0';
  if (v >= 100_000) return `${(v / 100_000).toFixed(v % 100_000 === 0 ? 0 : 1)}L`;
  if (v >= 1000) return `${(v / 1000).toFixed(0)}K`;
  return String(v);
}
function shortChannel(name: string) {
  const m: Record<string, string> = {
    MYNTRA: 'MYN', FLIPKART: 'FK', AMAZON_IN_API: 'AMZ', AMAZON_FLEX: 'AMZ-F',
    SHOPIFY: 'SHOP', AJIO_OMNI: 'AJIO', MEESHO_26: 'MEE', NYKAA_FASHION_NEW: 'NYK',
    FIRSTCRY_NEW: 'FC', TATACLIQ: 'TATA', SNAPDEAL_NEW: 'SD',
  };
  return m[name] ?? name.replace(/_/g, ' ').slice(0, 6);
}
function fmtDate(d: string) {
  try {
    const dt = new Date(d + 'T00:00:00');
    return dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
  } catch { return d; }
}

/* Custom Tooltips */
function RevTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  return (
    <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-lg px-4 py-3 text-sm pointer-events-none">
      <p className="text-[11px] font-medium text-slate-400 dark:text-slate-500 mb-1">{d?.date || label}</p>
      <p className="text-lg font-bold text-slate-900 dark:text-white">{fmtINR(payload[0]?.value || 0)}</p>
      {d?.units != null && <p className="text-xs text-slate-500">{d.units} bundles · {d.orders} orders</p>}
    </div>
  );
}
function BarTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  return (
    <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-lg px-3.5 py-2.5 text-sm pointer-events-none">
      <p className="text-[11px] font-medium text-slate-400 dark:text-slate-500 mb-1">{d?.name}</p>
      <p className="font-semibold text-slate-900 dark:text-white">{fmtINR(d?.revenue || 0)}</p>
      <p className="text-xs text-slate-500">{fmtNum(d?.units || 0)} units · {fmtNum(d?.orders || 0)} orders</p>
    </div>
  );
}
function PieTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  return (
    <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-lg px-3.5 py-2.5 text-sm pointer-events-none">
      <p className="text-[11px] font-medium text-slate-400 dark:text-slate-500 mb-1">{d?.name}</p>
      <p className="font-semibold text-slate-900 dark:text-white">{fmtINR(d?.value || 0)}</p>
      <p className="text-xs text-slate-500">{fmtNum(d?.units || 0)} units · {d?.bundle_count} bundle types</p>
    </div>
  );
}

/*  */

export default function BundleSalesAnalysisPage() {
  const [dateMode, setDateMode] = useState<ReportDateMode>('monthly');
  const [anchorDate, setAnchorDate] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() - 1);
    return date.toISOString().split('T')[0];
  });
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);

  const effectiveRange = useMemo(() => resolveReportDateRange({
    mode: dateMode,
    anchorDate,
    fromDate,
    toDate,
  }), [dateMode, anchorDate, fromDate, toDate]);

  const apiPeriod = useMemo(() => {
    const today = getTodayYmd();
    const yesterday = getYesterdayYmd();

    if (dateMode === 'daily' && effectiveRange.fromDate === today) return 'today';
    if (dateMode === 'daily' && effectiveRange.fromDate === yesterday) return 'yesterday';
    return 'custom';
  }, [dateMode, effectiveRange.fromDate]);

  const queryParams = useMemo(() => {
    const p: any = { period: apiPeriod };
    if (apiPeriod === 'custom') {
      p.from_date = effectiveRange.fromDate;
      p.to_date = effectiveRange.toDate;
    }
    return p;
  }, [apiPeriod, effectiveRange.fromDate, effectiveRange.toDate]);

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ['bundle-sales-analysis', queryParams],
    queryFn: async () => {
      const res = await ucSales.getBundleSalesAnalysis(queryParams);
      return res.data;
    },
    staleTime: 120_000,
    enabled: dateMode !== 'custom' || (!!fromDate && !!toDate),
  });

  const summary = useMemo(() => data?.summary ?? {}, [data?.summary]);
  const bundleSales: any[] = useMemo(() => data?.bundle_sales ?? [], [data?.bundle_sales]);
  const dailyTrend: any[] = useMemo(() => data?.daily_trend ?? [], [data?.daily_trend]);
  const channelBreakdown: Record<string, any> = useMemo(() => data?.channel_breakdown ?? {}, [data?.channel_breakdown]);
  const categoryBreakdown: Record<string, any> = useMemo(() => data?.category_breakdown ?? {}, [data?.category_breakdown]);

  /* Filter bundle table */
  const filteredBundles = useMemo(() => {
    if (!search) return bundleSales;
    const t = search.toLowerCase();
    return bundleSales.filter(
      (b: any) =>
        b.skuCode?.toLowerCase().includes(t) ||
        b.itemName?.toLowerCase().includes(t) ||
        b.category?.toLowerCase().includes(t)
    );
  }, [bundleSales, search]);

  const totalPages = Math.ceil(filteredBundles.length / PAGE_SIZE);
  const paginated = filteredBundles.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  /* Chart data prep */
  const trendData = useMemo(() =>
    dailyTrend.map(d => ({ ...d, dateLabel: fmtDate(d.date) })),
    [dailyTrend]
  );

  const channelData = useMemo(() =>
    Object.entries(channelBreakdown).map(([name, v]: [string, any]) => ({
      name, revenue: v.revenue, units: v.units, orders: v.orders,
    })),
    [channelBreakdown]
  );

  const categoryData = useMemo(() =>
    Object.entries(categoryBreakdown)
      .slice(0, 10)
      .map(([name, v]: [string, any]) => ({
        name, value: v.revenue, units: v.units, bundle_count: v.bundle_count,
      })),
    [categoryBreakdown]
  );

  const maxTrendRev = useMemo(() => {
    const m = Math.max(...trendData.map(d => d.revenue), 0);
    const step = m > 500000 ? 100000 : m > 50000 ? 50000 : m > 5000 ? 10000 : 1000;
    return Math.ceil(m / step) * step || 1000;
  }, [trendData]);

  /* Period change */
  const handleDateMode = useCallback((mode: ReportDateMode) => {
    setDateMode(mode);
    setPage(0);
  }, []);

  /* Column defs for top bundles table */
  const columns: Column<any>[] = [
    {
      key: 'skuCode', header: 'SKU', width: '10%',
      render: (v) => <span className="font-mono text-xs font-semibold text-slate-900 dark:text-slate-100">{v}</span>,
    },
    {
      key: 'itemName', header: 'Bundle Name', width: '22%',
      render: (v) => <span className="text-sm text-slate-800 dark:text-slate-200 line-clamp-2">{v}</span>,
    },
    {
      key: 'category', header: 'Category', width: '12%',
      render: (v) => (
        <span className="px-2 py-0.5 bg-violet-50 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 rounded-lg text-xs font-medium">
          {v || '-'}
        </span>
      ),
    },
    {
      key: 'units_sold', header: 'Units Sold', width: '9%',
      render: (v) => <span className="font-semibold text-slate-900 dark:text-white">{fmtNum(v || 0)}</span>,
    },
    {
      key: 'revenue', header: 'Revenue', width: '11%',
      render: (v) => <span className="font-semibold text-emerald-600 dark:text-emerald-400">{fmtINR(v || 0)}</span>,
    },
    {
      key: 'avg_selling_price', header: 'Avg SP', width: '9%',
      render: (v) => <span className="text-slate-700 dark:text-slate-300">{fmtINR(v || 0)}</span>,
    },
    {
      key: 'order_count', header: 'Orders', width: '8%',
      render: (v) => <span className="text-slate-600 dark:text-slate-400">{fmtNum(v || 0)}</span>,
    },
    {
      key: 'mrp', header: 'MRP', width: '8%',
      render: (v) => <span className="text-slate-500 dark:text-slate-500">{fmtINR(v || 0)}</span>,
    },
    {
      key: 'componentCount', header: 'Comp', width: '5%',
      render: (v) => <span className="text-xs text-slate-500">{v ?? '-'}</span>,
    },
    {
      key: 'channels', header: 'Top Channel', width: '10%',
      render: (v) => {
        if (!v || typeof v !== 'object') return <span className="text-slate-400">-</span>;
        const top = Object.entries(v).sort((a: any, b: any) => b[1] - a[1])[0];
        if (!top) return <span className="text-slate-400">-</span>;
        return (
          <span className="px-2 py-0.5 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-[10px] font-medium">
            {shortChannel(top[0])} ({String(top[1])})
          </span>
        );
      },
    },
  ];

  return (
    <div className="page-section-gap">
      <PageHeader
        title="Bundle Sales Analysis"
        description="Revenue, quantity & performance insights — derived by reverse-mapping component SKUs to bundle definitions"
      />

      {/* Global Date Range */}
      <div className="mb-6 space-y-3">
        <div className="tab-strip">
          {([
            { key: 'daily' as ReportDateMode, label: 'Daily' },
            { key: 'weekly' as ReportDateMode, label: 'Weekly' },
            { key: 'monthly' as ReportDateMode, label: 'Monthly' },
            { key: 'custom' as ReportDateMode, label: 'Custom' },
          ]).map((p) => (
            <button
              key={p.key}
              onClick={() => handleDateMode(p.key)}
              className={`px-4 py-2 rounded-xl text-sm font-medium transition-all whitespace-nowrap ${dateMode === p.key
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200 dark:shadow-indigo-900/40'
                : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-600'
                }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="flex flex-col lg:flex-row lg:items-center gap-2 lg:gap-3">
          {dateMode === 'daily' && (
            <div className="flex flex-col sm:flex-row sm:items-center gap-2 w-full lg:w-auto">
              <span className="text-sm text-slate-500 dark:text-slate-400">Report Date</span>
              <input
                type="date"
                value={anchorDate}
                onChange={e => setAnchorDate(e.target.value)}
                className="input text-sm px-3 py-1.5 w-full sm:w-auto"
              />
            </div>
          )}

          {dateMode === 'custom' && (
            <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_1fr] gap-2 w-full lg:w-auto">
              <input
                type="date"
                value={fromDate}
                onChange={e => setFromDate(e.target.value)}
                className="input text-sm px-3 py-1.5 w-full"
              />
              <span className="text-slate-400 self-center text-center">→</span>
              <input
                type="date"
                value={toDate}
                onChange={e => setToDate(e.target.value)}
                className="input text-sm px-3 py-1.5 w-full"
              />
            </div>
          )}

          <div className="text-xs text-slate-500 dark:text-slate-400 lg:ml-1">{effectiveRange.label}</div>

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className={`w-full lg:w-auto lg:ml-auto px-4 py-2 rounded-xl text-sm font-medium transition-colors ${isFetching
              ? 'bg-slate-200 dark:bg-slate-700 text-slate-400 cursor-not-allowed'
              : 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm'
              }`}
          >
            {isFetching ? 'Analysing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Loading / Error */}
      <ProgressLoader loading={isLoading || isFetching} stages={[
        { at: 0, label: 'Initializing export job…' },
        { at: 15, label: 'Fetching orders…' },
        { at: 40, label: 'Matching components to bundles…' },
        { at: 70, label: 'Calculating revenue attribution…' },
        { at: 90, label: 'Finalizing…' },
      ]} />

      {error && (
        <div className="card bg-rose-50 dark:bg-rose-900/20 mb-6">
          <p className="text-rose-600 dark:text-rose-400">
            Error: {(error as any)?.message || 'Analysis failed'}
          </p>
        </div>
      )}

      {/* Summary KPIs */}
      {!isLoading && data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-5 mb-6">
            <StatCard
              title="Bundle Orders"
              value={`${fmtNum(summary.orders_with_bundles || 0)} / ${fmtNum(summary.total_orders || 0)}`}
              icon="📦"
              color="purple"
            />
            <StatCard
              title="Attach Rate"
              value={`${summary.bundle_attach_rate || 0}%`}
              icon="📎"
              color="yellow"
            />
            <StatCard
              title="Bundle Units Sold"
              value={fmtNum(summary.total_bundle_units || 0)}
              icon="🛒"
              color="green"
            />
            <StatCard
              title="Bundle Revenue"
              value={fmtINR(summary.total_bundle_revenue || 0)}
              icon="💰"
              color="blue"
            />
          </div>

          {/* Charts Row 1: Revenue Trend + Channel Breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            {/* Revenue Trend */}
            <ChartCard title="Bundle Revenue Trend" subtitle="Daily bundle revenue over time">
              {trendData.length === 0 ? (
                <div className="h-[260px] flex items-center justify-center">
                  <p className="text-sm text-slate-400">No trend data for this period</p>
                </div>
              ) : (
                <div className="h-[260px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={trendData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="bundleRevGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#6366f1" stopOpacity={0.35} />
                          <stop offset="100%" stopColor="#6366f1" stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="currentColor"
                        className="text-slate-100 dark:text-slate-800/60" vertical={false} />
                      <XAxis dataKey="dateLabel" tick={{ fontSize: 11 }}
                        className="text-slate-400 dark:text-slate-500"
                        axisLine={false} tickLine={false} interval="preserveStartEnd" dy={4} />
                      <YAxis tick={{ fontSize: 11 }} className="text-slate-400 dark:text-slate-500"
                        axisLine={false} tickLine={false} width={52}
                        domain={[0, maxTrendRev]} tickFormatter={fmtAxisINR} allowDecimals={false} />
                      <Tooltip content={<RevTooltip />}
                        cursor={{ stroke: '#6366f1', strokeWidth: 1, strokeDasharray: '4 4' }} />
                      <Area type="monotone" dataKey="revenue" stroke="#6366f1" strokeWidth={2.5}
                        fill="url(#bundleRevGrad)"
                        dot={{ r: 3, fill: '#6366f1', stroke: 'white', strokeWidth: 2 }}
                        activeDot={{ r: 5, strokeWidth: 2, fill: '#6366f1', stroke: 'white' }} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>

            {/* Channel Revenue */}
            <ChartCard title="Channel Performance" subtitle="Bundle revenue by sales channel">
              {channelData.length === 0 ? (
                <div className="h-[260px] flex items-center justify-center">
                  <p className="text-sm text-slate-400">No channel data</p>
                </div>
              ) : (
                <div className="h-[260px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={channelData} margin={{ top: 8, right: 4, left: -8, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="currentColor"
                        className="text-slate-200 dark:text-slate-800" vertical={false} />
                      <XAxis dataKey="name" tick={{ fontSize: 10 }}
                        className="text-slate-400 dark:text-slate-500"
                        axisLine={false} tickLine={false} interval={0} tickFormatter={shortChannel} />
                      <YAxis tick={{ fontSize: 11 }} className="text-slate-400 dark:text-slate-500"
                        axisLine={false} tickLine={false} width={44} tickFormatter={fmtAxisINR} />
                      <Tooltip content={<BarTooltip />}
                        cursor={{ fill: 'currentColor', className: 'text-slate-100 dark:text-slate-800/40' }} />
                      <Bar dataKey="revenue" radius={[6, 6, 0, 0]} maxBarSize={48}>
                        {channelData.map((_, i) => (
                          <Cell key={i} fill={COLORS[i % COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>
          </div>

          {/* Charts Row 2: Units Trend + Category Breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            {/* Units Sold Trend */}
            <ChartCard title="Bundle Units Trend" subtitle="Daily bundle quantity sold">
              {trendData.length === 0 ? (
                <div className="h-[260px] flex items-center justify-center">
                  <p className="text-sm text-slate-400">No trend data</p>
                </div>
              ) : (
                <div className="h-[260px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={trendData} margin={{ top: 8, right: 4, left: -8, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="currentColor"
                        className="text-slate-200 dark:text-slate-800" vertical={false} />
                      <XAxis dataKey="dateLabel" tick={{ fontSize: 10 }}
                        className="text-slate-400 dark:text-slate-500"
                        axisLine={false} tickLine={false} interval="preserveStartEnd" />
                      <YAxis tick={{ fontSize: 11 }} className="text-slate-400 dark:text-slate-500"
                        axisLine={false} tickLine={false} width={40} allowDecimals={false} />
                      <Tooltip content={<RevTooltip />}
                        cursor={{ fill: 'currentColor', className: 'text-slate-100 dark:text-slate-800/40' }} />
                      <Bar dataKey="units" radius={[4, 4, 0, 0]} maxBarSize={32} fill="#10b981" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>

            {/* Category Pie */}
            <ChartCard title="Category Revenue Share" subtitle="Top 10 categories by bundle revenue">
              {categoryData.length === 0 ? (
                <div className="h-[260px] flex items-center justify-center">
                  <p className="text-sm text-slate-400">No category data</p>
                </div>
              ) : (
                <div className="h-[260px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={categoryData} cx="50%" cy="50%" outerRadius={90} innerRadius={40}
                        paddingAngle={2} dataKey="value" nameKey="name" label={false}>
                        {categoryData.map((_, i) => (
                          <Cell key={i} fill={COLORS[i % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip content={<PieTooltip />} />
                      <Legend
                        layout="horizontal"
                        align="center"
                        verticalAlign="bottom"
                        formatter={(value: string) => (
                          <span className="text-xs text-slate-600 dark:text-slate-400">
                            {value.length > 18 ? value.slice(0, 18) + '…' : value}
                          </span>
                        )}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>
          </div>

          {/* Comparison Cards Row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
            {/* Top Channel */}
            <div className="card">
              <h3 className="text-sm font-medium text-slate-500 dark:text-slate-400 mb-3">Top Channel</h3>
              {channelData.length > 0 ? (
                <div>
                  <p className="text-xl font-bold text-slate-900 dark:text-white">
                    {shortChannel(channelData[0].name)}
                  </p>
                  <p className="text-sm text-emerald-600 dark:text-emerald-400">
                    {fmtINR(channelData[0].revenue)} · {fmtNum(channelData[0].units)} units
                  </p>
                  <div className="mt-2 space-y-1">
                    {channelData.slice(0, 5).map((ch, i) => {
                      const pct = channelData[0].revenue > 0
                        ? (ch.revenue / channelData.reduce((s, c) => s + c.revenue, 0) * 100).toFixed(1)
                        : '0';
                      return (
                        <div key={i} className="flex items-center gap-2 text-xs">
                          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS[i] }} />
                          <span className="text-slate-600 dark:text-slate-400 flex-1">{shortChannel(ch.name)}</span>
                          <span className="text-slate-900 dark:text-white font-medium">{pct}%</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <p className="text-slate-400 text-sm">No data</p>
              )}
            </div>

            {/* Top Category */}
            <div className="card">
              <h3 className="text-sm font-medium text-slate-500 dark:text-slate-400 mb-3">Top Category</h3>
              {categoryData.length > 0 ? (
                <div>
                  <p className="text-xl font-bold text-slate-900 dark:text-white">
                    {categoryData[0].name.length > 22 ? categoryData[0].name.slice(0, 22) + '…' : categoryData[0].name}
                  </p>
                  <p className="text-sm text-emerald-600 dark:text-emerald-400">
                    {fmtINR(categoryData[0].value)} · {fmtNum(categoryData[0].units)} units
                  </p>
                  <div className="mt-2 space-y-1">
                    {categoryData.slice(0, 5).map((cat, i) => {
                      const totalRev = categoryData.reduce((s, c) => s + c.value, 0);
                      const pct = totalRev > 0 ? (cat.value / totalRev * 100).toFixed(1) : '0';
                      return (
                        <div key={i} className="flex items-center gap-2 text-xs">
                          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS[i] }} />
                          <span className="text-slate-600 dark:text-slate-400 flex-1">
                            {cat.name.length > 16 ? cat.name.slice(0, 16) + '…' : cat.name}
                          </span>
                          <span className="text-slate-900 dark:text-white font-medium">{pct}%</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <p className="text-slate-400 text-sm">No data</p>
              )}
            </div>

            {/* Performance Insights */}
            <div className="card">
              <h3 className="text-sm font-medium text-slate-500 dark:text-slate-400 mb-3">Key Insights</h3>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-500">Bundle attach rate</span>
                  <span className={`text-sm font-bold ${(summary.bundle_attach_rate || 0) > 50 ? 'text-emerald-600' : 'text-amber-600'
                    }`}>
                    {summary.bundle_attach_rate || 0}%
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-500">Avg revenue / bundle</span>
                  <span className="text-sm font-bold text-slate-900 dark:text-white">
                    {fmtINR(summary.avg_revenue_per_bundle || 0)}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-500">Unique bundles sold</span>
                  <span className="text-sm font-bold text-indigo-600 dark:text-indigo-400">
                    {fmtNum(summary.unique_bundles_sold || 0)}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-500">Analysis time</span>
                  <span className="text-xs text-slate-400">{summary.analysis_time || 0}s</span>
                </div>
                {bundleSales.length > 0 && (
                  <>
                    <hr className="border-slate-100 dark:border-slate-700" />
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-slate-500">Best seller</span>
                      <span className="text-xs font-medium text-slate-900 dark:text-white truncate ml-2">
                        {bundleSales[0]?.skuCode} ({fmtNum(bundleSales[0]?.units_sold)} units)
                      </span>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Top Bundles Table */}
          <div className="card">
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3 mb-4">
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
                Top Bundle SKUs by Sales
              </h2>
              <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
                <input
                  type="text"
                  placeholder="Search SKU, name, category…"
                  className="input w-full sm:w-64 text-sm"
                  value={search}
                  onChange={(e) => { setSearch(e.target.value); setPage(0); }}
                />
                <span className="text-sm text-slate-500 dark:text-slate-400">
                  {filteredBundles.length} bundle{filteredBundles.length !== 1 ? 's' : ''}
                </span>
              </div>
            </div>

            <DataTable
              data={paginated}
              columns={columns}
              emptyMessage="No bundle sales found for this period."
            />
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 mt-4">
              <button disabled={page === 0} onClick={() => setPage(page - 1)}
                className="btn btn-secondary disabled:opacity-40">
                ← Previous
              </button>
              <span className="text-sm text-slate-600 dark:text-slate-400">
                Page {page + 1} of {totalPages}
              </span>
              <button disabled={page >= totalPages - 1} onClick={() => setPage(page + 1)}
                className="btn btn-secondary disabled:opacity-40">
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
