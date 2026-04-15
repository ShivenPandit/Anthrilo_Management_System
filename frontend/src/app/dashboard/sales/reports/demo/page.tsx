'use client';

import { useMemo, useState, useCallback } from 'react';
import { Calendar, Search, FileBarChart } from 'lucide-react';
import DemoReportTable from '@/components/reports/DemoReportTable';
import { unicommerceApi } from '@/features/sales/api';
import { resolveReportDateRange } from '@/lib/report-date-range';

export default function DemoSalesReportPage() {
    const today = new Date().toISOString().split('T')[0];

    const [dateMode, setDateMode] = useState<'daily' | 'weekly' | 'monthly' | 'custom'>('daily');
    const [anchorDate, setAnchorDate] = useState(today);
    const [fromDate, setFromDate] = useState(today);
    const [toDate, setToDate] = useState(today);
    const [channelFilter, setChannelFilter] = useState('ALL');
    const [search, setSearch] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [data, setData] = useState<any[]>([]);

    const effectiveRange = useMemo(() => {
        return resolveReportDateRange({
            mode: dateMode,
            anchorDate,
            fromDate,
            toDate,
        });
    }, [dateMode, anchorDate, fromDate, toDate]);

    const channels = useMemo(() => {
        const set = new Set<string>();
        for (const row of data) {
            const channel = String(row.channel || '').trim();
            if (channel) set.add(channel);
        }
        return ['ALL', ...Array.from(set).sort((a, b) => a.localeCompare(b))];
    }, [data]);

    const filteredData = useMemo(() => {
        return data.filter((row) => {
            if (channelFilter !== 'ALL' && row.channel !== channelFilter) return false;
            if (!search.trim()) return true;

            const q = search.toLowerCase();
            return (
                String(row.item_sku_code || '').toLowerCase().includes(q) ||
                String(row.item_type_name || '').toLowerCase().includes(q) ||
                String(row.item_type_size || row.size || '').toLowerCase().includes(q) ||
                String(row.channel || '').toLowerCase().includes(q)
            );
        });
    }, [data, search, channelFilter]);

    const handleGenerate = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await unicommerceApi.getSalesActivity({
                from_date: effectiveRange.fromDate,
                to_date: effectiveRange.toDate,
            });
            setData(res.data?.items || []);
            setChannelFilter('ALL');
        } catch (err: any) {
            const msg = err?.response?.data?.detail || err?.message || 'Failed to fetch demo report data';
            setError(msg);
        } finally {
            setLoading(false);
        }
    }, [effectiveRange.fromDate, effectiveRange.toDate]);

    return (
        <div className="space-y-6">
            <div>
                <div className="flex items-center gap-3 mb-1">
                    <div className="p-2 rounded-xl bg-primary-50 dark:bg-primary-950/40">
                        <FileBarChart className="w-5 h-5 text-primary-600 dark:text-primary-400" />
                    </div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Demo Report</h1>
                </div>
                <p className="text-sm text-slate-500 dark:text-slate-400 ml-12">
                    Item Type Size based report with size-wise sale, return, cancelled, net and current inventory snapshot.
                </p>
            </div>

            <div className="card space-y-4">
                <div>
                    <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">Date Range Mode</label>
                    <div className="inline-flex rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden bg-slate-50 dark:bg-slate-900">
                        {(['daily', 'weekly', 'monthly', 'custom'] as const).map((mode) => (
                            <button
                                key={mode}
                                type="button"
                                onClick={() => setDateMode(mode)}
                                className={`px-3 py-2 text-xs font-medium transition-colors ${dateMode === mode
                                        ? 'bg-primary-600 text-white'
                                        : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
                                    }`}
                            >
                                {mode[0].toUpperCase() + mode.slice(1)}
                            </button>
                        ))}
                    </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-4 gap-3">
                    {dateMode === 'daily' && (
                        <div>
                            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">Reference Date</label>
                            <div className="relative">
                                <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                <input
                                    type="date"
                                    value={anchorDate}
                                    onChange={(e) => setAnchorDate(e.target.value)}
                                    className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm"
                                />
                            </div>
                        </div>
                    )}

                    {dateMode === 'custom' && (
                        <>
                            <div>
                                <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">From Date</label>
                                <input
                                    type="date"
                                    value={fromDate}
                                    onChange={(e) => setFromDate(e.target.value)}
                                    className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm"
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">To Date</label>
                                <input
                                    type="date"
                                    value={toDate}
                                    onChange={(e) => setToDate(e.target.value)}
                                    className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm"
                                />
                            </div>
                        </>
                    )}

                    <div className="lg:col-span-2">
                        <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">Effective Range</label>
                        <div className="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-sm text-slate-700 dark:text-slate-300">
                            {effectiveRange.label}
                        </div>
                    </div>
                </div>

                <div className="flex flex-col lg:flex-row gap-3">
                    <div className="relative flex-1">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                        <input
                            type="text"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder="Search by SKU, item name, item type size or channel..."
                            className="w-full pl-10 pr-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm"
                        />
                    </div>

                    <select
                        value={channelFilter}
                        onChange={(e) => setChannelFilter(e.target.value)}
                        className="w-full lg:w-64 px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm"
                    >
                        {channels.map((ch) => (
                            <option key={ch} value={ch}>
                                {ch === 'ALL' ? 'All Channels' : ch}
                            </option>
                        ))}
                    </select>

                    <button
                        onClick={handleGenerate}
                        disabled={loading}
                        className="px-5 py-2 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
                    >
                        {loading ? 'Generating...' : 'Generate'}
                    </button>
                </div>
            </div>

            {error && (
                <div className="card border border-amber-200 dark:border-amber-800/50 bg-amber-50/80 dark:bg-amber-950/30 text-amber-700 dark:text-amber-300 text-sm">
                    {error}
                </div>
            )}

            <div className="card">
                <DemoReportTable data={filteredData} selectedChannel={channelFilter} />
            </div>
        </div>
    );
}
