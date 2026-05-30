'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
    AlertCircle,
    CalendarDays,
    ChevronLeft,
    ChevronRight,
    Download,
    Filter,
    Loader2,
    RefreshCw,
    Sparkles,
} from 'lucide-react';
import { apiClient, getApiOrigin } from '@/lib/api-client';

interface PlanningReportItem {
    style_code: string;
    sku: string;
    name: string;
    type: string;
    lifecycle?: string | null;
    size: string;
    /** Sum of sales_orders.qty for order_date in the selected range (same rules as backend). */
    net_sale_qty: number;
    good_inventory: number;
    average_daily_sales: number;
    season_factor: number;
    style_factor: number;
    adjusted_ads: number;
    lead_time: number;
    buffer: number;
    required_qty: number;
    plan: number;
    percent_available: number;
    status: 'RED' | 'YELLOW' | 'GREEN';
}

interface PlanningReportResponse {
    report_type: string;
    generated_at: string;
    period: {
        start_date: string;
        end_date: string;
        days: number;
    };
    season_filter: string;
    summary: {
        total_skus: number;
        total_net_sale_qty: number;
        total_good_inventory: number;
        total_required_qty: number;
        total_plan_qty: number;
        status_breakdown: {
            RED: number;
            YELLOW: number;
            GREEN: number;
        };
    };
    pagination: {
        page: number;
        page_size: number;
        total_skus: number;
        total_pages: number;
    };
    items: PlanningReportItem[];
}

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
    items: FabricPlanningReportItem[];
}

const PAGE_SIZE = 20;

const badgeClasses: Record<PlanningReportItem['status'], string> = {
    RED: 'bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-300',
    YELLOW: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
    GREEN: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
};

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
const defaultEnd = formatAsLocalDateInput(today);
const startDefault = new Date(today);
startDefault.setDate(startDefault.getDate() - 30);
const defaultStart = formatAsLocalDateInput(startDefault);

export default function GarmentPlanningReportPage() {
    const [startDate, setStartDate] = useState(defaultStart);
    const [endDate, setEndDate] = useState(defaultEnd);
    const [season, setSeason] = useState<'both' | 'summer' | 'winter'>('both');
    const [selectedType, setSelectedType] = useState<string>('all');
    const [typeOptions, setTypeOptions] = useState<string[]>([]);
    const [report, setReport] = useState<PlanningReportResponse | null>(null);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [csvLoading, setCsvLoading] = useState(false);
    const [fabricReport, setFabricReport] = useState<FabricPlanningReportResponse | null>(null);
    const [fabricLoading, setFabricLoading] = useState(false);

    // Fetch type options on mount
    useEffect(() => {
        const fetchTypes = async () => {
            try {
                const { data } = await apiClient.get<{ types: string[] }>('/shopify-master-data/meta/filter-options');
                setTypeOptions(data.types ?? []);
            } catch {
                setTypeOptions([]);
            }
        };
        fetchTypes();
    }, []);

    const loadReport = useCallback(
        async (nextPage: number) => {
            setLoading(true);
            setErrorMessage(null);
            try {
                const params: Record<string, string | number> = {
                    start_date: startDate,
                    end_date: endDate,
                    season,
                    page: nextPage,
                    page_size: PAGE_SIZE,
                };
                // Add type filter if not "all"
                if (selectedType !== 'all') {
                    params.type = selectedType;
                }
                const { data } = await apiClient.get<PlanningReportResponse>('/reports/garments/planning-report', {
                    params,
                });
                setReport(data);
            } catch (error: unknown) {
                setReport(null);
                const err = error as { response?: { data?: { detail?: unknown } } };
                const detail = err?.response?.data?.detail;
                if (typeof detail === 'string') {
                    setErrorMessage(detail);
                } else if (Array.isArray(detail)) {
                    setErrorMessage(
                        detail.map((d: { msg?: string }) => d?.msg).filter(Boolean).join(' ') ||
                            'Failed to generate garment planning report.',
                    );
                } else {
                    setErrorMessage('Failed to generate garment planning report.');
                }
            } finally {
                setLoading(false);
            }
        },
        [startDate, endDate, season, selectedType],
    );

    const handleGenerate = () => {
        void loadReport(1);
        void loadFabricReport(1);
    };

    const loadFabricReport = useCallback(
        async (nextPage: number) => {
            setFabricLoading(true);
            try {
                const { data } = await apiClient.get<FabricPlanningReportResponse>(
                    '/reports/garments/fabric-planning-report',
                    {
                        params: {
                            as_of_date: endDate,
                            page: nextPage,
                            page_size: PAGE_SIZE,
                        },
                    },
                );
                setFabricReport(data);
            } catch {
                setFabricReport(null);
            } finally {
                setFabricLoading(false);
            }
        },
        [endDate],
    );

    const handleDownloadCsv = async () => {
        const params = new URLSearchParams({
            start_date: startDate,
            end_date: endDate,
            season,
        });
        // Add type filter if not "all"
        if (selectedType !== 'all') {
            params.append('type', selectedType);
        }
        const origin = getApiOrigin();
        const url = `${origin}/api/v1/reports/garments/planning-report/export.csv?${params.toString()}`;
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
                    /* ignore */
                }
                throw new Error(msg);
            }
            const blob = await res.blob();
            const cd = res.headers.get('Content-Disposition');
            const match = cd?.match(/filename="([^"]+)"/);
            const filename = match?.[1] ?? `garment-planning_${startDate}_${endDate}.csv`;
            const objectUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = objectUrl;
            a.download = filename;
            a.click();
            URL.revokeObjectURL(objectUrl);
        } catch (e: unknown) {
            const msg = e instanceof Error ? e.message : 'CSV export failed.';
            setErrorMessage(msg);
        } finally {
            setCsvLoading(false);
        }
    };

    const summaryCards = useMemo(() => {
        if (!report) {
            return [
                { label: 'SKUs in range', value: '—' },
                { label: 'Net sale (qty)', value: '—' },
                { label: 'Good inventory', value: '—' },
                { label: 'Required qty', value: '—' },
            ];
        }
        const s = report.summary;
        return [
            { label: 'SKUs in range', value: formatNumber(s.total_skus) },
            { label: 'Net sale (qty)', value: formatNumber(s.total_net_sale_qty) },
            { label: 'Good inventory', value: formatNumber(s.total_good_inventory) },
            { label: 'Required qty', value: formatNumber(s.total_required_qty, 2) },
        ];
    }, [report]);

    const statusCards = useMemo(() => {
        if (!report) {
            return [
                { label: 'RED', value: '—', className: badgeClasses.RED },
                { label: 'YELLOW', value: '—', className: badgeClasses.YELLOW },
                { label: 'GREEN', value: '—', className: badgeClasses.GREEN },
            ];
        }
        const b = report.summary.status_breakdown;
        return [
            { label: 'RED', value: formatNumber(b.RED), className: badgeClasses.RED },
            { label: 'YELLOW', value: formatNumber(b.YELLOW), className: badgeClasses.YELLOW },
            { label: 'GREEN', value: formatNumber(b.GREEN), className: badgeClasses.GREEN },
        ];
    }, [report]);

    const items = report?.items ?? [];
    const pagination = report?.pagination;
    const currentPage = pagination?.page ?? 1;
    const canPrev = !!pagination && pagination.page > 1 && !loading;
    const canNext =
        !!pagination && pagination.total_pages > 0 && pagination.page < pagination.total_pages && !loading;

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Garment Planning Report</h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                    Simple SKUs with net positive{' '}
                    <span className="font-medium text-slate-600 dark:text-slate-300">sales_orders.qty</span> in the
                    selected dates (rows counted only when{' '}
                    <span className="font-medium text-slate-600 dark:text-slate-300">order_date</span> is set and falls
                    in range). Inventory from snapshots; planning fields derive from that sale window.
                </p>
            </div>

            <div className="card space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    <label className="space-y-2 text-sm">
                        <span className="flex items-center gap-2 font-medium text-slate-600 dark:text-slate-300">
                            <CalendarDays className="h-4 w-4" /> Start Date
                        </span>
                        <input
                            type="date"
                            value={startDate}
                            onChange={(e) => setStartDate(e.target.value)}
                            className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
                        />
                    </label>
                    <label className="space-y-2 text-sm">
                        <span className="flex items-center gap-2 font-medium text-slate-600 dark:text-slate-300">
                            <CalendarDays className="h-4 w-4" /> End Date
                        </span>
                        <input
                            type="date"
                            value={endDate}
                            onChange={(e) => setEndDate(e.target.value)}
                            className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
                        />
                    </label>
                    <label className="space-y-2 text-sm">
                        <span className="flex items-center gap-2 font-medium text-slate-600 dark:text-slate-300">
                            <Filter className="h-4 w-4" /> Season
                        </span>
                        <select
                            value={season}
                            onChange={(e) => setSeason(e.target.value as 'both' | 'summer' | 'winter')}
                            className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
                        >
                            <option value="both">Both</option>
                            <option value="summer">Summer</option>
                            <option value="winter">Winter</option>
                        </select>
                    </label>
                    <label className="space-y-2 text-sm">
                        <span className="flex items-center gap-2 font-medium text-slate-600 dark:text-slate-300">
                            <Filter className="h-4 w-4" /> Type
                        </span>
                        <select
                            value={selectedType}
                            onChange={(e) => setSelectedType(e.target.value)}
                            className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
                        >
                            <option value="all">Select All</option>
                            {typeOptions.map((type) => (
                                <option key={type} value={type}>
                                    {type}
                                </option>
                            ))}
                        </select>
                    </label>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                    <button
                        type="button"
                        onClick={handleGenerate}
                        disabled={loading}
                        className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-60"
                    >
                        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                        Generate
                    </button>
                    <button
                        type="button"
                        onClick={() => void handleDownloadCsv()}
                        disabled={csvLoading || loading}
                        className="inline-flex items-center gap-2 rounded-lg border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-60"
                    >
                        {csvLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                        Download CSV
                    </button>
                    <button
                        type="button"
                        onClick={() => {
                            setReport(null);
                            setFabricReport(null);
                            setErrorMessage(null);
                            setStartDate(defaultStart);
                            setEndDate(defaultEnd);
                            setSeason('both');
                            setSelectedType('all');
                        }}
                        className="inline-flex items-center gap-2 rounded-lg border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800"
                    >
                        <RefreshCw className="h-4 w-4" /> Reset
                    </button>
                </div>

                {errorMessage && (
                    <div className="rounded-lg border border-rose-200 dark:border-rose-700 bg-rose-50 dark:bg-rose-900/20 px-3 py-2 text-sm text-rose-700 dark:text-rose-300 flex items-center gap-2">
                        <AlertCircle className="h-4 w-4 shrink-0" /> {errorMessage}
                    </div>
                )}
            </div>

            {report ? (
                <>
                    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                        {summaryCards.map((card) => (
                            <div key={card.label} className="card">
                                <div className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
                                    {card.label}
                                </div>
                                <div className="mt-2 text-3xl font-bold text-slate-900 dark:text-white">{card.value}</div>
                            </div>
                        ))}
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                        {statusCards.map((card) => (
                            <div key={card.label} className="card">
                                <div className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
                                    Status · {card.label}
                                </div>
                                <div className={`mt-2 text-3xl font-bold rounded-lg px-2 py-1 inline-block ${card.className}`}>
                                    {card.value}
                                </div>
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
                                            'TYPE',
                                            'LIFECYCLE',
                                            'Size',
                                            'Net sale (qty)',
                                            'good inventory',
                                            'AVERAGE DAILY SALES',
                                            'Season Factor( WINTER/SUMMER)',
                                            'Style Factor',
                                            'Adjusted ADS',
                                            'LEAD TIME',
                                            'BUFFER',
                                            'Required Qty',
                                            'PLAN',
                                            '% AVAILABLE',
                                            'Status',
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
                                    {items.map((item) => (
                                        <tr
                                            key={item.sku}
                                            className="border-t border-slate-200 dark:border-slate-800 hover:bg-slate-50/60 dark:hover:bg-slate-800/40"
                                        >
                                            <td className="px-4 py-3 whitespace-nowrap">{item.style_code || '-'}</td>
                                            <td className="px-4 py-3 whitespace-nowrap font-mono text-xs">{item.sku}</td>
                                            <td className="px-4 py-3 min-w-[280px]">{item.name || '-'}</td>
                                            <td className="px-4 py-3 whitespace-nowrap">{item.type || '-'}</td>
                                            <td className="px-4 py-3 whitespace-nowrap">{item.lifecycle || '-'}</td>
                                            <td className="px-4 py-3 whitespace-nowrap">{item.size || '-'}</td>
                                            <td className="px-4 py-3 text-right whitespace-nowrap">
                                                {formatNumber(item.net_sale_qty)}
                                            </td>
                                            <td className="px-4 py-3 text-right whitespace-nowrap">
                                                {formatNumber(item.good_inventory)}
                                            </td>
                                            <td className="px-4 py-3 text-right whitespace-nowrap">
                                                {formatNumber(item.average_daily_sales, 2)}
                                            </td>
                                            <td className="px-4 py-3 text-right whitespace-nowrap">
                                                {formatNumber(item.season_factor, 2)}
                                            </td>
                                            <td className="px-4 py-3 text-right whitespace-nowrap">
                                                {formatNumber(item.style_factor, 2)}
                                            </td>
                                            <td className="px-4 py-3 text-right whitespace-nowrap">
                                                {formatNumber(item.adjusted_ads, 2)}
                                            </td>
                                            <td className="px-4 py-3 text-right whitespace-nowrap">
                                                {formatNumber(item.lead_time)}
                                            </td>
                                            <td className="px-4 py-3 text-right whitespace-nowrap">
                                                {formatNumber(item.buffer)}
                                            </td>
                                            <td className="px-4 py-3 text-right whitespace-nowrap">
                                                {formatNumber(item.required_qty, 2)}
                                            </td>
                                            <td className="px-4 py-3 text-right whitespace-nowrap">
                                                {formatNumber(item.plan, 2)}
                                            </td>
                                            <td className="px-4 py-3 text-right whitespace-nowrap">
                                                {formatNumber(item.percent_available, 2)}%
                                            </td>
                                            <td className="px-4 py-3 whitespace-nowrap">
                                                <span
                                                    className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${badgeClasses[item.status]}`}
                                                >
                                                    {item.status}
                                                </span>
                                            </td>
                                        </tr>
                                    ))}
                                    {!items.length && (
                                        <tr>
                                            <td colSpan={18} className="px-4 py-8 text-center text-slate-500 dark:text-slate-400">
                                                No planning rows on this page for the selected filters.
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>

                        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 dark:border-slate-800 px-4 py-3 text-sm text-slate-600 dark:text-slate-300">
                            <div>
                                Page{' '}
                                <span className="font-semibold text-slate-900 dark:text-white">{currentPage}</span>{' '}
                                of{' '}
                                <span className="font-semibold text-slate-900 dark:text-white">
                                    {pagination?.total_pages ?? 0}
                                </span>
                                <span className="text-slate-400 dark:text-slate-500 ml-2">
                                    ({pagination?.total_skus ?? 0} SKUs total, {PAGE_SIZE} per page)
                                </span>
                            </div>
                            <div className="flex gap-2">
                                <button
                                    type="button"
                                    disabled={!canPrev}
                                    onClick={() => void loadReport(currentPage - 1)}
                                    className="inline-flex items-center gap-1 rounded-lg border border-slate-300 dark:border-slate-600 px-3 py-1.5 font-medium hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-40 disabled:pointer-events-none"
                                >
                                    <ChevronLeft className="h-4 w-4" /> Previous
                                </button>
                                <button
                                    type="button"
                                    disabled={!canNext}
                                    onClick={() => void loadReport(currentPage + 1)}
                                    className="inline-flex items-center gap-1 rounded-lg border border-slate-300 dark:border-slate-600 px-3 py-1.5 font-medium hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-40 disabled:pointer-events-none"
                                >
                                    Next <ChevronRight className="h-4 w-4" />
                                </button>
                            </div>
                        </div>
                    </div>

                    <div className="mt-8">
                        <div className="mb-3">
                            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Fabric Planning Report</h2>
                            <p className="text-sm text-slate-500 dark:text-slate-400">
                                Required quantity is sourced from garment planning required qty for the rolling last 30 days.
                                QTY REQUIRED is calculated as (NET WEIGHT x Required QTY) + 25%.
                            </p>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
                            <div className="card">
                                <div className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">SKUs</div>
                                <div className="mt-2 text-3xl font-bold text-slate-900 dark:text-white">
                                    {formatNumber(fabricReport?.summary.total_skus ?? 0)}
                                </div>
                            </div>
                            <div className="card">
                                <div className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
                                    Required Qty (30d)
                                </div>
                                <div className="mt-2 text-3xl font-bold text-slate-900 dark:text-white">
                                    {formatNumber(fabricReport?.summary.total_required_qty ?? 0, 2)}
                                </div>
                            </div>
                            <div className="card">
                                <div className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
                                    Total Qty Required
                                </div>
                                <div className="mt-2 text-3xl font-bold text-slate-900 dark:text-white">
                                    {formatNumber(fabricReport?.summary.total_qty_required ?? 0, 2)}
                                </div>
                            </div>
                        </div>

                        <div className="card p-0 overflow-hidden relative">
                            {fabricLoading && (
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
                                        {(fabricReport?.items ?? []).map((item) => (
                                            <tr
                                                key={`fabric-${item.sku}`}
                                                className="border-t border-slate-200 dark:border-slate-800 hover:bg-slate-50/60 dark:hover:bg-slate-800/40"
                                            >
                                                <td className="px-4 py-3 whitespace-nowrap">{item.style_code || '-'}</td>
                                                <td className="px-4 py-3 whitespace-nowrap font-mono text-xs">{item.sku}</td>
                                                <td className="px-4 py-3 min-w-[280px]">{item.name || '-'}</td>
                                                <td className="px-4 py-3 whitespace-nowrap">{item.size || '-'}</td>
                                                <td className="px-4 py-3 text-right whitespace-nowrap">
                                                    {formatNumber(item.required_qty, 2)}
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap">{item.fabric || '-'}</td>
                                                <td className="px-4 py-3 whitespace-nowrap">{item.print || '-'}</td>
                                                <td className="px-4 py-3 text-right whitespace-nowrap">
                                                    {formatNumber(item.net_weight, 4)}
                                                </td>
                                                <td className="px-4 py-3 text-right whitespace-nowrap">
                                                    {formatNumber(item.qty_required, 2)}
                                                </td>
                                            </tr>
                                        ))}
                                        {!(fabricReport?.items?.length ?? 0) && (
                                            <tr>
                                                <td colSpan={9} className="px-4 py-8 text-center text-slate-500 dark:text-slate-400">
                                                    No fabric planning rows found.
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>

                            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 dark:border-slate-800 px-4 py-3 text-sm text-slate-600 dark:text-slate-300">
                                <div>
                                    Page{' '}
                                    <span className="font-semibold text-slate-900 dark:text-white">
                                        {fabricReport?.pagination.page ?? 1}
                                    </span>{' '}
                                    of{' '}
                                    <span className="font-semibold text-slate-900 dark:text-white">
                                        {fabricReport?.pagination.total_pages ?? 0}
                                    </span>
                                    <span className="text-slate-400 dark:text-slate-500 ml-2">
                                        ({fabricReport?.pagination.total_skus ?? 0} SKUs total, {PAGE_SIZE} per page)
                                    </span>
                                </div>
                                <div className="flex gap-2">
                                    <button
                                        type="button"
                                        disabled={(fabricReport?.pagination.page ?? 1) <= 1 || fabricLoading}
                                        onClick={() => void loadFabricReport((fabricReport?.pagination.page ?? 1) - 1)}
                                        className="inline-flex items-center gap-1 rounded-lg border border-slate-300 dark:border-slate-600 px-3 py-1.5 font-medium hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-40 disabled:pointer-events-none"
                                    >
                                        <ChevronLeft className="h-4 w-4" /> Previous
                                    </button>
                                    <button
                                        type="button"
                                        disabled={
                                            !fabricReport ||
                                            (fabricReport.pagination.page >= fabricReport.pagination.total_pages) ||
                                            fabricLoading
                                        }
                                        onClick={() => void loadFabricReport((fabricReport?.pagination.page ?? 1) + 1)}
                                        className="inline-flex items-center gap-1 rounded-lg border border-slate-300 dark:border-slate-600 px-3 py-1.5 font-medium hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-40 disabled:pointer-events-none"
                                    >
                                        Next <ChevronRight className="h-4 w-4" />
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </>
            ) : loading ? (
                <div className="card flex items-center justify-center gap-2 py-12 text-slate-600 dark:text-slate-300">
                    <Loader2 className="h-5 w-5 animate-spin" />
                    Generating planning report…
                </div>
            ) : (
                <div className="card text-center py-12 text-slate-500 dark:text-slate-400">
                    {errorMessage
                        ? 'Fix the issue above and click Generate, or adjust filters.'
                        : 'Choose dates and season, then click Generate to load the report.'}
                </div>
            )}
        </div>
    );
}
