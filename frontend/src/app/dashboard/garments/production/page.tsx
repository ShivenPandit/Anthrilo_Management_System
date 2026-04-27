'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ucSales } from '@/features/sales/api';

const PAGE_SIZE = 15;
type OrdersPeriod = 'today' | 'yesterday' | 'last_7_days' | 'last_30_days' | 'last_month';

/* helpers */
const fmt = (v: number) =>
  v >= 100_000 ? `₹${(v / 100_000).toFixed(1)}L` : v >= 1_000 ? `₹${(v / 1_000).toFixed(1)}K` : `₹${v.toLocaleString('en-IN')}`;

const channelColors: Record<string, string> = {
  MYNTRA: 'from-pink-500 to-pink-600',
  FIRSTCRY_NEW: 'from-orange-500 to-orange-600',
  AMAZON_FLEX: 'from-amber-500 to-amber-600',
  AMAZON_IN_API: 'from-yellow-500 to-yellow-600',
  SHOPIFY: 'from-green-500 to-green-600',
  NYKAA_FASHION_NEW: 'from-purple-500 to-purple-600',
  AJIO_OMNI: 'from-blue-500 to-blue-600',
  MEESHO_26: 'from-teal-500 to-teal-600',
  TATACLIQ: 'from-indigo-500 to-indigo-600',
};
const channelLabel = (c: string) => c.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase()).replace(/ New$/, '').replace(/ Api$/, '').replace(/ 26$/, '');

const statusStyle: Record<string, { bg: string; dot: string }> = {
  CREATED: { bg: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300', dot: 'bg-blue-500' },
  PROCESSING: { bg: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300', dot: 'bg-amber-500' },
  COMPLETE: { bg: 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300', dot: 'bg-emerald-500' },
  CANCELLED: { bg: 'bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300', dot: 'bg-rose-500' },
  DISPATCHED: { bg: 'bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300', dot: 'bg-violet-500' },
  SHIPPED: { bg: 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300', dot: 'bg-indigo-500' },
  DELIVERED: { bg: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300', dot: 'bg-green-500' },
  PENDING_VERIFICATION: { bg: 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300', dot: 'bg-slate-400' },
};
const defaultStatus = { bg: 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300', dot: 'bg-slate-400' };

const getLastMonthRange = () => {
  const now = new Date();
  const firstOfCurrentMonth = new Date(now.getFullYear(), now.getMonth(), 1);
  const monthStart = new Date(firstOfCurrentMonth.getFullYear(), firstOfCurrentMonth.getMonth() - 1, 1);
  const monthEnd = new Date(firstOfCurrentMonth.getFullYear(), firstOfCurrentMonth.getMonth(), 0);

  const toYmd = (d: Date) => {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  return {
    from: toYmd(monthStart),
    to: toYmd(monthEnd),
  };
};

export default function OrdersPage() {
  const [period, setPeriod] = useState<OrdersPeriod>('today');
  const [page, setPage] = useState(1);
  const [channelFilter, setChannelFilter] = useState<string | null>(null);
  const lastMonthRange = useMemo(() => getLastMonthRange(), []);

  /* Summary data (includes channel_breakdown, status_breakdown) */
  const { data: summaryRaw, isLoading: summaryLoading } = useQuery({
    queryKey: ['uc-orders-summary', period, lastMonthRange.from, lastMonthRange.to],
    queryFn: async () => {
      if (period === 'last_month') {
        return (await ucSales.getSalesReport({
          period: 'custom',
          from_date: lastMonthRange.from,
          to_date: lastMonthRange.to,
        })).data;
      }

      const fn = period === 'today' ? ucSales.getToday
        : period === 'yesterday' ? ucSales.getYesterday
          : period === 'last_7_days' ? ucSales.getLast7Days
            : ucSales.getLast30Days;
      return (await fn()).data;
    },
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  const summary = useMemo(() => summaryRaw?.summary ?? {}, [summaryRaw?.summary]);

  /* channels derived from channel_breakdown */
  const channels = useMemo(() => {
    const cb = summary.channel_breakdown || {};
    return Object.entries(cb)
      .map(([name, data]: [string, any]) => ({ name, orders: data.orders, revenue: data.revenue, items: data.items }))
      .sort((a, b) => b.revenue - a.revenue);
  }, [summary]);

  const totalRevenue = summary.total_revenue || 0;
  const revenueOrders = summary.valid_orders ?? summary.total_orders ?? 0;

  /* statuses from status_breakdown */
  const statuses = useMemo(() => {
    const sb = summary.status_breakdown || {};
    return Object.entries(sb)
      .map(([name, count]: [string, any]) => ({ name, count: count as number }))
      .sort((a, b) => b.count - a.count);
  }, [summary]);

  /* Paginated Orders */
  const { data: ordersData, isLoading, error, isFetching } = useQuery({
    queryKey: ['uc-orders-page', period, page, lastMonthRange.from, lastMonthRange.to],
    queryFn: async () => {
      if (period === 'last_month') {
        return (await ucSales.getOrders({
          period: 'custom',
          from_date: lastMonthRange.from,
          to_date: lastMonthRange.to,
          page,
          page_size: PAGE_SIZE,
        })).data;
      }
      return (await ucSales.getOrders({ period, page, page_size: PAGE_SIZE })).data;
    },
    staleTime: 60_000,
    placeholderData: (prev: any) => prev,
  });

  const rawOrders = useMemo(() => ordersData?.orders ?? [], [ordersData?.orders]);
  const orders = useMemo(() => {
    const mapped = rawOrders.map((o: any) => ({
      code: o.code || o.displayOrderCode || '-',
      channel: o.channel || '-',
      status: o.status || '-',
      items: o.item_count || o.items?.length || 0,
      selling_price: o.selling_price || o.total_selling_price || 0,
      net_revenue: o.net_revenue || o.selling_price || 0,
      created: o.created || o.displayOrderDateTime || '',
      cod: o.cashOnDelivery || o.cod || false,
      itemSku: o.items?.[0]?.itemSku || o.items?.[0]?.sku || '-',
    }));
    if (!channelFilter) return mapped;
    return mapped.filter((o: any) => o.channel === channelFilter);
  }, [rawOrders, channelFilter]);

  const totalOrders = ordersData?.pagination?.total_orders || ordersData?.total || rawOrders.length;
  const totalPages = ordersData?.pagination?.total_pages || ordersData?.total_pages || Math.ceil(totalOrders / PAGE_SIZE) || 1;

  /* pagination numbers */
  const pageNums = useMemo(() => {
    const nums: (number | '...')[] = [];
    if (totalPages <= 7) { for (let i = 1; i <= totalPages; i++) nums.push(i); return nums; }
    nums.push(1);
    if (page > 3) nums.push('...');
    for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) nums.push(i);
    if (page < totalPages - 2) nums.push('...');
    nums.push(totalPages);
    return nums;
  }, [page, totalPages]);

  /*  */
  return (
    <div className="space-y-6">
      {/* Header + period toggle */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Orders &amp; Channels</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            {revenueOrders != null
              ? `${Number(revenueOrders).toLocaleString()} revenue orders · ${fmt(totalRevenue)} revenue · ${channels.length} channels`
              : 'Loading…'}
          </p>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
            30-day view is rolling last 30 complete days. Use Last Month to match month-wise reports.
          </p>
        </div>
        <div className="flex gap-1.5 bg-slate-100 dark:bg-slate-700/60 rounded-xl p-1 self-start">
          {([
            { key: 'today', label: 'Today' },
            { key: 'yesterday', label: 'Yesterday' },
            { key: 'last_7_days', label: '7 Days' },
            { key: 'last_30_days', label: 'Last 30 Days' },
            { key: 'last_month', label: 'Last Month' },
          ] as Array<{ key: OrdersPeriod; label: string }>).map((p) => (
            <button key={p.key} onClick={() => { setPeriod(p.key); setPage(1); setChannelFilter(null); }}
              className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all ${period === p.key
                ? 'bg-white dark:bg-slate-600 text-slate-900 dark:text-white shadow-sm'
                : 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white'
                }`}>
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {([
          { label: 'Revenue Orders', value: revenueOrders, icon: '🛒', gradient: 'from-blue-500 to-blue-600', suffix: '' },
          { label: 'Revenue', value: totalRevenue, icon: '💰', gradient: 'from-emerald-500 to-emerald-600', fmt: true },
          { label: 'Avg Order', value: summary.avg_order_value, icon: '📊', gradient: 'from-violet-500 to-violet-600', fmt: true },
          { label: 'Channels', value: channels.length, icon: '🏪', gradient: 'from-amber-500 to-amber-600', suffix: '' },
        ] as const).map((c) => (
          <div key={c.label} className="relative overflow-hidden rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-4 shadow-sm">
            <div className={`absolute -top-4 -right-4 h-16 w-16 rounded-full bg-gradient-to-br ${c.gradient} opacity-10`} />
            <span className="text-xl">{c.icon}</span>
            <p className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">{c.label}</p>
            <p className="text-2xl font-bold text-slate-900 dark:text-white tabular-nums">
              {summaryLoading ? '…' : (c as any).fmt ? fmt(c.value || 0) : (c.value?.toLocaleString() ?? '-')}
            </p>
          </div>
        ))}
      </div>

      {/* Channel breakdown */}
      {channels.length > 0 && (
        <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold text-slate-900 dark:text-white">Channel Performance</h2>
            {channelFilter && (
              <button onClick={() => setChannelFilter(null)}
                className="text-xs px-3 py-1 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors">
                Clear filter: {channelLabel(channelFilter)} ✕
              </button>
            )}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {channels.map((ch) => {
              const pct = totalRevenue > 0 ? Math.round((ch.revenue / totalRevenue) * 100) : 0;
              const isActive = channelFilter === ch.name;
              const grad = channelColors[ch.name] || 'from-slate-500 to-slate-600';
              return (
                <button key={ch.name} onClick={() => setChannelFilter(isActive ? null : ch.name)}
                  className={`text-left p-3.5 rounded-xl border transition-all group ${isActive
                    ? 'border-blue-400 dark:border-blue-500 bg-blue-50/50 dark:bg-blue-900/20 ring-1 ring-blue-400/30'
                    : 'border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 hover:border-slate-300 dark:hover:border-slate-600'
                    }`}>
                  <div className="flex items-center gap-2 mb-2">
                    <div className={`h-2.5 w-2.5 rounded-full bg-gradient-to-br ${grad}`} />
                    <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 truncate">{channelLabel(ch.name)}</p>
                  </div>
                  <p className="text-lg font-bold text-slate-900 dark:text-white tabular-nums">{fmt(ch.revenue)}</p>
                  <div className="flex items-center gap-2 mt-1.5">
                    <div className="flex-1 h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
                      <div className={`h-full rounded-full bg-gradient-to-r ${grad}`} style={{ width: `${pct}%` }} />
                    </div>
                    <span className="text-[10px] text-slate-500 tabular-nums">{pct}%</span>
                  </div>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 tabular-nums">{ch.orders} orders · {ch.items} items</p>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Status breakdown (horizontal bar) */}
      {statuses.length > 0 && (
        <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm p-5">
          <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-3">Order Status</h2>
          <div className="flex flex-wrap gap-3">
            {statuses.map((s) => {
              const st = statusStyle[s.name] || defaultStatus;
              const total = summary.total_orders || 1;
              const pct = Math.round((s.count / total) * 100);
              return (
                <div key={s.name} className="flex items-center gap-2 min-w-[140px]">
                  <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${st.bg}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${st.dot}`} />
                    {s.name.replace(/_/g, ' ')}
                  </div>
                  <span className="text-sm font-bold text-slate-900 dark:text-white tabular-nums">{s.count}</span>
                  <span className="text-[10px] text-slate-400 tabular-nums">({pct}%)</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-2xl bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 p-4">
          <p className="text-sm text-rose-600 dark:text-rose-400">
            {(error as any)?.response?.data?.detail || (error as any)?.message || 'Failed to load orders'}
          </p>
        </div>
      )}

      {/* Orders table */}
      <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 dark:border-slate-700">
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            Recent Orders
          </h2>
          <span className="text-xs text-slate-500 dark:text-slate-400 tabular-nums">
            {totalOrders.toLocaleString()} total · Page {page}/{totalPages}
            {isFetching && !isLoading && <span className="ml-1 animate-pulse">⟳</span>}
          </span>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
              <p className="text-sm text-slate-500 dark:text-slate-400">Fetching orders…</p>
            </div>
          </div>
        ) : orders.length === 0 ? (
          <div className="flex items-center justify-center py-20">
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {channelFilter ? `No orders from ${channelLabel(channelFilter)} on this page.` : 'No orders found for the selected period.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60">
                  {['Order Code', 'Channel', 'Status', 'Items', 'Created', 'Amount', 'Type'].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/60">
                {orders.map((o: any, idx: number) => {
                  const st = statusStyle[o.status] || defaultStatus;
                  const chGrad = channelColors[o.channel] || 'from-slate-500 to-slate-600';
                  return (
                    <tr key={o.code + idx} className="hover:bg-slate-50/60 dark:hover:bg-slate-700/30 transition-colors">
                      {/* Order Code */}
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs font-medium text-slate-900 dark:text-white">{o.code}</span>
                        {o.itemSku !== '-' && (
                          <p className="text-[11px] text-slate-400 mt-0.5">{o.itemSku}</p>
                        )}
                      </td>
                      {/* Channel */}
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-700 dark:text-slate-300">
                          <span className={`h-2 w-2 rounded-full bg-gradient-to-br ${chGrad}`} />
                          {channelLabel(o.channel)}
                        </span>
                      </td>
                      {/* Status */}
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${st.bg}`}>
                          <span className={`h-1.5 w-1.5 rounded-full ${st.dot}`} />
                          {o.status}
                        </span>
                      </td>
                      {/* Items */}
                      <td className="px-4 py-3">
                        <span className="font-semibold text-slate-900 dark:text-white tabular-nums">{o.items}</span>
                      </td>
                      {/* Created */}
                      <td className="px-4 py-3">
                        <span className="text-xs text-slate-600 dark:text-slate-400 tabular-nums">{o.created ? o.created.replace(/^\d{4}-\d{2}-\d{2}\s/, '').slice(0, 5) : '-'}</span>
                      </td>
                      {/* Amount */}
                      <td className="px-4 py-3">
                        <span className="font-bold text-emerald-600 dark:text-emerald-400 tabular-nums">₹{o.selling_price.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
                      </td>
                      {/* Payment type */}
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium ${o.cod
                          ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
                          : 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300'
                          }`}>
                          {o.cod ? 'COD' : 'Prepaid'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-between items-center">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}
            className="px-4 py-2 rounded-xl text-sm font-medium bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 disabled:opacity-40 transition-colors shadow-sm">
            ← Previous
          </button>
          <div className="flex items-center gap-1">
            {pageNums.map((n, i) =>
              n === '...' ? (
                <span key={`e${i}`} className="px-2 text-slate-400 text-sm">…</span>
              ) : (
                <button key={n} onClick={() => setPage(n as number)}
                  className={`min-w-[36px] h-9 rounded-lg text-sm font-medium transition-colors ${n === page
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'
                    }`}>
                  {n}
                </button>
              )
            )}
          </div>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}
            className="px-4 py-2 rounded-xl text-sm font-medium bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 disabled:opacity-40 transition-colors shadow-sm">
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
