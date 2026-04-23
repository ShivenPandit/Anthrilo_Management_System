'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ucSales } from '@/features/sales/api';

const PAGE_SIZE = 15;
const fmt = (v: number) => v >= 100_000 ? `₹${(v / 100_000).toFixed(1)}L` : v >= 1_000 ? `₹${(v / 1_000).toFixed(1)}K` : `₹${v.toLocaleString('en-IN')}`;

const channelColors: Record<string, string> = {
  MYNTRA: 'from-pink-500 to-pink-600', FIRSTCRY_NEW: 'from-orange-500 to-orange-600',
  AMAZON_FLEX: 'from-amber-500 to-amber-600', AMAZON_IN_API: 'from-yellow-500 to-yellow-600',
  SHOPIFY: 'from-green-500 to-green-600', NYKAA_FASHION_NEW: 'from-purple-500 to-purple-600',
  AJIO_OMNI: 'from-blue-500 to-blue-600', MEESHO_26: 'from-teal-500 to-teal-600',
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
const defaultSt = { bg: 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300', dot: 'bg-slate-400' };

export default function SalesTransactionsPage() {
  const [period, setPeriod] = useState('today');
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [paymentFilter, setPaymentFilter] = useState('all');
  const [channelFilter, setChannelFilter] = useState('');
  const [customFrom, setCustomFrom] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 7);
    return d.toISOString().split('T')[0];
  });
  const [customTo, setCustomTo] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    return d.toISOString().split('T')[0];
  });
  const [appliedCustomFrom, setAppliedCustomFrom] = useState('');
  const [appliedCustomTo, setAppliedCustomTo] = useState('');

  const customRangeValid = !!customFrom && !!customTo && customFrom <= customTo;
  const customRangeApplied = period !== 'custom' || (!!appliedCustomFrom && !!appliedCustomTo);
  const customRangeDirty = customFrom !== appliedCustomFrom || customTo !== appliedCustomTo;

  /* Summary aligned to selected period */
  const { data: selectedSummaryData, isLoading: loadingSummary } = useQuery({
    queryKey: ['uc-transactions-summary', period, appliedCustomFrom, appliedCustomTo],
    queryFn: async () => {
      if (period === 'custom') {
        return (await ucSales.getSalesReport({
          period: 'custom',
          from_date: appliedCustomFrom,
          to_date: appliedCustomTo,
        })).data;
      }

      const fn = period === 'today' ? ucSales.getToday : ucSales.getYesterday;
      return (await fn()).data;
    },
    enabled: customRangeApplied,
    staleTime: 2 * 60_000,
  });

  /* Orders (paginated) */
  const { data: ordersData, isLoading, error, isFetching } = useQuery({
    queryKey: ['uc-transactions', period, page, appliedCustomFrom, appliedCustomTo],
    queryFn: async () => {
      if (period === 'custom') {
        return (await ucSales.getOrders({
          period: 'custom',
          from_date: appliedCustomFrom,
          to_date: appliedCustomTo,
          page,
          page_size: 100,
        })).data;
      }
      return (await ucSales.getOrders({ period, page, page_size: 100 })).data;
    },
    enabled: customRangeApplied,
    staleTime: 60_000,
    placeholderData: (prev: any) => prev,
  });

  /* flatten to item-level rows */
  const allRows = useMemo(() => {
    const orders = ordersData?.orders || [];
    const rows: any[] = [];
    orders.forEach((o: any) => {
      const items = o.items || [];
      if (items.length === 0) {
        rows.push({ date: o.displayOrderDateTime || o.created, code: o.displayOrderCode || o.code, channel: o.channel || '-', status: o.status || '-', sku: '-', size: '-', price: o.selling_price || 0, cod: o.cashOnDelivery ?? o.cod ?? false });
      } else {
        items.forEach((it: any) => {
          rows.push({ date: o.displayOrderDateTime || o.created, code: o.displayOrderCode || o.code, channel: o.channel || '-', status: o.status || '-', sku: it.itemSku || it.sku || '-', size: it.size || '-', price: it.sellingPrice || it.selling_price || 0, cod: o.cashOnDelivery ?? o.cod ?? false });
        });
      }
    });
    return rows;
  }, [ordersData]);

  const uniqueChannels = useMemo(() => [...new Set(allRows.map((r) => r.channel).filter((c) => c !== '-'))].sort(), [allRows]);

  /* filter */
  const filtered = useMemo(() => allRows.filter((r) => {
    if (search) { const t = search.toLowerCase(); if (!r.code?.toLowerCase().includes(t) && !r.sku?.toLowerCase().includes(t) && !r.channel?.toLowerCase().includes(t)) return false; }
    if (paymentFilter === 'cod' && !r.cod) return false;
    if (paymentFilter === 'prepaid' && r.cod) return false;
    if (channelFilter && r.channel !== channelFilter) return false;
    return true;
  }), [allRows, search, paymentFilter, channelFilter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const paginated = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  const selectedS = selectedSummaryData?.summary || {};

  /* quick stats from current filtered data */
  const filteredRevenue = useMemo(() => filtered.reduce((s, r) => s + (r.price || 0), 0), [filtered]);
  const codCount = useMemo(() => filtered.filter((r) => r.cod).length, [filtered]);
  const prepaidCount = filtered.length - codCount;

  /* pagination numbers */
  const pageNums = useMemo(() => {
    const nums: (number | '...')[] = [];
    if (totalPages <= 7) { for (let i = 1; i <= totalPages; i++) nums.push(i); return nums; }
    nums.push(1);
    if (safePage > 3) nums.push('...');
    for (let i = Math.max(2, safePage - 1); i <= Math.min(totalPages - 1, safePage + 1); i++) nums.push(i);
    if (safePage < totalPages - 2) nums.push('...');
    nums.push(totalPages);
    return nums;
  }, [safePage, totalPages]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Sales Transactions</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Item-level transaction breakdown from Anthrilo</p>
        </div>
        <div className="flex gap-1.5 bg-slate-100 dark:bg-slate-700/60 rounded-xl p-1 self-start">
          {[{ key: 'today', label: 'Today' }, { key: 'yesterday', label: 'Yesterday' }, { key: 'custom', label: 'Custom' }].map((p) => (
            <button key={p.key} onClick={() => { setPeriod(p.key); setPage(1); }}
              className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all ${period === p.key ? 'bg-white dark:bg-slate-600 text-slate-900 dark:text-white shadow-sm' : 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white'}`}>
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Custom date picker */}
      {period === 'custom' && (
        <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-4 shadow-sm">
          <div className="flex gap-3 items-center flex-wrap">
            <span className="text-sm text-slate-500 dark:text-slate-400">From</span>
            <input type="date" value={customFrom} onChange={(e) => setCustomFrom(e.target.value)}
              max={new Date().toISOString().split('T')[0]}
              className="px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700/40 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40" />
            <span className="text-sm text-slate-500 dark:text-slate-400">to</span>
            <input type="date" value={customTo} onChange={(e) => setCustomTo(e.target.value)}
              max={new Date().toISOString().split('T')[0]}
              className="px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700/40 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40" />
            <button
              type="button"
              onClick={() => {
                if (!customRangeValid) return;
                setAppliedCustomFrom(customFrom);
                setAppliedCustomTo(customTo);
                setPage(1);
              }}
              disabled={!customRangeValid || !customRangeDirty}
              className="px-3 py-1.5 rounded-lg text-sm font-medium bg-blue-600 text-white disabled:opacity-40 disabled:cursor-not-allowed hover:bg-blue-700 transition-colors"
            >
              Fetch Data
            </button>
            {!customRangeApplied && (
              <span className="text-xs text-amber-600 dark:text-amber-300">Choose dates and click Fetch Data.</span>
            )}
            {customRangeApplied && customRangeDirty && (
              <span className="text-xs text-slate-500 dark:text-slate-400">Date changed. Click Fetch Data to refresh.</span>
            )}
          </div>
        </div>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        {([
          { label: 'Revenue Orders', value: selectedS.valid_orders ?? selectedS.total_orders, loading: loadingSummary, icon: '🛒', gradient: 'from-blue-500 to-blue-600' },
          { label: 'All Orders', value: selectedS.total_orders, loading: loadingSummary, icon: '📊', gradient: 'from-violet-500 to-violet-600' },
          { label: 'Selected Revenue', value: selectedS.total_revenue, loading: loadingSummary, icon: '💰', gradient: 'from-emerald-500 to-emerald-600', isCur: true },
          { label: 'Items Sold', value: selectedS.total_items, loading: loadingSummary, icon: '📦', gradient: 'from-indigo-500 to-indigo-600' },
          { label: 'Filtered Revenue', value: filteredRevenue, loading: false, icon: '🔍', gradient: 'from-amber-500 to-amber-600', isCur: true },
          { label: 'Items Shown', value: filtered.length, loading: false, icon: '📋', gradient: 'from-rose-500 to-rose-600' },
        ] as const).map((c) => (
          <div key={c.label} className="relative overflow-hidden rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-4 shadow-sm">
            <div className={`absolute -top-4 -right-4 h-16 w-16 rounded-full bg-gradient-to-br ${c.gradient} opacity-10`} />
            <span className="text-xl">{c.icon}</span>
            <p className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">{c.label}</p>
            <p className="text-xl font-bold text-slate-900 dark:text-white tabular-nums">
              {c.loading ? '…' : (c as any).isCur ? fmt(c.value || 0) : (c.value?.toLocaleString() ?? '-')}
            </p>
          </div>
        ))}
      </div>

      {/* Filter bar */}
      <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-4 shadow-sm">
        <div className="flex flex-wrap gap-3 items-center">
          {/* Payment pills */}
          <div className="flex gap-1.5 bg-slate-100 dark:bg-slate-700/60 rounded-xl p-1">
            {[{ key: 'all', label: 'All' }, { key: 'prepaid', label: `Prepaid (${prepaidCount})` }, { key: 'cod', label: `COD (${codCount})` }].map((f) => (
              <button key={f.key} onClick={() => { setPaymentFilter(f.key); setPage(1); }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${paymentFilter === f.key ? 'bg-white dark:bg-slate-600 text-slate-900 dark:text-white shadow-sm' : 'text-slate-600 dark:text-slate-300'}`}>
                {f.label}
              </button>
            ))}
          </div>

          {/* Channel select */}
          <select value={channelFilter} onChange={(e) => { setChannelFilter(e.target.value); setPage(1); }}
            className="px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700/40 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40">
            <option value="">All Channels</option>
            {uniqueChannels.map((ch) => <option key={ch} value={ch}>{channelLabel(ch)}</option>)}
          </select>

          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
            <input type="text" placeholder="Search order code, SKU, channel…"
              className="w-full pl-10 pr-4 py-1.5 rounded-xl border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700/40 text-sm text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
              value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
          </div>

          <span className="text-xs text-slate-500 dark:text-slate-400 tabular-nums whitespace-nowrap">
            {filtered.length} items · Page {safePage}/{totalPages}
            {isFetching && !isLoading && <span className="ml-1 animate-pulse">⟳</span>}
          </span>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-2xl bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 p-4">
          <p className="text-sm text-rose-600 dark:text-rose-400">{(error as any)?.message || 'Failed to load transactions'}</p>
        </div>
      )}

      {/* Table */}
      <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
              <p className="text-sm text-slate-500 dark:text-slate-400">Fetching transactions…</p>
            </div>
          </div>
        ) : paginated.length === 0 ? (
          <div className="flex items-center justify-center py-20">
            <p className="text-sm text-slate-500 dark:text-slate-400">No transactions found for the selected filters.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60">
                  {['Time', 'Order Code', 'Channel', 'Status', 'SKU', 'Size', 'Price', 'Payment'].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/60">
                {paginated.map((r, idx) => {
                  const st = statusStyle[r.status] || defaultSt;
                  const chGrad = channelColors[r.channel] || 'from-slate-500 to-slate-600';
                  const time = r.date ? r.date.replace(/^\d{4}-\d{2}-\d{2}\s/, '').slice(0, 5) : '-';
                  const dateStr = r.date ? new Date(r.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : '';
                  return (
                    <tr key={r.code + r.sku + idx} className="hover:bg-slate-50/60 dark:hover:bg-slate-700/30 transition-colors">
                      <td className="px-4 py-3">
                        <span className="text-xs text-slate-900 dark:text-white font-medium tabular-nums">{time}</span>
                        {dateStr && <p className="text-[10px] text-slate-400">{dateStr}</p>}
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs font-medium text-slate-900 dark:text-white">{r.code}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-700 dark:text-slate-300">
                          <span className={`h-2 w-2 rounded-full bg-gradient-to-br ${chGrad}`} />
                          {channelLabel(r.channel)}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${st.bg}`}>
                          <span className={`h-1.5 w-1.5 rounded-full ${st.dot}`} />
                          {r.status}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-block px-2 py-0.5 rounded-md bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-mono text-xs font-semibold">{r.sku}</span>
                      </td>
                      <td className="px-4 py-3">
                        {r.size !== '-' ? <span className="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-700 text-xs font-medium text-slate-700 dark:text-slate-300">{r.size}</span> : <span className="text-slate-400 text-xs">-</span>}
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-bold text-emerald-600 dark:text-emerald-400 tabular-nums">₹{(r.price || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium ${r.cod ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300' : 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300'}`}>
                          {r.cod ? 'COD' : 'Prepaid'}
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
          <button disabled={safePage <= 1} onClick={() => setPage(safePage - 1)}
            className="px-4 py-2 rounded-xl text-sm font-medium bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 disabled:opacity-40 transition-colors shadow-sm">
            ← Previous
          </button>
          <div className="flex items-center gap-1">
            {pageNums.map((n, i) => n === '...' ? (
              <span key={`e${i}`} className="px-2 text-slate-400 text-sm">…</span>
            ) : (
              <button key={n} onClick={() => setPage(n as number)}
                className={`min-w-[36px] h-9 rounded-lg text-sm font-medium transition-colors ${n === safePage ? 'bg-blue-600 text-white shadow-sm' : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'}`}>
                {n}
              </button>
            ))}
          </div>
          <button disabled={safePage >= totalPages} onClick={() => setPage(safePage + 1)}
            className="px-4 py-2 rounded-xl text-sm font-medium bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 disabled:opacity-40 transition-colors shadow-sm">
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
