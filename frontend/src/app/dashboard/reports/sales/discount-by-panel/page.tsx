'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ucSales } from '@/features/sales/api';
import { DataTable, Column } from '@/components/ui/DataTable';
import { PageHeader, ProgressLoader, ErrorPanel } from '@/components/ui/Common';
import { motion } from 'framer-motion';
import {
  Percent, Tag, TrendingDown, Store, Download,
} from 'lucide-react';
import { ReportDateMode, resolveReportDateRange } from '@/lib/report-date-range';

const fmt = (v: number) =>
  v >= 100000 ? `₹${(v / 100000).toFixed(1)}L` : `₹${v.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

export default function DiscountByChannelPage() {
  const [mode, setMode] = useState<ReportDateMode>('weekly');
  const [anchorDate, setAnchorDate] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() - 1);
    return date.toISOString().split('T')[0];
  });
  const [fromDate, setFromDate] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() - 7);
    return date.toISOString().split('T')[0];
  });
  const [toDate, setToDate] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() - 1);
    return date.toISOString().split('T')[0];
  });

  const effectiveRange = useMemo(() => resolveReportDateRange({
    mode,
    anchorDate,
    fromDate,
    toDate,
  }), [mode, anchorDate, fromDate, toDate]);

  const { data, isLoading, error } = useQuery({
    queryKey: ['uc-discount-by-channel', mode, effectiveRange.fromDate, effectiveRange.toDate],
    queryFn: async () => (await ucSales.getSalesBySku({
      period: 'custom',
      from_date: effectiveRange.fromDate,
      to_date: effectiveRange.toDate,
    })).data,
    staleTime: 120_000,
  });

  const channelDiscounts = useMemo(() => {
    const skus = data?.skus || [];
    const channelMap: Record<string, { channel: string; orders: number; revenue: number; mrp: number; quantity: number }> = {};

    for (const sku of skus) {
      const channels = sku.channels || {};
      for (const [channel, chData] of Object.entries(channels) as [string, any][]) {
        if (!channelMap[channel]) channelMap[channel] = { channel, orders: 0, revenue: 0, mrp: 0, quantity: 0 };
        channelMap[channel].revenue += chData.revenue || 0;
        channelMap[channel].quantity += chData.quantity || 0;
      }
      const totalRev = sku.total_revenue || 0;
      const totalMrp = sku.total_mrp || totalRev;
      if (totalRev > 0 && totalMrp > 0) {
        for (const [channel, chData] of Object.entries(channels) as [string, any][]) {
          channelMap[channel].mrp += totalMrp * ((chData.revenue || 0) / totalRev);
        }
      }
      for (const ch of Object.keys(channels)) {
        if (channelMap[ch]) channelMap[ch].orders += 1;
      }
    }

    const totalRevenue = Object.values(channelMap).reduce((s, c) => s + c.revenue, 0);

    return Object.values(channelMap)
      .map(ch => {
        const discount = Math.max(ch.mrp - ch.revenue, 0);
        return {
          ...ch,
          revenue: Math.round(ch.revenue * 100) / 100,
          mrp: Math.round(ch.mrp * 100) / 100,
          discount: Math.round(discount * 100) / 100,
          discount_pct: ch.mrp > 0 ? Math.round((discount / ch.mrp) * 10000) / 100 : 0,
          revenue_share: totalRevenue > 0 ? Math.round((ch.revenue / totalRevenue) * 10000) / 100 : 0,
        };
      })
      .sort((a, b) => b.revenue - a.revenue);
  }, [data]);

  const summary = data?.summary || {};

  const handleExport = () => {
    if (!channelDiscounts.length) return;
    const headers = ['Channel', 'MRP', 'Discount', 'Disc %', 'Net Revenue', 'Revenue Share %', 'Items'];
    const rows = channelDiscounts.map(c => [c.channel, c.mrp, c.discount, c.discount_pct, c.revenue, c.revenue_share, c.quantity].join(','));
    const blob = new Blob([headers.join(',') + '\n' + rows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `discount-by-channel-${effectiveRange.fromDate}-to-${effectiveRange.toDate}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  const columns: Column<any>[] = [
    {
      key: 'channel', header: 'Channel', width: '22%',
      render: (v) => (
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center flex-shrink-0">
            <Store className="w-3.5 h-3.5 text-white" />
          </div>
          <span className="font-medium text-sm text-slate-800 dark:text-slate-200">{v}</span>
        </div>
      ),
    },
    {
      key: 'mrp', header: 'MRP Total', width: '13%',
      render: (v) => <span className="text-slate-500 dark:text-slate-400">{fmt(v || 0)}</span>,
    },
    {
      key: 'discount', header: 'Discount', width: '13%',
      render: (v) => <span className="text-orange-600 dark:text-orange-400 font-semibold">{fmt(v || 0)}</span>,
    },
    {
      key: 'discount_pct', header: 'Disc %', width: '10%',
      render: (v) => {
        const pct = v || 0;
        const c = pct > 30 ? 'text-rose-600 dark:text-rose-400 bg-rose-500/10' : pct > 15 ? 'text-amber-600 dark:text-amber-400 bg-amber-500/10' : 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10';
        return <span className={`text-xs font-bold px-2 py-0.5 rounded-md ${c}`}>{pct.toFixed(1)}%</span>;
      },
    },
    {
      key: 'revenue', header: 'Net Revenue', width: '13%',
      render: (v) => <span className="text-emerald-600 dark:text-emerald-400 font-bold">{fmt(v || 0)}</span>,
    },
    {
      key: 'revenue_share', header: 'Revenue Share', width: '18%',
      render: (v) => (
        <div className="flex items-center gap-2.5">
          <div className="flex-1 h-2.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
            <motion.div
              initial={{ width: 0 }} animate={{ width: `${Math.min(v || 0, 100)}%` }}
              transition={{ duration: 0.6, ease: 'easeOut' }}
              className="h-full bg-gradient-to-r from-primary-500 to-primary-600 rounded-full"
            />
          </div>
          <span className="font-semibold text-xs text-slate-600 dark:text-slate-300 w-10 text-right">{(v || 0).toFixed(1)}%</span>
        </div>
      ),
    },
    {
      key: 'quantity', header: 'Items', width: '8%',
      render: (v) => <span className="font-semibold text-slate-900 dark:text-white">{(v || 0).toLocaleString()}</span>,
    },
  ];

  return (
    <div className="page-section-gap">
      <PageHeader title="Discount by Channel" description="Channel-wise discount performance comparison" />

      {/* Controls */}
      <div className="flex flex-col gap-3">
        <div className="tab-strip">
          <div className="tab-strip-inner">
            {[
              { key: 'daily', label: 'Daily' },
              { key: 'weekly', label: 'Weekly' },
              { key: 'monthly', label: 'Monthly' },
              { key: 'custom', label: 'Custom' },
            ].map(p => (
              <button key={p.key} onClick={() => setMode(p.key as ReportDateMode)}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all duration-200 ${
                  mode === p.key
                    ? 'bg-white dark:bg-slate-700 text-primary-600 dark:text-primary-400 shadow-sm'
                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
                }`}>
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
          {mode === 'daily' && (
            <input type="date" className="input w-full sm:w-auto" value={anchorDate} onChange={e => setAnchorDate(e.target.value)} />
          )}
          {mode === 'custom' && (
            <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto">
              <input type="date" className="input w-full sm:w-auto" value={fromDate} onChange={e => setFromDate(e.target.value)} />
              <input type="date" className="input w-full sm:w-auto" value={toDate} onChange={e => setToDate(e.target.value)} />
            </div>
          )}
          <div className="text-xs text-slate-500 dark:text-slate-400 sm:ml-1">{effectiveRange.label}</div>
          <div className="flex-1" />
          <button onClick={handleExport} disabled={!channelDiscounts.length}
            className="btn btn-secondary flex items-center justify-center gap-2 text-xs disabled:opacity-40 w-full sm:w-auto">
            <Download className="w-3.5 h-3.5" /> Export CSV
          </button>
          </div>
      </div>

      {error && <ErrorPanel message="Failed to load channel discount data." />}

      <ProgressLoader loading={isLoading} stages={[
        { at: 0, label: 'Connecting to Unicommerce…' },
        { at: 20, label: 'Aggregating channel data…' },
        { at: 50, label: 'Computing discount metrics…' },
        { at: 80, label: 'Finalizing…' },
      ]} />
      {!isLoading && (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { title: 'Avg Discount', value: `${(summary.avg_discount_pct ?? 0).toFixed(1)}%`, icon: Percent, accent: 'blue' },
              { title: 'Net Revenue', value: fmt(summary.total_revenue ?? 0), icon: Tag, accent: 'emerald' },
              { title: 'Total Discount', value: fmt(summary.total_discount ?? 0), icon: TrendingDown, accent: 'rose' },
              { title: 'Channels', value: `${channelDiscounts.length}`, icon: Store, accent: 'violet' },
            ].map((kpi, i) => (
              <motion.div key={kpi.title}
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, delay: i * 0.05 }}
                className="rounded-2xl border border-slate-200/60 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-[var(--shadow-soft)] p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{kpi.title}</span>
                  <div className={`p-1.5 rounded-lg bg-${kpi.accent}-500/10`}>
                    <kpi.icon className={`w-3.5 h-3.5 text-${kpi.accent}-500`} strokeWidth={2.5} />
                  </div>
                </div>
                <p className="text-xl font-bold text-slate-900 dark:text-white">{kpi.value}</p>
              </motion.div>
            ))}
          </div>

          {/* Channel Cards Mini-Grid (top 4 channels) */}
          {channelDiscounts.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {channelDiscounts.slice(0, 4).map((ch, i) => (
                <motion.div key={ch.channel}
                  initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.2, delay: i * 0.04 }}
                  className="rounded-xl border border-slate-200/60 dark:border-slate-800 bg-white dark:bg-slate-900 p-4"
                >
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
                      <Store className="w-4 h-4 text-white" />
                    </div>
                    <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 truncate">{ch.channel}</p>
                  </div>
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="text-slate-400">Discount</span>
                      <span className={`font-bold ${ch.discount_pct > 30 ? 'text-rose-500' : ch.discount_pct > 15 ? 'text-amber-500' : 'text-emerald-500'}`}>{ch.discount_pct.toFixed(1)}%</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-slate-400">Revenue</span>
                      <span className="font-semibold text-slate-700 dark:text-slate-300">{fmt(ch.revenue)}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-slate-400">Items</span>
                      <span className="font-medium text-slate-600 dark:text-slate-400">{ch.quantity}</span>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          )}

          {/* DataTable */}
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white">All Channels</h3>
              <span className="text-xs text-slate-400">{channelDiscounts.length} channels</span>
            </div>
            <DataTable data={channelDiscounts} columns={columns} emptyMessage="No channel discount data for this period." />
          </div>
        </>
      )}
    </div>
  );
}
