'use client';

import { useCallback, useMemo, useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight, Loader2, Sparkles } from 'lucide-react';
import { apiClient } from '@/lib/api-client';

interface FabricPlanningReportItem {
  style_code: string;
  sku: string;
  name: string;
  size: string;
  required_qty: number;
  fabric: string;
  print: string;
  net_weight: number;
  qty_required: number;
}

interface FabricSummaryItem {
  fabric: string;
  print: string;
  total_qty_required: number;
}

interface FabricPlanningReportResponse {
  report_type: string;
  generated_at: string;
  period: {
    start_date: string;
    end_date: string;
    days: number;
  };
  summary: {
    total_skus: number;
    total_required_qty: number;
    total_qty_required: number;
  };
  pagination: {
    page: number;
    page_size: number;
    total_skus: number;
    total_pages: number;
  };
  fabric_summary: FabricSummaryItem[];
  items: FabricPlanningReportItem[];
}

const PAGE_SIZE = 20;

const formatNumber = (value: number, digits = 0) =>
  new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number.isFinite(value) ? value : 0);

const formatAsLocalDateInput = (value: Date) => {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const today = new Date();
const defaultAsOfDate = formatAsLocalDateInput(today);

const escapeCsvCell = (value: string | number) => {
  const text = String(value ?? '');
  if (text.includes('"') || text.includes(',') || text.includes('\n')) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
};

export default function FabricPlanningPage() {
  const [asOfDate, setAsOfDate] = useState(defaultAsOfDate);
  const [report, setReport] = useState<FabricPlanningReportResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const loadReport = useCallback(
    async (nextPage: number) => {
      setLoading(true);
      try {
        const { data } = await apiClient.get<FabricPlanningReportResponse>(
          '/reports/garments/fabric-planning-report',
          {
            params: {
              as_of_date: asOfDate,
              page: nextPage,
              page_size: PAGE_SIZE,
            },
          },
        );
        setReport(data);
      } finally {
        setLoading(false);
      }
    },
    [asOfDate],
  );

  const summaryCards = useMemo(
    () => [
      { label: 'SKUs', value: formatNumber(report?.summary.total_skus ?? 0) },
      { label: 'Required Qty (30d)', value: formatNumber(report?.summary.total_required_qty ?? 0, 2) },
      { label: 'Total Qty Required', value: formatNumber(report?.summary.total_qty_required ?? 0, 2) },
    ],
    [report],
  );

  const fabricSummaryRows = useMemo(() => {
    // Prefer backend summary if available
    if (report?.fabric_summary && report.fabric_summary.length > 0) {
      return report.fabric_summary;
    }

    // Fallback: calculate from paginated items (limited but better than empty)
    // or from all items if they happened to be fetched.
    // NOTE: Since the backend now provides this, this is just a safety catch.
    const grouped = new Map<string, { fabric: string; print: string; total_qty_required: number }>();
    for (const item of report?.items ?? []) {
      const fabric = item.fabric || '-';
      const print = item.print || '-';
      const key = `${fabric}__${print}`;
      const current = grouped.get(key) ?? { fabric, print, total_qty_required: 0 };
      current.total_qty_required += Number(item.qty_required || 0);
      grouped.set(key, current);
    }
    return Array.from(grouped.values()).sort((a, b) => b.total_qty_required - a.total_qty_required);
  }, [report]);

  const downloadDetailCsv = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiClient.get('/reports/garments/fabric-planning-report/export-csv', {
        params: { as_of_date: asOfDate },
        responseType: 'blob',
      });
      const url = URL.createObjectURL(new Blob([response.data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `fabric-planning_${asOfDate}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Download failed:', error);
      alert('Failed to download CSV.');
    } finally {
      setLoading(false);
    }
  }, [asOfDate]);

  const downloadSummaryCsv = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiClient.get('/reports/garments/fabric-planning-report/summary-csv', {
        params: { as_of_date: asOfDate },
        responseType: 'blob',
      });
      const url = URL.createObjectURL(new Blob([response.data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `fabric-planning-summary_${asOfDate}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Download failed:', error);
      alert('Failed to download summary CSV.');
    } finally {
      setLoading(false);
    }
  }, [asOfDate]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Fabric Planning Report</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Uses last 30 days garment required quantity per SKU. QTY REQUIRED = (NET WEIGHT x Required QTY) + 25%.
        </p>
      </div>

      <div className="card space-y-4">
        <label className="space-y-2 text-sm block max-w-xs">
          <span className="flex items-center gap-2 font-medium text-slate-600 dark:text-slate-300">
            <CalendarDays className="h-4 w-4" /> As Of Date
          </span>
          <input
            type="date"
            value={asOfDate}
            onChange={(e) => setAsOfDate(e.target.value)}
            className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
          />
        </label>

        <button
          type="button"
          onClick={() => void loadReport(1)}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-60"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          Generate
        </button>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={downloadDetailCsv}
            disabled={!report?.items?.length}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
          >
            Download Fabric Planning CSV
          </button>
          <button
            type="button"
            onClick={downloadSummaryCsv}
            disabled={!fabricSummaryRows.length}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
          >
            Download Summary CSV
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {summaryCards.map((card) => (
          <div key={card.label} className="card">
            <div className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">{card.label}</div>
            <div className="mt-2 text-3xl font-bold text-slate-900 dark:text-white">{card.value}</div>
          </div>
        ))}
      </div>

      <div className="card p-0 overflow-hidden relative">
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/70 dark:bg-slate-900/70">
            <Loader2 className="h-8 w-8 animate-spin text-primary-600" />
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800/60">
              <tr>
                {[
                  'STYLE CODE',
                  'SKU',
                  'NAME',
                  'Size',
                  'Required QTY',
                  'FABRIC',
                  'PRINT',
                  'NET WEIGHT',
                  'QTY REQUIRED',
                ].map((column) => (
                  <th
                    key={column}
                    className="px-4 py-3 text-left whitespace-nowrap font-semibold text-slate-600 dark:text-slate-300"
                  >
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(report?.items ?? []).map((item) => (
                <tr
                  key={item.sku}
                  className="border-t border-slate-200 dark:border-slate-800 hover:bg-slate-50/60 dark:hover:bg-slate-800/40"
                >
                  <td className="px-4 py-3 whitespace-nowrap">{item.style_code || '-'}</td>
                  <td className="px-4 py-3 whitespace-nowrap font-mono text-xs">{item.sku}</td>
                  <td className="px-4 py-3 min-w-[280px]">{item.name || '-'}</td>
                  <td className="px-4 py-3 whitespace-nowrap">{item.size || '-'}</td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">{formatNumber(item.required_qty, 2)}</td>
                  <td className="px-4 py-3 whitespace-nowrap">{item.fabric || '-'}</td>
                  <td className="px-4 py-3 whitespace-nowrap">{item.print || '-'}</td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">{formatNumber(item.net_weight, 4)}</td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">{formatNumber(item.qty_required, 2)}</td>
                </tr>
              ))}
              {!(report?.items?.length ?? 0) && (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-slate-500 dark:text-slate-400">
                    {report ? 'No planning data found for the selected date.' : 'Click Generate to load fabric planning rows.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 dark:border-slate-800 px-4 py-3 text-sm text-slate-600 dark:text-slate-300">
          <div>
            Page <span className="font-semibold text-slate-900 dark:text-white">{report?.pagination.page ?? 1}</span> of{' '}
            <span className="font-semibold text-slate-900 dark:text-white">{report?.pagination.total_pages ?? 0}</span>
            <span className="text-slate-400 dark:text-slate-500 ml-2">
              ({report?.pagination.total_skus ?? 0} SKUs total, {PAGE_SIZE} per page)
            </span>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={(report?.pagination.page ?? 1) <= 1 || loading}
              onClick={() => void loadReport((report?.pagination.page ?? 1) - 1)}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-300 dark:border-slate-600 px-3 py-1.5 font-medium hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-40 disabled:pointer-events-none"
            >
              <ChevronLeft className="h-4 w-4" /> Previous
            </button>
            <button
              type="button"
              disabled={!report || report.pagination.page >= report.pagination.total_pages || loading}
              onClick={() => void loadReport((report?.pagination.page ?? 1) + 1)}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-300 dark:border-slate-600 px-3 py-1.5 font-medium hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-40 disabled:pointer-events-none"
            >
              Next <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      <div>
        <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-3">Fabric Planning Report Summary</h2>
        <div className="card p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 dark:bg-slate-800/60">
                <tr>
                  {['FABRIC', 'PRINT', 'TOTAL QTY REQUIRED'].map((column) => (
                    <th
                      key={column}
                      className="px-4 py-3 text-left whitespace-nowrap font-semibold text-slate-600 dark:text-slate-300"
                    >
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {fabricSummaryRows.map((row) => (
                  <tr
                    key={`${row.fabric}-${row.print}`}
                    className="border-t border-slate-200 dark:border-slate-800 hover:bg-slate-50/60 dark:hover:bg-slate-800/40"
                  >
                    <td className="px-4 py-3 whitespace-nowrap">{row.fabric}</td>
                    <td className="px-4 py-3 whitespace-nowrap">{row.print}</td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">{formatNumber(row.total_qty_required, 2)}</td>
                  </tr>
                ))}
                {!fabricSummaryRows.length && (
                  <tr>
                    <td colSpan={3} className="px-4 py-8 text-center text-slate-500 dark:text-slate-400">
                      {report ? 'No summary data found for the selected date.' : 'Click Generate to load fabric planning summary.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
