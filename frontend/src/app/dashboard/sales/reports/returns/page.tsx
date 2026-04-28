'use client';

import { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ucSales } from '@/features/sales/api';
import { motion, AnimatePresence } from 'framer-motion';
import { ProgressLoader } from '@/components/ui/Common';
import {
  Calendar, Download, BarChart3, TrendingUp, TrendingDown, AlertTriangle,
  ArrowUpDown, ArrowUp, ArrowDown, Search, Flame, ShieldAlert,
  Package, RotateCcw, Undo2, Loader2, ChevronDown, Hash,
} from 'lucide-react';
import {
  PieChart, Pie, Cell, Tooltip as RTooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Legend,
} from 'recharts';
import { DayPicker } from 'react-day-picker';
import 'react-day-picker/style.css';
import { format, parse } from 'date-fns';
import { getYesterdayIst, getIstRelativeDate } from '@/lib/ist-date';

/* helpers */
const fmtCurr = (v: number) => `₹${v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtShort = (v: number) =>
  v >= 10_000_000 ? `₹${(v / 10_000_000).toFixed(2)}Cr`
    : v >= 100_000 ? `₹${(v / 100_000).toFixed(1)}L`
      : v >= 1_000 ? `₹${(v / 1_000).toFixed(1)}K`
        : `₹${v.toLocaleString('en-IN')}`;

const channelLabel = (c: string) =>
  c.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())
    .replace(/ New$/, '').replace(/ Api$/, '').replace(/ 26$/, '');

const CHANNEL_COLORS: Record<string, string> = {
  FIRSTCRY_NEW: '#F97316', MYNTRA: '#EC4899', NYKAA_FASHION_NEW: '#A855F7',
  AMAZON_FLEX: '#F59E0B', AMAZON_IN_API: '#EAB308', SHOPIFY: '#22C55E',
  AJIO_OMNI: '#3B82F6', MEESHO_26: '#14B8A6', FLIPKART: '#6366F1',
  TATACLIQ: '#8B5CF6', SNAPDEAL_NEW: '#EF4444',
};
const getColor = (ch: string, i: number) => CHANNEL_COLORS[ch] || ['#F97316', '#EC4899', '#A855F7', '#3B82F6', '#14B8A6', '#F59E0B', '#6366F1', '#EF4444', '#8B5CF6', '#22C55E'][i % 10];

const riskBadge = (pct: number) =>
  pct >= 40 ? { label: 'High Risk', cls: 'bg-rose-50 dark:bg-rose-900/20 text-rose-500 dark:text-rose-400', dot: 'bg-rose-500' }
    : pct >= 20 ? { label: 'Medium', cls: 'bg-violet-50 dark:bg-violet-900/20 text-violet-500 dark:text-violet-400', dot: 'bg-violet-500' }
      : { label: 'Low Risk', cls: 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-500 dark:text-emerald-400', dot: 'bg-emerald-500' };

/* animated counter */
function AnimatedNum({ value, prefix = '' }: { value: number; prefix?: string }) {
  const [display, setDisplay] = useState(0);
  const prev = useRef(0);
  useEffect(() => {
    const start = prev.current, diff = value - start, t0 = performance.now();
    const step = (now: number) => {
      const p = Math.min((now - t0) / 800, 1);
      setDisplay(Math.round(start + diff * (1 - Math.pow(1 - p, 3))));
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
    prev.current = value;
  }, [value]);
  return <>{prefix}{display.toLocaleString('en-IN')}</>;
}

/* sort types */
type ChSortKey = 'channel' | 'returns' | 'items' | 'value' | 'rto' | 'cir' | 'pct' | 'valuePct';
type SkuSortKey = 'sku' | 'name' | 'quantity' | 'value' | 'return_count';
type Dir = 'asc' | 'desc';

type ReportPeriod = 'daily' | 'weekly' | 'monthly' | 'custom';

const PERIOD_OPTIONS: { value: ReportPeriod; label: string }[] = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'custom', label: 'Custom' },
];

const SKU_ROWS_PER_PAGE = 50;

const createProgressId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `report-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

/*  */
export default function ReturnReportPage() {
  const [reportDate, setReportDate] = useState<string>(() => {
    return getYesterdayIst();
  });
  const [fromDate, setFromDate] = useState<string>(() => {
    return getIstRelativeDate(-7);
  });
  const [toDate, setToDate] = useState<string>(() => {
    return getYesterdayIst();
  });
  const [period, setPeriod] = useState<ReportPeriod>('daily');
  const [showReport, setShowReport] = useState(true);
  const [calOpen, setCalOpen] = useState(false);
  const calRef = useRef<HTMLDivElement>(null);

  // Channel table state
  const [chSort, setChSort] = useState<ChSortKey>('value');
  const [chDir, setChDir] = useState<Dir>('desc');

  // SKU table state
  const [skuSort, setSkuSort] = useState<SkuSortKey>('value');
  const [skuDir, setSkuDir] = useState<Dir>('desc');
  const [skuSearch, setSkuSearch] = useState('');
  const [skuPage, setSkuPage] = useState(1);
  const [activeProgressId, setActiveProgressId] = useState<string | null>(null);
  const [backendPercent, setBackendPercent] = useState(0);
  const [backendLabel, setBackendLabel] = useState('');

  // Close calendar on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (calRef.current && !calRef.current.contains(e.target as Node)) setCalOpen(false);
    };
    if (calOpen) document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [calOpen]);

  const canGenerate = period !== 'custom' || (!!fromDate && !!toDate);

  const { data: raw, isLoading, isFetching, isError, error } = useQuery({
    queryKey: ['return-report', period, reportDate, fromDate, toDate, activeProgressId],
    queryFn: async () => {
      const params: any = { return_type: 'ALL', period };
      if (period === 'custom') {
        params.from_date = fromDate;
        params.to_date = toDate;
      } else if (period === 'daily') {
        params.date = reportDate;
      }
      params.progress_id = activeProgressId || undefined;
      return (await ucSales.getReturnReport(params)).data;
    },
    enabled: showReport && canGenerate,
    staleTime: 5 * 60_000,
    retry: false,
  });

  const { data: progressData } = useQuery({
    queryKey: ['return-report-progress', activeProgressId],
    queryFn: async () => {
      if (!activeProgressId) return null;
      const res = await ucSales.getReportProgress(activeProgressId);
      return res.data;
    },
    enabled: !!activeProgressId && (isLoading || isFetching),
    refetchInterval: (isLoading || isFetching) ? 800 : false,
    retry: false,
    staleTime: 0,
  });

  useEffect(() => {
    if (!progressData) return;
    const nextPercent = Number(progressData.percent || 0);
    if (Number.isFinite(nextPercent)) {
      setBackendPercent((prev) => (nextPercent > prev ? nextPercent : prev));
    }
    const nextLabel = String(progressData.label || '').trim();
    if (nextLabel) setBackendLabel(nextLabel);
  }, [progressData]);

  const queryLoading = isLoading || isFetching;

  const handleGenerate = useCallback(() => {
    setBackendPercent(1);
    setBackendLabel('Starting return report generation…');
    setActiveProgressId(createProgressId());
    setShowReport(true);
  }, []);

  /* CSV download */
  const handleCSV = useCallback(() => {
    if (!raw?.by_channel) return;
    const hdr = ['Channel', 'Returns', 'Items', 'Value (₹)', 'Return %', 'Value %', 'RTO', 'CIR'];
    const totalRet = raw.totals.total_returns || 1;
    const totalVal = raw.totals.total_value || 1;
    const rows = raw.by_channel.map((ch: any) => [
      channelLabel(ch.channel), ch.returns, ch.items, ch.value.toFixed(2),
      ((ch.returns / totalRet) * 100).toFixed(1) + '%',
      ((ch.value / totalVal) * 100).toFixed(1) + '%', ch.rto, ch.cir,
    ]);
    rows.push(['TOTAL', raw.totals.total_returns, raw.totals.total_items, raw.totals.total_value.toFixed(2), '100%', '100%', raw.totals.rto_count, raw.totals.cir_count]);
    const csv = [hdr.join(','), ...rows.map((r: any) => r.join(','))].join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    const from = raw?.from_date || reportDate;
    const to = raw?.to_date || reportDate;
    const suffix = from === to ? from : `${from}_to_${to}`;
    const a = document.createElement('a'); a.href = url; a.download = `return-report-${suffix}.csv`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
  }, [raw, reportDate]);

  /* derived data */
  const totals = raw?.totals;
  const totalRet = totals?.total_returns || 1;
  const totalVal = totals?.total_value || 1;

  const channels = useMemo(() => {
    if (!raw?.by_channel) return [];
    return raw.by_channel.map((ch: any, i: number) => ({
      ...ch,
      label: channelLabel(ch.channel),
      color: getColor(ch.channel, i),
      pct: (ch.returns / totalRet) * 100,
      valuePct: (ch.value / totalVal) * 100,
      rtoRatio: ch.returns > 0 ? (ch.rto / ch.returns) * 100 : 0,
    })).sort((a: any, b: any) => b.value - a.value);
  }, [raw, totalRet, totalVal]);

  const topChannel = channels[0];
  const maxChVal = topChannel?.value || 1;

  const highestRtoChannel = useMemo(() => {
    if (!channels.length) return null;
    return [...channels].sort((a, b) => b.rtoRatio - a.rtoRatio)[0];
  }, [channels]);

  /* channel sort */
  const sortedChannels = useMemo(() => {
    return [...channels].sort((a: any, b: any) => {
      const va = chSort === 'channel' ? a.label : a[chSort];
      const vb = chSort === 'channel' ? b.label : b[chSort];
      if (typeof va === 'string') return chDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      return chDir === 'asc' ? va - vb : vb - va;
    });
  }, [channels, chSort, chDir]);

  /* sku data */
  const skus = useMemo(() => {
    if (!raw?.by_sku) return [];
    const maxSkuVal = Math.max(...raw.by_sku.map((s: any) => s.value), 1);
    return raw.by_sku.map((s: any, i: number) => ({
      ...s,
      rank: i + 1,
      barW: Math.max(3, Math.round((s.value / maxSkuVal) * 100)),
    }));
  }, [raw]);

  const filteredSkus = useMemo(() => {
    let list = skuSearch
      ? skus.filter((s: any) => s.sku.toLowerCase().includes(skuSearch.toLowerCase()) || s.name.toLowerCase().includes(skuSearch.toLowerCase()))
      : skus;
    return [...list].sort((a: any, b: any) => {
      const va = a[skuSort]; const vb = b[skuSort];
      if (typeof va === 'string') return skuDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      return skuDir === 'asc' ? va - vb : vb - va;
    });
  }, [skus, skuSearch, skuSort, skuDir]);

  const totalSkuPages = Math.max(1, Math.ceil(filteredSkus.length / SKU_ROWS_PER_PAGE));

  const paginatedSkus = useMemo(() => {
    const start = (skuPage - 1) * SKU_ROWS_PER_PAGE;
    return filteredSkus.slice(start, start + SKU_ROWS_PER_PAGE);
  }, [filteredSkus, skuPage]);

  useEffect(() => {
    setSkuPage(1);
  }, [skuSearch, skuSort, skuDir, period, fromDate, toDate, reportDate]);

  useEffect(() => {
    if (skuPage > totalSkuPages) setSkuPage(totalSkuPages);
  }, [skuPage, totalSkuPages]);

  /* chart data */
  const pieData = useMemo(
    () => channels.map((ch: any) => ({ name: ch.label, value: ch.value, color: ch.color })),
    [channels],
  );
  const rtoBarData = useMemo(
    () => channels.map((ch: any) => ({ name: ch.label, RTO: ch.rto, CIR: ch.cir })),
    [channels],
  );
  const topSkuBarData = useMemo(
    () => skus.slice(0, 5).map((s: any) => ({ name: s.sku, value: s.value })).reverse(),
    [skus],
  );

  /* insights */
  const insights = useMemo(() => {
    if (!channels.length) return [];
    const ins: { icon: any; color: string; title: string; desc: string }[] = [];
    if (topChannel) ins.push({
      icon: AlertTriangle, color: 'red', title: 'Highest Returns',
      desc: `${topChannel.label} — ${topChannel.returns} returns (${topChannel.pct.toFixed(1)}% of total)`,
    });
    if (highestRtoChannel && highestRtoChannel.rto > 0) ins.push({
      icon: RotateCcw, color: 'amber', title: 'Highest RTO Ratio',
      desc: `${highestRtoChannel.label} — ${highestRtoChannel.rtoRatio.toFixed(1)}% RTO rate (${highestRtoChannel.rto} of ${highestRtoChannel.returns})`,
    });
    if (skus.length > 0) ins.push({
      icon: Package, color: 'violet', title: 'Top SKU by Value',
      desc: `${skus[0].sku} — ${fmtCurr(skus[0].value)} (${skus[0].return_count} returns)`,
    });
    return ins;
  }, [channels, topChannel, highestRtoChannel, skus]);

  const toggleChSort = (k: ChSortKey) => { if (chSort === k) setChDir(d => d === 'asc' ? 'desc' : 'asc'); else { setChSort(k); setChDir('desc'); } };
  const toggleSkuSort = (k: SkuSortKey) => { if (skuSort === k) setSkuDir(d => d === 'asc' ? 'desc' : 'asc'); else { setSkuSort(k); setSkuDir('desc'); } };

  const SortIcn = ({ active, dir }: { active: boolean; dir: Dir }) =>
    active ? (dir === 'asc' ? <ArrowUp className="w-3.5 h-3.5" /> : <ArrowDown className="w-3.5 h-3.5" />) : <ArrowUpDown className="w-3.5 h-3.5 opacity-30" />;

  const dateLabel = useMemo(() => {
    const from = raw?.from_date || (period === 'custom' ? fromDate : reportDate);
    const to = raw?.to_date || (period === 'custom' ? toDate : reportDate);
    if (from === to) {
      return format(parse(from, 'yyyy-MM-dd', new Date()), 'EEEE, dd MMMM yyyy');
    }
    return `${format(parse(from, 'yyyy-MM-dd', new Date()), 'dd MMM yyyy')} - ${format(parse(to, 'yyyy-MM-dd', new Date()), 'dd MMM yyyy')}`;
  }, [raw, period, fromDate, toDate, reportDate]);

  /*  */
  return (
    <div className="page-section-gap">
      {/* Header */}
      <div>
        <h1 className="responsive-title text-slate-900 dark:text-white">Return Report</h1>
        <p className="responsive-subtitle mt-1">RTO & Customer-Initiated Returns · Risk analytics</p>
      </div>

      {/* Filters */}
      <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm p-4 sm:p-5">
        <div className="flex flex-wrap items-end gap-3">
          {/* Period */}
          <div className="w-full sm:min-w-[260px]">
            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">Range</label>
            <div className="tab-strip">
              <div className="tab-strip-inner">
                {PERIOD_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => { setPeriod(opt.value); setShowReport(false); setCalOpen(false); }}
                    className={`px-3 py-2 text-xs font-medium rounded-lg whitespace-nowrap transition ${period === opt.value ? 'bg-violet-600 text-white' : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'}`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Date picker */}
          {period === 'daily' && (
            <div className="w-full sm:flex-1 sm:min-w-[180px] sm:max-w-[240px]" ref={calRef}>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">Report date</label>
              <div className="relative">
                <button type="button" onClick={() => setCalOpen(o => !o)}
                  className="w-full flex items-center gap-2 pl-3 pr-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-violet-500 text-left">
                  <Calendar className="w-4 h-4 text-slate-400 flex-shrink-0" />
                  <span>{format(parse(reportDate, 'yyyy-MM-dd', new Date()), 'dd MMM yyyy')}</span>
                </button>
                <AnimatePresence>
                  {calOpen && (
                    <motion.div initial={{ opacity: 0, y: 6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 6, scale: 0.97 }} transition={{ duration: 0.15 }}
                      className="absolute left-0 top-full mt-2 z-50 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-xl p-3">
                      <DayPicker mode="single"
                        selected={parse(reportDate, 'yyyy-MM-dd', new Date())}
                        onSelect={(day) => { if (day) { setReportDate(format(day, 'yyyy-MM-dd')); setShowReport(false); setCalOpen(false); } }}
                        disabled={{ after: new Date() }}
                        defaultMonth={parse(reportDate, 'yyyy-MM-dd', new Date())}
                        classNames={{
                          root: 'rdp-custom',
                          month_caption: 'text-sm font-semibold text-slate-900 dark:text-white flex items-center justify-center py-1',
                          weekday: 'text-[11px] font-medium text-slate-400 dark:text-slate-500 w-9 text-center',
                          day_button: 'h-9 w-9 rounded-lg text-sm text-slate-700 dark:text-slate-300 hover:bg-violet-50 dark:hover:bg-slate-700 transition cursor-pointer flex items-center justify-center',
                          today: 'font-bold text-violet-600 dark:text-violet-400',
                          selected: '!bg-violet-600 !text-white rounded-lg font-semibold',
                          disabled: 'text-slate-300 dark:text-slate-600 cursor-not-allowed opacity-40',
                          chevron: 'fill-slate-500 dark:fill-slate-400 w-4 h-4',
                        }}
                      />
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          )}

          {period === 'custom' && (
            <>
              <div className="w-full sm:min-w-[170px] sm:w-auto">
                <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">From</label>
                <input
                  type="date"
                  aria-label="Return report start date"
                  title="Return report start date"
                  value={fromDate}
                  max={toDate || undefined}
                  onChange={(e) => { setFromDate(e.target.value); setShowReport(false); }}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-violet-500"
                />
              </div>
              <div className="w-full sm:min-w-[170px] sm:w-auto">
                <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">To</label>
                <input
                  type="date"
                  aria-label="Return report end date"
                  title="Return report end date"
                  value={toDate}
                  min={fromDate || undefined}
                  max={getIstRelativeDate(0)}
                  onChange={(e) => { setToDate(e.target.value); setShowReport(false); }}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-violet-500"
                />
              </div>
            </>
          )}

          <button onClick={handleGenerate} disabled={queryLoading || !canGenerate}
            className="inline-flex items-center justify-center gap-2 px-5 py-2 rounded-xl bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium transition disabled:opacity-50 shadow-sm w-full sm:w-auto">
            {queryLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <BarChart3 className="w-4 h-4" />}
            {queryLoading ? 'Generating…' : 'Generate Report'}
          </button>
          {showReport && raw?.success && (
            <button onClick={handleCSV}
              className="inline-flex items-center justify-center gap-2 px-5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-sm font-medium text-slate-700 dark:text-slate-300 transition shadow-sm w-full sm:w-auto">
              <Download className="w-4 h-4" /> Download CSV
            </button>
          )}
        </div>
      </div>

      {/* Loading */}
      <ProgressLoader loading={queryLoading} stages={[
        { at: 0, label: 'Initializing export job…' },
        { at: 15, label: 'Fetching return orders…' },
        { at: 40, label: 'Classifying RTO vs CIR…' },
        { at: 70, label: 'Building channel breakdown…' },
        { at: 90, label: 'Finalizing…' },
      ]}
        progressPercent={Math.max(backendPercent, 0)}
        progressLabel={backendLabel || undefined}
      />

      {/* Error */}
      {showReport && (isError || (raw && !raw.success)) && !queryLoading && (
        <div className="rounded-2xl bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 p-4">
          <p className="text-sm text-rose-600 dark:text-rose-400">
            {raw?.error || (error as any)?.message || 'Failed to generate report'}
          </p>
        </div>
      )}

      {/* Report content */}
      <AnimatePresence>
        {showReport && raw?.success && totals && !queryLoading && (
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }} className="space-y-8">

            {/* Hero summary */}
            <div className="rounded-2xl bg-gradient-to-br from-slate-800 via-slate-900 to-violet-950 p-6 sm:p-8 shadow-lg text-white relative overflow-hidden">
              <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjAiIGhlaWdodD0iNjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGRlZnM+PHBhdHRlcm4gaWQ9ImciIHdpZHRoPSI2MCIgaGVpZ2h0PSI2MCIgcGF0dGVyblVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHBhdGggZD0iTTAgMGg2MHY2MEgweiIgZmlsbD0ibm9uZSIvPjxjaXJjbGUgY3g9IjMwIiBjeT0iMzAiIHI9IjEuNSIgZmlsbD0icmdiYSgyNTUsMjU1LDI1NSwwLjA2KSIvPjwvcGF0dGVybj48L2RlZnM+PHJlY3QgZmlsbD0idXJsKCNnKSIgd2lkdGg9IjEwMCUiIGhlaWdodD0iMTAwJSIvPjwvc3ZnPg==')] opacity-50" />
              <div className="relative z-10">
                <div className="flex items-center gap-2 mb-1">
                  <ShieldAlert className="w-4 h-4 opacity-70" />
                  <span className="text-xs font-medium opacity-70 uppercase tracking-wider">{dateLabel} · RTO + CIR</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 mt-4">
                  <div>
                    <p className="text-xs font-medium text-violet-300 mb-1">Total Returns</p>
                    <p className="text-3xl sm:text-4xl font-extrabold tabular-nums tracking-tight">
                      <AnimatedNum value={totals.total_returns} />
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-violet-300 mb-1">Return Value</p>
                    <p className="text-2xl sm:text-3xl font-bold tabular-nums">
                      <AnimatedNum value={Math.round(totals.total_value)} prefix="₹" />
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-violet-300 mb-1">RTO / CIR</p>
                    <p className="text-2xl sm:text-3xl font-bold tabular-nums">
                      {totals.rto_count} <span className="text-lg opacity-60">/</span> {totals.cir_count}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-violet-300 mb-1">Highest Risk</p>
                    <p className="text-xl sm:text-2xl font-bold truncate">{topChannel?.label || '—'}</p>
                    {topChannel && <p className="text-xs text-violet-300 mt-0.5">{topChannel.pct.toFixed(1)}% of all returns</p>}
                  </div>
                </div>
              </div>
            </div>

            {/* No returns case */}
            {totals.total_returns === 0 && (
              <div className="rounded-2xl bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 p-8 text-center">
                <p className="text-2xl mb-2">✅</p>
                <p className="text-sm text-emerald-700 dark:text-emerald-300 font-medium">No returns found for this selected range</p>
              </div>
            )}

            {totals.total_returns > 0 && (
              <>
                {/* Charts */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Donut */}
                  <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm p-5">
                    <h2 className="text-base font-semibold text-slate-900 dark:text-white mb-4">Returns by Channel (Value)</h2>
                    <div className="h-[280px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie data={pieData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} paddingAngle={2} dataKey="value" animationDuration={800}>
                            {pieData.map((e: any, i: number) => <Cell key={i} fill={e.color} stroke="none" />)}
                          </Pie>
                          <RTooltip content={({ active, payload }) => {
                            if (!active || !payload?.length) return null;
                            const d = payload[0].payload;
                            return (
                              <div className="rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 shadow-lg px-3.5 py-2.5 min-w-[150px]">
                                <p className="text-xs font-semibold text-slate-900 dark:text-white mb-1">{d.name}</p>
                                <div className="flex items-center gap-2">
                                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: d.color }} />
                                  <span className="text-sm font-bold tabular-nums text-slate-700 dark:text-slate-200">{fmtCurr(d.value)}</span>
                                </div>
                                <p className="text-[11px] text-slate-400 mt-0.5">{((d.value / totalVal) * 100).toFixed(1)}% of total</p>
                              </div>
                            );
                          }} />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                    <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-2">
                      {pieData.map((e: any) => (
                        <div key={e.name} className="flex items-center gap-1.5">
                          <span className="h-2.5 w-2.5 rounded-full" style={{ background: e.color }} />
                          <span className="text-[11px] text-slate-500 dark:text-slate-400">{e.name}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* RTO vs CIR bar */}
                  <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm p-5">
                    <h2 className="text-base font-semibold text-slate-900 dark:text-white mb-4">RTO vs CIR per Channel</h2>
                    <div className="h-[320px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={rtoBarData} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e2e8f0" />
                          <XAxis type="number" tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                          <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                          <RTooltip content={({ active, payload, label }) => {
                            if (!active || !payload?.length) return null;
                            return (
                              <div className="rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 shadow-lg px-3.5 py-2.5">
                                <p className="text-xs font-semibold text-slate-900 dark:text-white mb-1.5">{label}</p>
                                {payload.map((p: any) => (
                                  <div key={p.dataKey} className="flex items-center gap-2 text-sm">
                                    <span className="h-2.5 w-2.5 rounded-full" style={{ background: p.fill }} />
                                    <span className="text-slate-500 dark:text-slate-400">{p.dataKey}:</span>
                                    <span className="font-bold tabular-nums text-slate-700 dark:text-slate-200">{p.value}</span>
                                  </div>
                                ))}
                              </div>
                            );
                          }} />
                          <Legend wrapperStyle={{ fontSize: 11 }} />
                          <Bar dataKey="RTO" fill="#8B5CF6" radius={[0, 4, 4, 0]} stackId="a" />
                          <Bar dataKey="CIR" fill="#EC4899" radius={[0, 4, 4, 0]} stackId="a" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </div>

                {/* Top 5 SKUs bar chart */}
                {topSkuBarData.length > 0 && (
                  <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm p-5">
                    <h2 className="text-base font-semibold text-slate-900 dark:text-white mb-4">Top 5 SKUs by Return Value</h2>
                    <div className="h-[220px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={topSkuBarData} layout="vertical" margin={{ left: 10, right: 24, top: 4, bottom: 4 }}>
                          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e2e8f0" />
                          <XAxis type="number" tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false}
                            tickFormatter={(v: number) => fmtShort(v)} />
                          <YAxis type="category" dataKey="name" width={80} tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                          <RTooltip content={({ active, payload }) => {
                            if (!active || !payload?.length) return null;
                            const d = payload[0].payload;
                            return (
                              <div className="rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 shadow-lg px-3.5 py-2.5">
                                <p className="text-xs font-semibold text-slate-900 dark:text-white mb-1">{d.name}</p>
                                <p className="text-sm font-bold tabular-nums text-violet-600 dark:text-violet-400">{fmtCurr(d.value)}</p>
                              </div>
                            );
                          }} />
                          <Bar dataKey="value" fill="#8B5CF6" radius={[0, 6, 6, 0]} animationDuration={800} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {/* Insights */}
                {insights.length > 0 && (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    {insights.map((ins, i) => (
                      <motion.div key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }}
                        className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm p-4 flex items-start gap-3">
                        <div className={`mt-0.5 rounded-lg p-2 ${ins.color === 'red' ? 'bg-rose-50 dark:bg-rose-900/20 text-rose-500 dark:text-rose-400' : ins.color === 'amber' ? 'bg-indigo-50 dark:bg-indigo-900/20 text-indigo-500 dark:text-indigo-400' : 'bg-violet-50 dark:bg-violet-900/20 text-violet-500 dark:text-violet-400'}`}>
                          <ins.icon className="w-4 h-4" />
                        </div>
                        <div>
                          <p className="text-xs font-semibold text-slate-900 dark:text-white">{ins.title}</p>
                          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 leading-relaxed">{ins.desc}</p>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                )}

                {/* Channel Table */}
                <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
                  <div className="p-4 border-b border-slate-100 dark:border-slate-700">
                    <h2 className="text-base font-semibold text-slate-900 dark:text-white">Channel Breakdown</h2>
                  </div>
                  <div className="table-scroll-wrap">
                    <table className="w-full">
                      <thead>
                        <tr className="bg-slate-50/80 dark:bg-slate-900/50 sticky top-0 z-10">
                          {([
                            { key: 'channel' as ChSortKey, label: 'Channel', align: 'left' },
                            { key: 'returns' as ChSortKey, label: 'Returns', align: 'right' },
                            { key: 'pct' as ChSortKey, label: 'Return %', align: 'right' },
                            { key: 'value' as ChSortKey, label: 'Value', align: 'right' },
                            { key: 'valuePct' as ChSortKey, label: 'Value %', align: 'right' },
                            { key: 'rto' as ChSortKey, label: 'RTO', align: 'right' },
                            { key: 'cir' as ChSortKey, label: 'CIR', align: 'right' },
                          ] as const).map((col) => (
                            <th key={col.key} onClick={() => toggleChSort(col.key)}
                              className={`px-5 py-3 text-[11px] font-semibold uppercase tracking-wider cursor-pointer select-none transition hover:text-slate-900 dark:hover:text-white ${col.align === 'left' ? 'text-left' : 'text-right'} text-slate-500 dark:text-slate-400`}>
                              <span className="inline-flex items-center gap-1">{col.label} <SortIcn active={chSort === col.key} dir={chDir} /></span>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-slate-700/60">
                        {sortedChannels.map((ch: any, idx: number) => {
                          const risk = riskBadge(ch.pct);
                          const isTop = ch.channel === topChannel?.channel;
                          const rank = channels.findIndex((c: any) => c.channel === ch.channel);
                          const valBarW = Math.max(3, Math.round((ch.value / maxChVal) * 100));
                          return (
                            <motion.tr key={ch.channel} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: idx * 0.03 }}
                              className="group transition hover:bg-slate-50/60 dark:hover:bg-slate-700/30">
                              <td className="px-5 py-4">
                                <div className="flex items-center gap-3">
                                  <div className="flex-shrink-0 h-8 w-8 rounded-lg flex items-center justify-center text-[10px] font-bold text-white" style={{ background: ch.color }}>
                                    {ch.label.substring(0, 2).toUpperCase()}
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <span className="text-sm font-medium text-slate-900 dark:text-white">{ch.label}</span>
                                    {isTop && (
                                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-bold bg-violet-100 dark:bg-violet-900/30 text-violet-600 dark:text-violet-400">
                                        <Flame className="w-3 h-3" /> Top
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </td>
                              <td className="px-5 py-4 text-right text-sm font-semibold tabular-nums text-slate-700 dark:text-slate-300">{ch.returns}</td>
                              <td className="px-5 py-4 text-right">
                                <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-bold ${risk.cls}`}>
                                  <span className={`h-1.5 w-1.5 rounded-full ${risk.dot}`} />
                                  {ch.pct.toFixed(1)}%
                                </span>
                              </td>
                              <td className="px-5 py-4 text-right">
                                <p className={`text-sm font-semibold tabular-nums ${rank < 3 ? 'text-violet-600 dark:text-violet-400' : 'text-slate-700 dark:text-slate-300'}`}>{fmtCurr(ch.value)}</p>
                                <div className="mt-1.5 h-1 rounded-full bg-slate-100 dark:bg-slate-700 overflow-hidden">
                                  <div className="h-full rounded-full transition-all duration-500" style={{ width: `${valBarW}%`, background: ch.color }} />
                                </div>
                              </td>
                              <td className="px-5 py-4 text-right text-sm font-semibold tabular-nums text-slate-600 dark:text-slate-400">{ch.valuePct.toFixed(1)}%</td>
                              <td className="px-5 py-4 text-right text-sm tabular-nums text-violet-500 dark:text-violet-400 font-medium">{ch.rto}</td>
                              <td className="px-5 py-4 text-right text-sm tabular-nums text-rose-500 dark:text-rose-400 font-medium">{ch.cir}</td>
                            </motion.tr>
                          );
                        })}
                      </tbody>
                      <tfoot>
                        <tr className="bg-slate-50 dark:bg-slate-900/60 border-t-2 border-slate-200 dark:border-slate-600">
                          <td className="px-5 py-4 text-sm font-bold text-slate-900 dark:text-white">Total</td>
                          <td className="px-5 py-4 text-right text-sm font-bold tabular-nums text-slate-900 dark:text-white">{totals.total_returns}</td>
                          <td className="px-5 py-4 text-right text-sm font-bold tabular-nums text-slate-900 dark:text-white">100%</td>
                          <td className="px-5 py-4 text-right text-sm font-bold tabular-nums text-violet-600 dark:text-violet-400">{fmtCurr(totals.total_value)}</td>
                          <td className="px-5 py-4 text-right text-sm font-bold tabular-nums text-slate-900 dark:text-white">100%</td>
                          <td className="px-5 py-4 text-right text-sm font-bold tabular-nums text-violet-500 dark:text-violet-400">{totals.rto_count}</td>
                          <td className="px-5 py-4 text-right text-sm font-bold tabular-nums text-rose-500 dark:text-rose-400">{totals.cir_count}</td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                </div>

                {/* SKU Table */}
                {skus.length > 0 && (
                  <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
                    <div className="p-4 border-b border-slate-100 dark:border-slate-700 flex flex-wrap items-center justify-between gap-3">
                      <h2 className="text-base font-semibold text-slate-900 dark:text-white">SKU-wise Returns</h2>
                      <div className="relative w-full sm:w-56">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                        <input value={skuSearch} onChange={(e) => setSkuSearch(e.target.value)}
                          placeholder="Search SKU or name…"
                          className="w-full pl-9 pr-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-sm text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-violet-500" />
                      </div>
                    </div>
                    <div className="table-scroll-wrap">
                      <table className="w-full">
                        <thead>
                          <tr className="bg-slate-50/80 dark:bg-slate-900/50 sticky top-0 z-10">
                            <th className="px-5 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 w-12">#</th>
                            {([
                              { key: 'sku' as SkuSortKey, label: 'SKU', align: 'left' },
                              { key: 'name' as SkuSortKey, label: 'Product', align: 'left' },
                              { key: 'quantity' as SkuSortKey, label: 'Qty', align: 'right' },
                              { key: 'value' as SkuSortKey, label: 'Value', align: 'right' },
                              { key: 'return_count' as SkuSortKey, label: 'Returns', align: 'right' },
                            ] as const).map((col) => (
                              <th key={col.key} onClick={() => toggleSkuSort(col.key)}
                                className={`px-5 py-3 text-[11px] font-semibold uppercase tracking-wider cursor-pointer select-none transition hover:text-slate-900 dark:hover:text-white ${col.align === 'left' ? 'text-left' : 'text-right'} text-slate-500 dark:text-slate-400`}>
                                <span className="inline-flex items-center gap-1">{col.label} <SortIcn active={skuSort === col.key} dir={skuDir} /></span>
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-slate-700/60">
                          {paginatedSkus.map((s: any, idx: number) => {
                            const rank = (skuPage - 1) * SKU_ROWS_PER_PAGE + idx + 1;
                            const isTop = rank === 1 && !skuSearch;
                            return (
                              <motion.tr key={s.sku} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: idx * 0.02 }}
                                className="group transition hover:bg-slate-50/60 dark:hover:bg-slate-700/30">
                                <td className="px-5 py-3.5 text-xs font-bold text-slate-400 dark:text-slate-500">{rank}</td>
                                <td className="px-5 py-3.5">
                                  <div className="flex items-center gap-2">
                                    <span className="text-sm font-mono font-medium text-slate-900 dark:text-white">{s.sku}</span>
                                    {isTop && (
                                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-bold bg-violet-100 dark:bg-violet-900/30 text-violet-600 dark:text-violet-400">
                                        <Flame className="w-3 h-3" /> #1
                                      </span>
                                    )}
                                  </div>
                                </td>
                                <td className="px-5 py-3.5 text-sm text-slate-500 dark:text-slate-400 max-w-[220px] truncate">{s.name}</td>
                                <td className="px-5 py-3.5 text-right text-sm tabular-nums text-slate-700 dark:text-slate-300 font-medium">{s.quantity}</td>
                                <td className="px-5 py-3.5 text-right">
                                  <p className="text-sm font-semibold tabular-nums text-violet-600 dark:text-violet-400">{fmtCurr(s.value)}</p>
                                  <div className="mt-1 h-1 rounded-full bg-slate-100 dark:bg-slate-700 overflow-hidden">
                                    <div className="h-full rounded-full bg-violet-500 transition-all duration-500" style={{ width: `${s.barW}%` }} />
                                  </div>
                                </td>
                                <td className="px-5 py-3.5 text-right text-sm tabular-nums text-slate-600 dark:text-slate-400">{s.return_count}</td>
                              </motion.tr>
                            );
                          })}
                          {paginatedSkus.length === 0 && (
                            <tr>
                              <td colSpan={6} className="px-5 py-8 text-center text-sm text-slate-400">
                                {skuSearch ? 'No SKU matches your search' : 'No SKU data available'}
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                    {filteredSkus.length > 0 && (
                      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 px-5 py-3 border-t border-slate-100 dark:border-slate-700">
                        <p className="text-xs text-slate-500 dark:text-slate-400">
                          Showing {((skuPage - 1) * SKU_ROWS_PER_PAGE) + 1}-{Math.min(skuPage * SKU_ROWS_PER_PAGE, filteredSkus.length)} of {filteredSkus.length}
                        </p>
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <button
                            onClick={() => setSkuPage(1)}
                            disabled={skuPage === 1}
                            className="px-2 py-1 rounded-md text-xs font-medium text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
                          >
                            First
                          </button>
                          <button
                            onClick={() => setSkuPage((p) => Math.max(1, p - 1))}
                            disabled={skuPage === 1}
                            className="px-2 py-1 rounded-md text-xs font-medium text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
                          >
                            Prev
                          </button>
                          <span className="px-2 py-1 text-xs font-medium text-slate-600 dark:text-slate-300">
                            {skuPage} / {totalSkuPages}
                          </span>
                          <button
                            onClick={() => setSkuPage((p) => Math.min(totalSkuPages, p + 1))}
                            disabled={skuPage === totalSkuPages}
                            className="px-2 py-1 rounded-md text-xs font-medium text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
                          >
                            Next
                          </button>
                          <button
                            onClick={() => setSkuPage(totalSkuPages)}
                            disabled={skuPage === totalSkuPages}
                            className="px-2 py-1 rounded-md text-xs font-medium text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
                          >
                            Last
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Debug / API info (collapsible) */}
                {raw.search_results && (
                  <details className="rounded-2xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 overflow-hidden group">
                    <summary className="px-5 py-3 text-xs font-semibold text-slate-500 dark:text-slate-400 cursor-pointer select-none flex items-center gap-2 hover:text-slate-700 dark:hover:text-slate-300">
                      <ChevronDown className="w-3.5 h-3.5 transition-transform group-open:rotate-180" /> API Debug Info
                    </summary>
                    <div className="px-5 pb-4 space-y-3">
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                        {Object.entries(raw.search_results).map(([type, count]: [string, any]) => (
                          <div key={type} className="flex justify-between bg-white dark:bg-slate-700 p-2 rounded-lg">
                            <span className="text-slate-500 dark:text-slate-400">{type} found:</span>
                            <span className="font-semibold text-slate-900 dark:text-white">{count}</span>
                          </div>
                        ))}
                      </div>
                      {raw.debug_info?.total_failed_rto > 0 && (
                        <div className="bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 p-3 rounded-lg text-xs text-rose-700 dark:text-rose-300">
                          {raw.debug_info.total_failed_rto} RTOs failed to fetch details
                        </div>
                      )}
                      {raw.debug_info?.total_failed_cir > 0 && (
                        <div className="bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-800 p-3 rounded-lg text-xs text-indigo-700 dark:text-indigo-300">
                          {raw.debug_info.total_failed_cir} CIRs failed to fetch details
                        </div>
                      )}
                    </div>
                  </details>
                )}

                {/* Footer */}
                <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px] text-slate-400 dark:text-slate-500 px-1">
                  <span>Source: Export Job API (Tally Return GST Report 3.0)</span>
                  <span>Scope: All Returns (RTO + CIR)</span>
                </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
