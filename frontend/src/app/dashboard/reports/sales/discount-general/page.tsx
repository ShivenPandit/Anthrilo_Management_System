'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ucSales } from '@/features/sales/api';
import { DataTable, Column } from '@/components/ui/DataTable';
import { PageHeader, ProgressLoader, ErrorPanel } from '@/components/ui/Common';
import { motion } from 'framer-motion';
import {
  Percent, Package, Tag, TrendingDown,
  Search, ChevronLeft, ChevronRight, Download,
} from 'lucide-react';
import { ReportDateMode, resolveReportDateRange } from '@/lib/report-date-range';

const PAGE_SIZE = 15;
const fmt = (v: number) => `₹${v.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

const BUCKETS = [
  { label: '0%', filter: (v: number) => v === 0, color: 'bg-emerald-500', ring: 'ring-emerald-500/20' },
  { label: '1–10%', filter: (v: number) => v > 0 && v <= 10, color: 'bg-blue-500', ring: 'ring-blue-500/20' },
  { label: '10–20%', filter: (v: number) => v > 10 && v <= 20, color: 'bg-amber-500', ring: 'ring-amber-500/20' },
  { label: '20–30%', filter: (v: number) => v > 20 && v <= 30, color: 'bg-orange-500', ring: 'ring-orange-500/20' },
  { label: '30%+', filter: (v: number) => v > 30, color: 'bg-rose-500', ring: 'ring-rose-500/20' },
];

export default function DiscountAnalysisPage() {
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
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);

  const effectiveRange = useMemo(() => resolveReportDateRange({
    mode,
    anchorDate,
    fromDate,
    toDate,
  }), [mode, anchorDate, fromDate, toDate]);

  const { data, isLoading, error } = useQuery({
    queryKey: ['uc-discount-analysis', mode, effectiveRange.fromDate, effectiveRange.toDate],
    queryFn: async () => (await ucSales.getSalesBySku({
      period: 'custom',
      from_date: effectiveRange.fromDate,
      to_date: effectiveRange.toDate,
    })).data,
    staleTime: 120_000,
  });

  const allSkus = useMemo(() =>
    (data?.skus || []).map((s: any) => ({ ...s, discount_pct: s.discount_pct ?? 0 })),
    [data]
  );
  const summary = data?.summary || {};

  const bucketCounts = useMemo(() =>
    BUCKETS.map(b => ({ ...b, count: allSkus.filter((s: any) => b.filter(s.discount_pct)).length })),
    [allSkus]
  );

  const filtered = useMemo(() => {
    if (!search) return allSkus;
    const term = search.toLowerCase();
    return allSkus.filter((s: any) =>
      s.sku?.toLowerCase().includes(term) || s.name?.toLowerCase().includes(term)
    );
  }, [allSkus, search]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const handleExport = () => {
    if (!filtered.length) return;
    const headers = ['SKU', 'Product Name', 'Qty', 'MRP Total', 'Discount', 'Disc %', 'Net Revenue', 'Avg SP', 'Avg MRP'];
    const rows = filtered.map((s: any) => [s.sku, `"${(s.name || '').replace(/"/g, '""')}"`, s.total_quantity, s.total_mrp?.toFixed(2), s.total_discount?.toFixed(2), s.discount_pct?.toFixed(1), s.total_revenue?.toFixed(2), s.avg_selling_price?.toFixed(2), s.avg_mrp?.toFixed(2)].join(','));
    const blob = new Blob([headers.join(',') + '\n' + rows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `discount-analysis-${effectiveRange.fromDate}-to-${effectiveRange.toDate}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  const columns: Column<any>[] = [
    {
      key: 'sku', header: 'SKU', width: '13%',
      render: (v) => <span className="font-mono text-xs text-slate-700 dark:text-slate-300">{v}</span>,
    },
    {
      key: 'name', header: 'Product', width: '20%',
      render: (v) => <span className="text-sm text-slate-800 dark:text-slate-200 truncate block max-w-[200px]" title={v}>{v || '—'}</span>,
    },
    {
      key: 'total_quantity', header: 'Qty', width: '5%',
      render: (v) => <span className="font-semibold text-slate-900 dark:text-white">{v}</span>,
    },
    {
      key: 'total_mrp', header: 'MRP', width: '10%',
      render: (v) => <span className="text-slate-500 dark:text-slate-400">{fmt(v || 0)}</span>,
    },
    {
      key: 'total_discount', header: 'Discount', width: '10%',
      render: (v) => <span className="text-orange-600 dark:text-orange-400 font-semibold">{fmt(v || 0)}</span>,
    },
    {
      key: 'discount_pct', header: 'Disc %', width: '9%',
      render: (v) => {
        const pct = v || 0;
        const c = pct > 30 ? 'text-rose-600 dark:text-rose-400 bg-rose-500/10' : pct > 15 ? 'text-amber-600 dark:text-amber-400 bg-amber-500/10' : pct > 0 ? 'text-blue-600 dark:text-blue-400 bg-blue-500/10' : 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10';
        return <span className={`text-xs font-bold px-2 py-0.5 rounded-md ${c}`}>{pct.toFixed(1)}%</span>;
      },
    },
    {
      key: 'total_revenue', header: 'Revenue', width: '11%',
      render: (v) => <span className="text-emerald-600 dark:text-emerald-400 font-bold">{fmt(v || 0)}</span>,
    },
    {
      key: 'avg_selling_price', header: 'Avg SP', width: '9%',
      render: (v) => <span className="text-slate-700 dark:text-slate-300">{fmt(v || 0)}</span>,
    },
    {
      key: 'avg_mrp', header: 'Avg MRP', width: '9%',
      render: (v) => <span className="text-slate-400">{fmt(v || 0)}</span>,
    },
  ];

  return (
    <div className="page-section-gap">
      <PageHeader title="SKU Discount Analysis" description="Product-level discount breakdown with distribution buckets" />

      {/* Controls bar */}
      <div className="flex flex-col gap-3">
        <div className="tab-strip">
          <div className="tab-strip-inner">
            {[
              { key: 'daily', label: 'Daily' },
              { key: 'weekly', label: 'Weekly' },
              { key: 'monthly', label: 'Monthly' },
              { key: 'custom', label: 'Custom' },
            ].map(p => (
              <button key={p.key} onClick={() => { setMode(p.key as ReportDateMode); setPage(0); }}
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
            <input type="date" className="input w-full sm:w-auto" value={anchorDate} onChange={e => { setAnchorDate(e.target.value); setPage(0); }} />
          )}
          {mode === 'custom' && (
            <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto">
              <input type="date" className="input w-full sm:w-auto" value={fromDate} onChange={e => { setFromDate(e.target.value); setPage(0); }} />
              <input type="date" className="input w-full sm:w-auto" value={toDate} onChange={e => { setToDate(e.target.value); setPage(0); }} />
            </div>
          )}
          <div className="text-xs text-slate-500 dark:text-slate-400 sm:ml-1">{effectiveRange.label}</div>
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input type="text" placeholder="Search SKU or product name..."
              className="input pl-9 w-full"
              value={search} onChange={e => { setSearch(e.target.value); setPage(0); }} />
          </div>
          <button onClick={handleExport} disabled={!filtered.length}
            className="btn btn-secondary flex items-center justify-center gap-2 text-xs disabled:opacity-40 w-full sm:w-auto">
            <Download className="w-3.5 h-3.5" /> Export CSV
          </button>
        </div>
      </div>

      {error && <ErrorPanel message="Failed to load discount data." />}

      <ProgressLoader loading={isLoading} stages={[
        { at: 0, label: 'Connecting to Unicommerce…' },
        { at: 20, label: 'Analyzing discounts…' },
        { at: 55, label: 'Computing per-SKU metrics…' },
        { at: 80, label: 'Finalizing…' },
      ]} />
      {!isLoading && (
        <>
          {/* KPI Row */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { title: 'Avg Discount', value: `${(summary.avg_discount_pct ?? 0).toFixed(1)}%`, icon: Percent, accent: 'blue' },
              { title: 'Total SKUs', value: `${summary.total_skus ?? 0}`, icon: Package, accent: 'violet' },
              { title: 'Net Revenue', value: fmt(summary.total_revenue ?? 0), icon: Tag, accent: 'emerald' },
              { title: 'Total Discount', value: fmt(summary.total_discount ?? 0), icon: TrendingDown, accent: 'rose' },
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

          {/* Distribution Buckets */}
          <div className="card">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-3">Discount Distribution</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              {bucketCounts.map((b, i) => {
                const pct = allSkus.length > 0 ? (b.count / allSkus.length) * 100 : 0;
                return (
                  <motion.div key={b.label}
                    initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.2, delay: i * 0.04 }}
                    className={`rounded-xl p-3 text-center ring-1 ${b.ring} bg-white dark:bg-slate-900`}
                  >
                    <div className={`w-8 h-8 rounded-lg ${b.color} mx-auto mb-2 flex items-center justify-center`}>
                      <span className="text-[10px] font-bold text-white">{b.label}</span>
                    </div>
                    <p className="text-lg font-bold text-slate-900 dark:text-white">{b.count}</p>
                    <p className="text-[10px] text-slate-400">{pct.toFixed(0)}% of SKUs</p>
                  </motion.div>
                );
              })}
            </div>
          </div>

          {/* DataTable */}
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white">SKU Breakdown</h3>
              <span className="text-xs text-slate-400">{filtered.length} SKUs</span>
            </div>
            <DataTable data={paginated} columns={columns} emptyMessage="No discount data for this period." />
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <button disabled={page === 0} onClick={() => setPage(page - 1)}
                className="btn btn-secondary flex items-center gap-1 text-xs disabled:opacity-40">
                <ChevronLeft className="w-3.5 h-3.5" /> Previous
              </button>
              <div className="flex items-center gap-1 flex-wrap">
                {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                  const p = totalPages <= 7 ? i : page < 3 ? i : page > totalPages - 4 ? totalPages - 7 + i : page - 3 + i;
                  return (
                    <button key={p} onClick={() => setPage(p)}
                      className={`w-8 h-8 rounded-lg text-xs font-medium transition-colors ${
                        p === page ? 'bg-primary-600 text-white' : 'text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800'
                      }`}>{p + 1}</button>
                  );
                })}
              </div>
              <button disabled={page >= totalPages - 1} onClick={() => setPage(page + 1)}
                className="btn btn-secondary flex items-center gap-1 text-xs disabled:opacity-40">
                Next <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
