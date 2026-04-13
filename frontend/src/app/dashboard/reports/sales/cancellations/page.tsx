'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ucSales } from '@/features/sales/api';
import { ProgressLoader } from '@/components/ui/Common';
import { AlertTriangle, BarChart3, Calendar, Download, Loader2, Search } from 'lucide-react';

const PERIOD_OPTIONS = [
    { value: 'daily', label: 'Daily' },
    { value: 'weekly', label: 'Weekly' },
    { value: 'monthly', label: 'Monthly' },
    { value: 'custom', label: 'Custom' },
] as const;

type Period = 'daily' | 'weekly' | 'monthly' | 'custom';

type SortKey = 'channel' | 'cancellations' | 'items' | 'value' | 'cod' | 'prepaid';
type SortDir = 'asc' | 'desc';

const createProgressId = () => {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID();
    }
    return `report-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const fmtCurr = (v: number) =>
    `₹${(v || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function CancellationReportPage() {
    const [period, setPeriod] = useState<Period>('daily');
    const [reportDate, setReportDate] = useState<string>(() => {
        const d = new Date();
        d.setDate(d.getDate() - 1);
        return d.toISOString().split('T')[0];
    });
    const [fromDate, setFromDate] = useState<string>(() => {
        const d = new Date();
        d.setDate(d.getDate() - 7);
        return d.toISOString().split('T')[0];
    });
    const [toDate, setToDate] = useState<string>(() => {
        const d = new Date();
        d.setDate(d.getDate() - 1);
        return d.toISOString().split('T')[0];
    });
    const [showReport, setShowReport] = useState(true);
    const [search, setSearch] = useState('');
    const [sortKey, setSortKey] = useState<SortKey>('value');
    const [sortDir, setSortDir] = useState<SortDir>('desc');
    const [activeProgressId, setActiveProgressId] = useState<string | null>(null);
    const [backendPercent, setBackendPercent] = useState(0);
    const [backendLabel, setBackendLabel] = useState('');

    const canGenerate = period !== 'custom' || (!!fromDate && !!toDate);

    const { data: raw, isLoading, isFetching, isError, error } = useQuery({
        queryKey: ['cancellation-report', period, reportDate, fromDate, toDate, activeProgressId],
        queryFn: async () => {
            const params: any = { period };
            if (period === 'custom') {
                params.from_date = fromDate;
                params.to_date = toDate;
            } else if (period === 'daily' || period === 'weekly' || period === 'monthly') {
                params.date = reportDate;
            }
            params.progress_id = activeProgressId || undefined;
            return (await ucSales.getCancellationReport(params)).data;
        },
        enabled: showReport && canGenerate,
        staleTime: 5 * 60_000,
        retry: false,
    });

    const { data: progressData } = useQuery({
        queryKey: ['cancellation-report-progress', activeProgressId],
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
        if (nextLabel) {
            setBackendLabel(nextLabel);
        }
    }, [progressData]);

    const queryLoading = isLoading || isFetching;

    const channels = useMemo(() => raw?.by_channel || [], [raw]);
    const items = useMemo(() => raw?.items || [], [raw]);

    const sortedChannels = useMemo(() => {
        const q = search.trim().toLowerCase();
        const filtered = q
            ? channels.filter((c: any) => (c.channel || '').toLowerCase().includes(q))
            : channels;

        return [...filtered].sort((a: any, b: any) => {
            const va = a[sortKey];
            const vb = b[sortKey];
            if (typeof va === 'string') {
                return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
            }
            return sortDir === 'asc' ? (va || 0) - (vb || 0) : (vb || 0) - (va || 0);
        });
    }, [channels, search, sortKey, sortDir]);

    const handleSort = (k: SortKey) => {
        if (sortKey === k) {
            setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
        } else {
            setSortKey(k);
            setSortDir('desc');
        }
    };

    const handleGenerate = useCallback(() => {
        setBackendPercent(1);
        setBackendLabel('Starting cancellation report generation…');
        setActiveProgressId(createProgressId());
        setShowReport(true);
    }, []);

    const handleCSV = useCallback(() => {
        if (!items.length) return;

        const hdr = [
            'Sale Order Code',
            'Sale Order Item Code',
            'Channel',
            'Status',
            'Order Date',
            'COD',
            'SKU',
            'Name',
            'Quantity',
            'Selling Price',
            'Line Value',
        ];

        const rows = items.map((it: any) => [
            it.sale_order_code || '',
            it.sale_order_item_code || '',
            it.channel || '',
            it.status || '',
            it.created || '',
            it.cod ? 'COD' : 'PREPAID',
            it.sku || '',
            String(it.name || '').replace(/,/g, ' '),
            String(it.quantity || 0),
            String(it.selling_price || 0),
            String(it.line_value || 0),
        ]);

        const csv = [hdr.join(','), ...rows.map((r: string[]) => r.join(','))].join('\n');
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const from = raw?.from_date || reportDate;
        const to = raw?.to_date || reportDate;
        a.download = from === to ? `cancellation-report-${from}.csv` : `cancellation-report-${from}-to-${to}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }, [items, raw, reportDate]);

    return (
        <div className="page-section-gap">
            <div>
                <h1 className="responsive-title text-slate-900 dark:text-white">Cancellation Report</h1>
                <p className="responsive-subtitle mt-1">Cancelled orders and items by channel, SKU and value</p>
            </div>

            <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm p-4 sm:p-5">
                <div className="flex flex-wrap items-end gap-3">
                    <div className="w-full sm:min-w-[260px]">
                        <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">Range</label>
                        <div className="tab-strip">
                            <div className="tab-strip-inner">
                                {PERIOD_OPTIONS.map((opt) => (
                                    <button
                                        key={opt.value}
                                        onClick={() => { setPeriod(opt.value); setShowReport(false); }}
                                        className={`px-3 py-2 text-xs font-medium rounded-lg whitespace-nowrap transition ${period === opt.value ? 'bg-rose-600 text-white' : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'}`}
                                    >
                                        {opt.label}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>

                    {period === 'daily' && (
                        <div className="w-full sm:min-w-[180px] sm:w-auto">
                            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">Report date</label>
                            <div className="relative">
                                <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                <input
                                    type="date"
                                    value={reportDate}
                                    onChange={(e) => { setReportDate(e.target.value); setShowReport(false); }}
                                    className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-rose-500"
                                />
                            </div>
                        </div>
                    )}

                    {period === 'custom' && (
                        <>
                            <div className="w-full sm:min-w-[170px] sm:w-auto">
                                <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">From</label>
                                <input
                                    type="date"
                                    value={fromDate}
                                    max={toDate || undefined}
                                    onChange={(e) => { setFromDate(e.target.value); setShowReport(false); }}
                                    className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-rose-500"
                                />
                            </div>
                            <div className="w-full sm:min-w-[170px] sm:w-auto">
                                <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">To</label>
                                <input
                                    type="date"
                                    value={toDate}
                                    min={fromDate || undefined}
                                    max={new Date().toISOString().split('T')[0]}
                                    onChange={(e) => { setToDate(e.target.value); setShowReport(false); }}
                                    className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-rose-500"
                                />
                            </div>
                        </>
                    )}

                    <button
                        onClick={handleGenerate}
                        disabled={queryLoading || !canGenerate}
                        className="inline-flex items-center justify-center gap-2 px-5 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-sm font-medium transition disabled:opacity-50 w-full sm:w-auto"
                    >
                        {queryLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <BarChart3 className="w-4 h-4" />}
                        {queryLoading ? 'Generating…' : 'Generate Report'}
                    </button>

                    {showReport && raw?.success && (
                        <button
                            onClick={handleCSV}
                            className="inline-flex items-center justify-center gap-2 px-5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-sm font-medium text-slate-700 dark:text-slate-300 transition w-full sm:w-auto"
                        >
                            <Download className="w-4 h-4" /> Download CSV
                        </button>
                    )}
                </div>
            </div>

            <ProgressLoader
                loading={queryLoading}
                stages={[
                    { at: 0, label: 'Initializing export job…' },
                    { at: 15, label: 'Fetching cancelled orders…' },
                    { at: 45, label: 'Building channel & SKU breakdown…' },
                    { at: 75, label: 'Preparing item-level details…' },
                    { at: 92, label: 'Finalizing cancellation report…' },
                ]}
                progressPercent={Math.max(backendPercent, 0)}
                progressLabel={backendLabel || undefined}
            />

            {showReport && (isError || (raw && !raw.success)) && !queryLoading && (
                <div className="rounded-2xl bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 p-4">
                    <p className="text-sm text-rose-600 dark:text-rose-400">
                        {(raw && (raw.error || raw.message)) || (error as any)?.message || 'Failed to generate report'}
                    </p>
                </div>
            )}

            {showReport && raw?.success && !queryLoading && (
                <>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-4">
                            <p className="text-xs text-slate-500 dark:text-slate-400">Cancelled Orders</p>
                            <p className="text-2xl font-bold text-slate-900 dark:text-white">{raw.totals.total_cancellations?.toLocaleString('en-IN') || 0}</p>
                        </div>
                        <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-4">
                            <p className="text-xs text-slate-500 dark:text-slate-400">Cancelled Items</p>
                            <p className="text-2xl font-bold text-slate-900 dark:text-white">{raw.totals.total_items?.toLocaleString('en-IN') || 0}</p>
                        </div>
                        <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-4">
                            <p className="text-xs text-slate-500 dark:text-slate-400">Cancelled Value</p>
                            <p className="text-2xl font-bold text-slate-900 dark:text-white">{fmtCurr(raw.totals.total_value || 0)}</p>
                        </div>
                        <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-4">
                            <p className="text-xs text-slate-500 dark:text-slate-400">Cancellation Rate</p>
                            <p className="text-2xl font-bold text-rose-600 dark:text-rose-400">{(raw.totals.cancellation_rate || 0).toFixed(2)}%</p>
                        </div>
                    </div>

                    <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
                        <div className="p-4 border-b border-slate-100 dark:border-slate-700 flex items-center justify-between gap-3 flex-wrap">
                            <h2 className="text-base font-semibold text-slate-900 dark:text-white">Channel Breakdown</h2>
                            <div className="relative w-full sm:w-64">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                <input
                                    value={search}
                                    onChange={(e) => setSearch(e.target.value)}
                                    placeholder="Search channel..."
                                    className="w-full pl-9 pr-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-sm text-slate-900 dark:text-white"
                                />
                            </div>
                        </div>
                        <div className="table-scroll-wrap">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="bg-slate-50 dark:bg-slate-900/50">
                                        <th className="px-4 py-2 text-left text-xs font-semibold text-slate-500 cursor-pointer" onClick={() => handleSort('channel')}>Channel</th>
                                        <th className="px-4 py-2 text-right text-xs font-semibold text-slate-500 cursor-pointer" onClick={() => handleSort('cancellations')}>Cancellations</th>
                                        <th className="px-4 py-2 text-right text-xs font-semibold text-slate-500 cursor-pointer" onClick={() => handleSort('items')}>Items</th>
                                        <th className="px-4 py-2 text-right text-xs font-semibold text-slate-500 cursor-pointer" onClick={() => handleSort('value')}>Value</th>
                                        <th className="px-4 py-2 text-right text-xs font-semibold text-slate-500 cursor-pointer" onClick={() => handleSort('cod')}>COD</th>
                                        <th className="px-4 py-2 text-right text-xs font-semibold text-slate-500 cursor-pointer" onClick={() => handleSort('prepaid')}>Prepaid</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                                    {sortedChannels.map((ch: any) => (
                                        <tr key={ch.channel}>
                                            <td className="px-4 py-2 text-slate-800 dark:text-slate-200">{String(ch.channel || '').replace(/_/g, ' ')}</td>
                                            <td className="px-4 py-2 text-right tabular-nums">{ch.cancellations}</td>
                                            <td className="px-4 py-2 text-right tabular-nums">{ch.items}</td>
                                            <td className="px-4 py-2 text-right tabular-nums">{fmtCurr(ch.value || 0)}</td>
                                            <td className="px-4 py-2 text-right tabular-nums">{ch.cod}</td>
                                            <td className="px-4 py-2 text-right tabular-nums">{ch.prepaid}</td>
                                        </tr>
                                    ))}
                                    {sortedChannels.length === 0 && (
                                        <tr>
                                            <td colSpan={6} className="px-4 py-8 text-center text-slate-400">No cancellation data found</td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
                        <div className="p-4 border-b border-slate-100 dark:border-slate-700">
                            <h2 className="text-base font-semibold text-slate-900 dark:text-white">Cancelled Item Details</h2>
                        </div>
                        <div className="table-scroll-wrap max-h-[520px]">
                            <table className="w-full text-sm">
                                <thead className="sticky top-0 bg-slate-50 dark:bg-slate-900/70">
                                    <tr>
                                        <th className="px-4 py-2 text-left text-xs font-semibold text-slate-500">Sale Order Code</th>
                                        <th className="px-4 py-2 text-left text-xs font-semibold text-slate-500">Sale Order Item Code</th>
                                        <th className="px-4 py-2 text-left text-xs font-semibold text-slate-500">Channel</th>
                                        <th className="px-4 py-2 text-left text-xs font-semibold text-slate-500">SKU</th>
                                        <th className="px-4 py-2 text-left text-xs font-semibold text-slate-500">Name</th>
                                        <th className="px-4 py-2 text-right text-xs font-semibold text-slate-500">Qty</th>
                                        <th className="px-4 py-2 text-right text-xs font-semibold text-slate-500">Selling Price</th>
                                        <th className="px-4 py-2 text-right text-xs font-semibold text-slate-500">Line Value</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                                    {items.slice(0, 500).map((it: any, idx: number) => (
                                        <tr key={`${it.sale_order_item_code || it.sale_order_code}-${idx}`}>
                                            <td className="px-4 py-2 font-mono text-xs">{it.sale_order_code}</td>
                                            <td className="px-4 py-2 font-mono text-xs">{it.sale_order_item_code || '—'}</td>
                                            <td className="px-4 py-2">{String(it.channel || '').replace(/_/g, ' ')}</td>
                                            <td className="px-4 py-2 font-mono text-xs">{it.sku}</td>
                                            <td className="px-4 py-2 max-w-[340px] truncate">{it.name}</td>
                                            <td className="px-4 py-2 text-right tabular-nums">{it.quantity}</td>
                                            <td className="px-4 py-2 text-right tabular-nums">{fmtCurr(it.selling_price || 0)}</td>
                                            <td className="px-4 py-2 text-right tabular-nums">{fmtCurr(it.line_value || 0)}</td>
                                        </tr>
                                    ))}
                                    {!items.length && (
                                        <tr>
                                            <td colSpan={8} className="px-4 py-8 text-center text-slate-400">No cancelled items found</td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                        {items.length > 500 && (
                            <p className="px-4 py-2 text-xs text-slate-400 border-t border-slate-100 dark:border-slate-700">
                                Showing first 500 rows in UI for performance. Use CSV to download full data.
                            </p>
                        )}
                    </div>

                    <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        <span>Period: {raw.from_date} to {raw.to_date} | Source: {raw.search_results?.method || 'export'}</span>
                    </div>
                </>
            )}
        </div>
    );
}
