'use client';

import { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Download, Loader2, RefreshCw, Search } from 'lucide-react';

import { apiClient, getApiOrigin } from '@/lib/api-client';
import { useToast } from '@/shared/components';

type StatusRow = {
    date: string;
    style_code: string;
    sku: string;
    size: string;
    name: string;
    required_qty: number;
    cutting_plan: number;
    cutting: number;
    stitching: number;
    finishing: number;
    scanning: number;
    balance: number;
};

type StatusReportResponse = {
    report_type: string;
    generated_at: string;
    period: {
        start_date: string;
        end_date: string;
    };
    summary: {
        total_rows: number;
        total_required_qty: number;
        total_balance: number;
    };
    items: StatusRow[];
};

const DEFAULT_START_DATE = '2026-04-11';
const DEFAULT_END_DATE = '2026-05-11';
const PAGE_SIZE = 20;

const formatNumber = (value: number, digits = 0) =>
    new Intl.NumberFormat('en-IN', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
    }).format(Number.isFinite(value) ? value : 0);

export default function ProductionPlanningStatusReportPage() {
    const { error: toastError } = useToast();

    const [startDate, setStartDate] = useState(DEFAULT_START_DATE);
    const [endDate, setEndDate] = useState(DEFAULT_END_DATE);
    const [report, setReport] = useState<StatusReportResponse | null>(null);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [csvLoading, setCsvLoading] = useState(false);
    const [currentPage, setCurrentPage] = useState(1);

    const totalRows = report?.items.length ?? 0;
    const totalPages = Math.max(1, Math.ceil(totalRows / PAGE_SIZE));
    const paginatedItems = useMemo(
        () => report?.items.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE) ?? [],
        [report, currentPage],
    );

    const handleGenerate = async () => {
        setLoading(true);
        setErrorMessage(null);
        try {
            const response = await apiClient.get<StatusReportResponse>('/reports/garments/production-planning-status-report', {
                params: {
                    start_date: startDate,
                    end_date: endDate,
                },
            });
            setReport(response.data);
            setCurrentPage(1);
        } catch (err: any) {
            setReport(null);
            const message =
                err?.response?.data?.detail ||
                'Failed to generate production planning status report.';
            setErrorMessage(String(message));
            toastError(String(message));
        } finally {
            setLoading(false);
        }
    };

    const handleDownloadCsv = async () => {
        const params = new URLSearchParams({
            start_date: startDate,
            end_date: endDate,
        });

        const origin = getApiOrigin();
        const url = `${origin}/api/v1/reports/garments/production-planning-status-report/export.csv?${params.toString()}`;
        const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

        setCsvLoading(true);
        setErrorMessage(null);
        try {
            const res = await fetch(url, {
                headers: token ? { Authorization: `Bearer ${token}` } : {},
            });
            if (!res.ok) {
                let msg = 'CSV export failed.';
                try {
                    const j = await res.json();
                    if (typeof j?.detail === 'string') msg = j.detail;
                } catch {
                    // ignore
                }
                throw new Error(msg);
            }

            const blob = await res.blob();
            const cd = res.headers.get('Content-Disposition');
            const match = cd?.match(/filename="([^"]+)"/);
            const filename = match?.[1] || `production-planning-status_${startDate}_${endDate}.csv`;

            const objectUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = objectUrl;
            a.download = filename;
            a.click();
            URL.revokeObjectURL(objectUrl);
        } catch (e: unknown) {
            const msg = e instanceof Error ? e.message : 'CSV export failed.';
            setErrorMessage(msg);
            toastError(msg);
        } finally {
            setCsvLoading(false);
        }
    };

    const handleReset = () => {
        setStartDate(DEFAULT_START_DATE);
        setEndDate(DEFAULT_END_DATE);
        setReport(null);
        setErrorMessage(null);
        setCurrentPage(1);
    };

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Production Planning &amp; Status Report</h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                    Date-wise planning status using production planning raw data, required quantity, and scanning inventory.
                </p>
            </div>

            <div className="card space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                    <div>
                        <label className="mb-1.5 block text-xs font-medium text-slate-500 dark:text-slate-400">Start Date</label>
                        <input
                            type="date"
                            value={startDate}
                            onChange={(e) => setStartDate(e.target.value)}
                            className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
                        />
                    </div>
                    <div>
                        <label className="mb-1.5 block text-xs font-medium text-slate-500 dark:text-slate-400">End Date</label>
                        <input
                            type="date"
                            value={endDate}
                            onChange={(e) => setEndDate(e.target.value)}
                            className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
                        />
                    </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                    <button
                        type="button"
                        onClick={() => void handleGenerate()}
                        disabled={loading}
                        className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-60"
                    >
                        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                        Generate
                    </button>

                    <button
                        type="button"
                        onClick={() => void handleDownloadCsv()}
                        disabled={csvLoading}
                        className="inline-flex items-center gap-2 rounded-lg border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-60"
                    >
                        {csvLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                        Download CSV
                    </button>

                    <button
                        type="button"
                        onClick={handleReset}
                        className="inline-flex items-center gap-2 rounded-lg border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800"
                    >
                        <RefreshCw className="h-4 w-4" />
                        Reset
                    </button>
                </div>

                {errorMessage && (
                    <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/30 dark:text-rose-300">
                        {errorMessage}
                    </div>
                )}
            </div>

            {report && (
                <>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div className="card">
                            <p className="text-xs text-slate-500 dark:text-slate-400">Rows</p>
                            <p className="mt-1 text-xl font-semibold text-slate-900 dark:text-white">{formatNumber(report.summary.total_rows)}</p>
                        </div>
                        <div className="card">
                            <p className="text-xs text-slate-500 dark:text-slate-400">Total Required Qty</p>
                            <p className="mt-1 text-xl font-semibold text-slate-900 dark:text-white">{formatNumber(report.summary.total_required_qty, 2)}</p>
                        </div>
                        <div className="card">
                            <p className="text-xs text-slate-500 dark:text-slate-400">Total Balance</p>
                            <p className="mt-1 text-xl font-semibold text-slate-900 dark:text-white">{formatNumber(report.summary.total_balance, 2)}</p>
                        </div>
                    </div>

                    <div className="card p-0 overflow-hidden">
                        <div className="overflow-x-auto">
                            <table className="min-w-full text-sm">
                                <thead className="bg-slate-50 dark:bg-slate-800/60">
                                    <tr>
                                        {[
                                            'DATE',
                                            'Style_Code',
                                            'SKU',
                                            'Size',
                                            'NAME',
                                            'Required QTY',
                                            'Cutting Plan',
                                            'Cutting',
                                            'stitching',
                                            'finishing',
                                            'scanning',
                                            'BALANCE',
                                        ].map((header) => (
                                            <th
                                                key={header}
                                                className="px-4 py-3 text-left whitespace-nowrap font-semibold text-slate-600 dark:text-slate-300"
                                            >
                                                {header}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {totalRows ? (
                                        paginatedItems.map((row) => (
                                            <tr key={`${row.sku}-${row.date}`} className="border-t border-slate-200 dark:border-slate-800">
                                                <td className="px-4 py-3 whitespace-nowrap">{row.date}</td>
                                                <td className="px-4 py-3 whitespace-nowrap">{row.style_code || '-'}</td>
                                                <td className="px-4 py-3 font-mono text-xs whitespace-nowrap">{row.sku}</td>
                                                <td className="px-4 py-3 whitespace-nowrap">{row.size || '-'}</td>
                                                <td className="px-4 py-3 whitespace-nowrap">{row.name || '-'}</td>
                                                <td className="px-4 py-3 text-right whitespace-nowrap">{formatNumber(row.required_qty, 2)}</td>
                                                <td className="px-4 py-3 text-right whitespace-nowrap">{formatNumber(row.cutting_plan)}</td>
                                                <td className="px-4 py-3 text-right whitespace-nowrap">{formatNumber(row.cutting)}</td>
                                                <td className="px-4 py-3 text-right whitespace-nowrap">{formatNumber(row.stitching)}</td>
                                                <td className="px-4 py-3 text-right whitespace-nowrap">{formatNumber(row.finishing)}</td>
                                                <td className="px-4 py-3 text-right whitespace-nowrap">{formatNumber(row.scanning)}</td>
                                                <td className="px-4 py-3 text-right whitespace-nowrap">{formatNumber(row.balance, 2)}</td>
                                            </tr>
                                        ))
                                    ) : (
                                        <tr>
                                            <td colSpan={12} className="px-4 py-10 text-center text-slate-500">
                                                No rows found for selected date range.
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                        {totalRows > 0 && (
                            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-4 py-3 text-sm dark:border-slate-800">
                                <p className="text-slate-500 dark:text-slate-400">
                                    Showing {(currentPage - 1) * PAGE_SIZE + 1} to {Math.min(currentPage * PAGE_SIZE, totalRows)} of {totalRows}
                                </p>
                                <div className="flex items-center gap-2">
                                    <button
                                        type="button"
                                        onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                                        disabled={currentPage === 1}
                                        className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
                                    >
                                        <ChevronLeft className="h-4 w-4" />
                                        Previous
                                    </button>
                                    <span className="text-slate-600 dark:text-slate-300">
                                        Page {currentPage} of {totalPages}
                                    </span>
                                    <button
                                        type="button"
                                        onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
                                        disabled={currentPage >= totalPages}
                                        className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
                                    >
                                        Next
                                        <ChevronRight className="h-4 w-4" />
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    );
}
