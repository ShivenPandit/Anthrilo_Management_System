'use client';

import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { motion } from 'framer-motion';
import { FileBarChart, AlertCircle, BarChart3, Search } from 'lucide-react';
import SalesActivitySelector, { type DateRangeMode, type ReportType } from '@/components/reports/SalesActivitySelector';
import SizeWiseReportTable, { type SalesActivityRow } from '@/components/reports/SizeWiseReportTable';
import ItemWiseReportTable from '@/components/reports/ItemWiseReportTable';
import ChannelWiseReportTable from '@/components/reports/ChannelWiseReportTable';
import ChannelSummaryTable from '@/components/reports/ChannelSummaryTable';
import { unicommerceApi } from '@/features/sales/api';
import { resolveReportDateRange } from '@/lib/report-date-range';
import { generateSalesActivityExcel } from '@/utils/exportSalesActivityExcel';

function formatDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export default function SalesActivityPage() {
  const today = formatDate(new Date());
  const [dateMode, setDateMode] = useState<DateRangeMode>('daily');
  const [anchorDate, setAnchorDate] = useState(today);
  const [fromDate, setFromDate] = useState(today);
  const [toDate, setToDate] = useState(today);
  const [reportType, setReportType] = useState<ReportType>('size-wise');
  const [data, setData] = useState<SalesActivityRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [progress, setProgress] = useState(0);
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const resetRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Simulated progress: ramps up fast then slows, caps at 92%
  useEffect(() => {
    if (resetRef.current) {
      clearTimeout(resetRef.current);
      resetRef.current = null;
    }

    if (loading) {
      setProgress(0);
      let p = 0;
      progressRef.current = setInterval(() => {
        // Fast at first, slower as it approaches ~92%
        const increment = p < 30 ? 3 : p < 60 ? 1.5 : p < 80 ? 0.6 : 0.2;
        p = Math.min(p + increment, 92);
        setProgress(p);
      }, 400);
    } else {
      if (progressRef.current) clearInterval(progressRef.current);
      setProgress((prev) => {
        if (prev <= 0) return prev;
        resetRef.current = setTimeout(() => setProgress(0), 600);
        return 100;
      });
    }
    return () => {
      if (progressRef.current) clearInterval(progressRef.current);
      if (resetRef.current) clearTimeout(resetRef.current);
    };
  }, [loading]);

  const PROGRESS_STAGES = [
    { at: 0, label: 'Initializing export job…' },
    { at: 15, label: 'Fetching orders from Unicommerce…' },
    { at: 45, label: 'Parsing order data…' },
    { at: 65, label: 'Fetching inventory snapshot…' },
    { at: 82, label: 'Building report…' },
    { at: 95, label: 'Finalizing…' },
  ];
  const progressLabel = PROGRESS_STAGES.slice().reverse().find(s => progress >= s.at)?.label ?? '';

  const effectiveRange = useMemo(() => {
    const resolved = resolveReportDateRange({
      mode: dateMode,
      anchorDate: anchorDate || today,
      fromDate,
      toDate,
    });
    return {
      from: resolved.fromDate,
      to: resolved.toDate,
      label: resolved.label,
    };
  }, [dateMode, anchorDate, fromDate, toDate, today]);

  const handleGenerate = useCallback(async () => {
    if (!effectiveRange.from || !effectiveRange.to) return;
    setLoading(true);
    setError(null);
    setData([]);
    try {
      const res = await unicommerceApi.getSalesActivity({
        from_date: effectiveRange.from,
        to_date: effectiveRange.to,
      });
      const items: SalesActivityRow[] = res.data?.items ?? [];
      if (items.length === 0) {
        setError('No data found for the selected date range.');
      }
      setData(items);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Failed to fetch sales activity data.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [effectiveRange.from, effectiveRange.to]);

  const handleExport = useCallback(async () => {
    if (data.length === 0) return;
    try {
      await generateSalesActivityExcel(data, effectiveRange.from, effectiveRange.to, reportType);
    } catch {
      setError('Failed to generate Excel file.');
    }
  }, [data, effectiveRange.from, effectiveRange.to, reportType]);

  const filteredData = useMemo(() => data.filter(row => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      row.item_sku_code.toLowerCase().includes(q) ||
      row.item_type_name.toLowerCase().includes(q) ||
      row.size.toLowerCase().includes(q) ||
      row.channel.toLowerCase().includes(q)
    );
  }), [data, search]);

  const renderTable = () => {
    if (filteredData.length === 0) return null;
    switch (reportType) {
      case 'size-wise':
        return <SizeWiseReportTable data={filteredData} />;
      case 'item-wise':
        return <ItemWiseReportTable data={filteredData} />;
      case 'channel-detailed':
        return <ChannelWiseReportTable data={filteredData} />;
      case 'channel-summary':
        return <ChannelSummaryTable data={filteredData} />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-1">
          <div className="p-2 rounded-xl bg-primary-50 dark:bg-primary-950/40">
            <FileBarChart className="w-5 h-5 text-primary-600 dark:text-primary-400" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Sales Activity</h1>
        </div>
        <p className="text-sm text-slate-500 dark:text-slate-400 ml-12">
          SKU movement, stock activity &amp; channel-wise breakdowns
        </p>
      </div>

      {/* Selector */}
      <SalesActivitySelector
        dateMode={dateMode}
        anchorDate={anchorDate}
        fromDate={fromDate}
        toDate={toDate}
        rangeLabel={effectiveRange.label}
        reportType={reportType}
        loading={loading}
        onDateModeChange={setDateMode}
        onAnchorDateChange={setAnchorDate}
        onFromDateChange={setFromDate}
        onToDateChange={setToDate}
        onReportTypeChange={setReportType}
        onGenerate={handleGenerate}
        onExport={handleExport}
        hasData={data.length > 0}
      />

      {/* Error */}
      {error && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-3 p-4 rounded-xl border border-amber-200 dark:border-amber-800/50
            bg-amber-50/80 dark:bg-amber-950/30 text-amber-700 dark:text-amber-300 text-sm"
        >
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
        </motion.div>
      )}

      {/* Loading with progress */}
      {loading && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="card space-y-4"
        >
          {/* Progress header */}
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
              {progressLabel}
            </span>
            <span className="text-sm font-bold text-primary-600 dark:text-primary-400 tabular-nums">
              {Math.round(progress)}%
            </span>
          </div>

          {/* Progress bar */}
          <div className="h-2.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-primary-500 to-primary-600"
              initial={{ width: 0 }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.4, ease: 'easeOut' }}
            />
          </div>

          {/* Skeleton rows */}
          <div className="space-y-2 pt-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-9 bg-slate-100 dark:bg-slate-800 rounded animate-pulse"
                style={{ opacity: 1 - i * 0.12 }} />
            ))}
          </div>
        </motion.div>
      )}

      {/* Report table */}
      {!loading && data.length > 0 && (
        <>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search by SKU, item name, size or channel…"
              className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/40 focus:border-primary-400 transition"
            />
          </div>
          {filteredData.length === 0 ? (
            <div className="card py-10 text-center text-sm text-slate-500 dark:text-slate-400">
              No rows match &ldquo;{search}&rdquo;
            </div>
          ) : (
            renderTable()
          )}
        </>
      )}

      {/* Empty state */}
      {!loading && !error && data.length === 0 && (
        <div className="card flex flex-col items-center justify-center py-16 text-center">
          <div className="p-4 rounded-2xl bg-slate-100 dark:bg-slate-800/60 mb-4">
            <BarChart3 className="w-10 h-10 text-slate-400 dark:text-slate-500" />
          </div>
          <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-300 mb-1">
            No report generated yet
          </h3>
          <p className="text-sm text-slate-500 dark:text-slate-400 max-w-sm">
            Select a date range and click <strong>Generate</strong> to view your sales activity report.
          </p>
        </div>
      )}
    </div>
  );
}
