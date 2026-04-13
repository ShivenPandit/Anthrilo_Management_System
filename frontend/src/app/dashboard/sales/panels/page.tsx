'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ucSales } from '@/features/sales/api';

const fmt = (v: number) => v >= 100_000 ? `₹${(v / 100_000).toFixed(1)}L` : v >= 1_000 ? `₹${(v / 1_000).toFixed(1)}K` : `₹${v.toLocaleString('en-IN')}`;

const channelColors: Record<string, { bar: string; bg: string }> = {
  MYNTRA: { bar: 'bg-pink-500', bg: 'bg-pink-100 dark:bg-pink-900/30 text-pink-700 dark:text-pink-300' },
  FIRSTCRY_NEW: { bar: 'bg-orange-500', bg: 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300' },
  AMAZON_FLEX: { bar: 'bg-amber-500', bg: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300' },
  AMAZON_IN_API: { bar: 'bg-yellow-500', bg: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300' },
  SHOPIFY: { bar: 'bg-green-500', bg: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300' },
  NYKAA_FASHION_NEW: { bar: 'bg-purple-500', bg: 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300' },
  AJIO_OMNI: { bar: 'bg-blue-500', bg: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300' },
  MEESHO_26: { bar: 'bg-teal-500', bg: 'bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-300' },
  TATACLIQ: { bar: 'bg-indigo-500', bg: 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300' },
};
const defaultChColor = { bar: 'bg-slate-500', bg: 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300' };

const channelLabel = (c: string) => c.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase()).replace(/ New$/, '').replace(/ Api$/, '').replace(/ 26$/, '');

const statusDot: Record<string, string> = {
  PROCESSING: 'bg-amber-500', COMPLETE: 'bg-emerald-500', CANCELLED: 'bg-rose-500',
  CREATED: 'bg-blue-500', SHIPPED: 'bg-indigo-500', DELIVERED: 'bg-green-500',
  DISPATCHED: 'bg-violet-500', PENDING_VERIFICATION: 'bg-slate-400',
};

type Period = 'today' | 'yesterday' | 'last7' | 'last30';

export default function PanelsPage() {
  const [period, setPeriod] = useState<Period>('today');

  const { data: raw, isLoading, error } = useQuery({
    queryKey: ['uc-panels', period],
    queryFn: async () => {
      const fn = period === 'today' ? ucSales.getToday
        : period === 'yesterday' ? ucSales.getYesterday
          : period === 'last7' ? ucSales.getLast7Days
            : ucSales.getLast30Days;
      return (await fn()).data;
    },
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  const summary = useMemo(() => raw?.summary ?? {}, [raw?.summary]);
  const totalRev = summary.total_revenue || 0;

  /* channels sorted by revenue */
  const channels = useMemo(() => {
    const cb = summary.channel_breakdown || {};
    return Object.entries(cb)
      .map(([name, d]: [string, any]) => ({ name, orders: d.orders, revenue: d.revenue, items: d.items }))
      .sort((a, b) => b.revenue - a.revenue);
  }, [summary]);
  const maxChRev = channels.length > 0 ? channels[0].revenue : 1;

  /* statuses */
  const statuses = useMemo(() => {
    const sb = summary.status_breakdown || {};
    return Object.entries(sb).map(([name, count]: [string, any]) => ({ name, count: count as number })).sort((a, b) => b.count - a.count);
  }, [summary]);
  const totalStatusOrders = statuses.reduce((s, v) => s + v.count, 0) || 1;

  /* daily breakdown for sparkline */
  const daily = useMemo(() => (summary.daily_breakdown || []) as { date: string; orders: number; revenue: number }[], [summary]);
  const maxDailyRev = useMemo(() => Math.max(...daily.map((d) => d.revenue), 1), [daily]);

  const periodLabels: Record<Period, string> = { today: 'Today', yesterday: 'Yesterday', last7: '7 Days', last30: '30 Days' };

  return (
    <div className="space-y-6">
      {/* Header + period */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Sales Analytics</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            {summary.total_orders != null ? `${summary.total_orders.toLocaleString()} orders · ${fmt(totalRev)} revenue` : 'Loading analytics…'}
          </p>
        </div>
        <div className="flex gap-1.5 bg-slate-100 dark:bg-slate-700/60 rounded-xl p-1 self-start">
          {(Object.keys(periodLabels) as Period[]).map((p) => (
            <button key={p} onClick={() => setPeriod(p)}
              className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all ${period === p ? 'bg-white dark:bg-slate-600 text-slate-900 dark:text-white shadow-sm' : 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white'}`}>
              {periodLabels[p]}
            </button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-2xl bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 p-4">
          <p className="text-sm text-rose-600 dark:text-rose-400">{(error as any)?.message || 'Failed to load data'}</p>
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {([
          { label: 'Total Orders', value: summary.total_orders, icon: '📦', gradient: 'from-blue-500 to-blue-600' },
          { label: 'Revenue', value: totalRev, icon: '💰', gradient: 'from-emerald-500 to-emerald-600', isCur: true },
          { label: 'Avg Order Value', value: summary.avg_order_value, icon: '📊', gradient: 'from-violet-500 to-violet-600', isCur: true },
          { label: 'Valid Orders', value: summary.valid_orders, icon: '✅', gradient: 'from-green-500 to-green-600' },
        ] as const).map((c) => (
          <div key={c.label} className="relative overflow-hidden rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-4 shadow-sm">
            <div className={`absolute -top-4 -right-4 h-16 w-16 rounded-full bg-gradient-to-br ${c.gradient} opacity-10`} />
            <span className="text-xl">{c.icon}</span>
            <p className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">{c.label}</p>
            <p className="text-2xl font-bold text-slate-900 dark:text-white tabular-nums">
              {isLoading ? '…' : (c as any).isCur ? fmt(c.value || 0) : (c.value?.toLocaleString() ?? '-')}
            </p>
          </div>
        ))}
      </div>

      {/* Revenue Breakdown card */}
      {!isLoading && (
        <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm p-5">
          <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-1">Revenue Breakdown</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-5">{periodLabels[period]}</p>
          <div className="grid grid-cols-3 gap-6 text-center">
            <div>
              <p className="text-xs text-slate-500 dark:text-slate-400">Total Revenue</p>
              <p className="text-2xl font-bold text-slate-900 dark:text-white tabular-nums">{fmt(totalRev)}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500 dark:text-slate-400">Total Discount</p>
              <p className="text-2xl font-bold text-rose-600 dark:text-rose-400 tabular-nums">{fmt(summary.total_discount || 0)}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500 dark:text-slate-400">Excluded Orders</p>
              <p className="text-2xl font-bold text-slate-900 dark:text-white tabular-nums">{(summary.excluded_orders || 0).toLocaleString()}</p>
            </div>
          </div>
        </div>
      )}

      {/* Channel Revenue Chart (horizontal bar) */}
      {channels.length > 0 && (
        <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm p-5">
          <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-4">Channel Revenue</h2>
          <div className="space-y-3">
            {channels.map((ch) => {
              const pct = totalRev > 0 ? Math.round((ch.revenue / totalRev) * 100) : 0;
              const barW = maxChRev > 0 ? Math.max(2, Math.round((ch.revenue / maxChRev) * 100)) : 0;
              const colors = channelColors[ch.name] || defaultChColor;
              return (
                <div key={ch.name} className="flex items-center gap-3">
                  <span className="w-[120px] text-xs font-medium text-slate-700 dark:text-slate-300 truncate">{channelLabel(ch.name)}</span>
                  <div className="flex-1 h-7 rounded-lg bg-slate-100 dark:bg-slate-700/50 overflow-hidden relative">
                    <div className={`h-full rounded-lg ${colors.bar} transition-all duration-500`} style={{ width: `${barW}%` }} />
                    <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[11px] font-semibold text-slate-700 dark:text-slate-200 tabular-nums">{fmt(ch.revenue)}</span>
                  </div>
                  <span className="w-[60px] text-right text-xs text-slate-500 dark:text-slate-400 tabular-nums">{ch.orders} ord</span>
                  <span className="w-[36px] text-right text-[11px] text-slate-400 tabular-nums">{pct}%</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Status + Daily side-by-side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Status donut-like visualization */}
        {statuses.length > 0 && (
          <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm p-5">
            <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-4">Order Status</h2>
            {/* stacked bar */}
            <div className="h-5 rounded-full overflow-hidden flex mb-4">
              {statuses.map((s) => {
                const pct = (s.count / totalStatusOrders) * 100;
                return <div key={s.name} className={`${statusDot[s.name] || 'bg-slate-400'} transition-all`} style={{ width: `${pct}%` }} title={`${s.name}: ${s.count}`} />;
              })}
            </div>
            <div className="grid grid-cols-2 gap-2">
              {statuses.map((s) => {
                const pct = Math.round((s.count / totalStatusOrders) * 100);
                return (
                  <div key={s.name} className="flex items-center gap-2 py-1.5">
                    <span className={`h-2.5 w-2.5 rounded-full ${statusDot[s.name] || 'bg-slate-400'}`} />
                    <span className="text-xs text-slate-600 dark:text-slate-400 flex-1 truncate">{s.name.replace(/_/g, ' ')}</span>
                    <span className="text-sm font-bold text-slate-900 dark:text-white tabular-nums">{s.count}</span>
                    <span className="text-[10px] text-slate-400 tabular-nums w-[30px] text-right">{pct}%</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Daily trend mini chart */}
        {daily.length > 1 && (
          <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm p-5">
            <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-4">Daily Revenue Trend</h2>
            <div className="flex items-end gap-1.5 h-[180px]">
              {daily.map((d, i) => {
                const h = Math.max(4, Math.round((d.revenue / maxDailyRev) * 160));
                const dateLabel = new Date(d.date + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
                return (
                  <div key={i} className="flex-1 flex flex-col items-center justify-end gap-1 group relative">
                    {/* tooltip */}
                    <div className="absolute bottom-full mb-2 hidden group-hover:block z-10">
                      <div className="bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 text-[10px] px-2 py-1 rounded-lg shadow-lg whitespace-nowrap tabular-nums">
                        {fmt(d.revenue)} · {d.orders} orders
                      </div>
                    </div>
                    <div className="w-full rounded-t-md bg-blue-500 dark:bg-blue-400 transition-all duration-300 hover:bg-blue-600 dark:hover:bg-blue-300 cursor-default" style={{ height: `${h}px` }} />
                    <span className="text-[9px] text-slate-400 tabular-nums">{dateLabel}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Channel detail cards grid */}
      {channels.length > 0 && (
        <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm p-5">
          <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-4">Channel Details</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {channels.map((ch) => {
              const pct = totalRev > 0 ? Math.round((ch.revenue / totalRev) * 100) : 0;
              const colors = channelColors[ch.name] || defaultChColor;
              return (
                <div key={ch.name} className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                  <div className="flex items-center gap-2 mb-2">
                    <div className={`h-2.5 w-2.5 rounded-full ${colors.bar}`} />
                    <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 truncate">{channelLabel(ch.name)}</p>
                  </div>
                  <p className="text-lg font-bold text-slate-900 dark:text-white tabular-nums">{fmt(ch.revenue)}</p>
                  <div className="flex items-center gap-2 mt-1.5">
                    <div className="flex-1 h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
                      <div className={`h-full rounded-full ${colors.bar}`} style={{ width: `${pct}%` }} />
                    </div>
                    <span className="text-[10px] text-slate-500 tabular-nums">{pct}%</span>
                  </div>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 tabular-nums">{ch.orders} orders · {ch.items} items</p>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
