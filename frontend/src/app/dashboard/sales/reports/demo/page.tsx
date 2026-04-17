'use client';

import { useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { Calendar, Search, FileBarChart } from 'lucide-react';
import DemoReportTable from '@/components/reports/DemoReportTable';
import { ProgressLoader } from '@/components/ui/Common';
import { unicommerceApi } from '@/features/sales/api';
import type { SalesActivityRow } from '@/components/reports/SizeWiseReportTable';

type DateMode = 'daily' | 'weekly' | 'monthly' | 'custom';

const toYmd = (date: Date): string => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
};

const parseYmd = (value: string): Date => {
    const parsed = new Date(`${value}T00:00:00`);
    return Number.isNaN(parsed.getTime()) ? new Date() : parsed;
};

const createProgressId = (): string => {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID();
    }
    return `sales-activity-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const deriveStyle = (itemTypeName: string, itemTypeSize: string): string => {
    const name = (itemTypeName || '').trim();
    const size = (itemTypeSize || '').trim();
    if (!name) return 'UNKNOWN';

    if (size && size.toUpperCase() !== 'UNKNOWN') {
        const suffix = ` - ${size}`;
        if (name.endsWith(suffix)) {
            const style = name.slice(0, -suffix.length).trim();
            if (style) return style;
        }
    }

    const idx = name.lastIndexOf(' - ');
    if (idx > 0) {
        const style = name.slice(0, idx).trim();
        return style || name;
    }

    return name;
};

export default function DemoSalesReportPage() {
    const today = new Date().toISOString().split('T')[0];

    const [dateMode, setDateMode] = useState<DateMode>('daily');
    const [anchorDate, setAnchorDate] = useState(today);
    const [fromDate, setFromDate] = useState(today);
    const [toDate, setToDate] = useState(today);
    const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
    const [channelMenuOpen, setChannelMenuOpen] = useState(false);
    const [search, setSearch] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [data, setData] = useState<SalesActivityRow[]>([]);
    const [activeProgressId, setActiveProgressId] = useState<string | null>(null);
    const [backendPercent, setBackendPercent] = useState(0);
    const [backendLabel, setBackendLabel] = useState('');
    const channelMenuRef = useRef<HTMLDivElement | null>(null);

    const progressStages = useMemo(() => ([
        { at: 5, label: 'Validating sales activity date range…' },
        { at: 18, label: 'Fetching sales rows for selected range…' },
        { at: 40, label: 'Aggregating SKU, channel and size rows…' },
        { at: 58, label: 'Reconciling return quantities…' },
        { at: 80, label: 'Loading current inventory snapshot…' },
        { at: 92, label: 'Preparing final rows and totals…' },
        { at: 98, label: 'Finalizing sales activity response…' },
    ]), []);

    useEffect(() => {
        if (!channelMenuOpen) return;

        const handleClickOutside = (event: MouseEvent) => {
            if (!channelMenuRef.current) return;
            if (!channelMenuRef.current.contains(event.target as Node)) {
                setChannelMenuOpen(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [channelMenuOpen]);

    const effectiveRange = useMemo(() => {
        const anchor = parseYmd(anchorDate);

        if (dateMode === 'daily') {
            const date = toYmd(anchor);
            return {
                fromDate: date,
                toDate: date,
                label: `Date: ${date}`,
            };
        }

        if (dateMode === 'weekly') {
            const mondayOffset = (anchor.getDay() + 6) % 7;
            const weekStart = new Date(anchor);
            weekStart.setDate(anchor.getDate() - mondayOffset);
            const weekEnd = new Date(weekStart);
            weekEnd.setDate(weekStart.getDate() + 6);

            const start = toYmd(weekStart);
            const end = toYmd(weekEnd);
            return {
                fromDate: start,
                toDate: end,
                label: `Week: ${start} to ${end}`,
            };
        }

        if (dateMode === 'monthly') {
            const monthStart = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
            const monthEnd = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);

            const start = toYmd(monthStart);
            const end = toYmd(monthEnd);
            return {
                fromDate: start,
                toDate: end,
                label: `Month: ${start} to ${end}`,
            };
        }

        const customStart = parseYmd(fromDate);
        const customEnd = parseYmd(toDate);
        const start = customStart <= customEnd ? toYmd(customStart) : toYmd(customEnd);
        const end = customStart <= customEnd ? toYmd(customEnd) : toYmd(customStart);
        return {
            fromDate: start,
            toDate: end,
            label: `Custom: ${start} to ${end}`,
        };
    }, [dateMode, anchorDate, fromDate, toDate]);

    const channels = useMemo(() => {
        const set = new Set<string>();
        for (const row of data) {
            const channel = String(row.channel || '').trim();
            if (channel) set.add(channel);
        }
        return Array.from(set).sort((a, b) => a.localeCompare(b));
    }, [data]);

    const allChannelsSelected = selectedChannels.length === 0 || selectedChannels.length === channels.length;
    const channelSummary = allChannelsSelected
        ? 'All Channels'
        : selectedChannels.length === 1
            ? selectedChannels[0]
            : `${selectedChannels.length} Channels Selected`;

    const filteredData = useMemo(() => {
        return data.filter((row) => {
            const rowChannel = String(row.channel || '').trim();
            if (!allChannelsSelected && !selectedChannels.includes(rowChannel)) return false;
            if (!search.trim()) return true;

            const q = search.toLowerCase();
            const itemTypeSize = String(row.item_type_size || row.size || '').trim();
            const style = deriveStyle(String(row.item_type_name || ''), itemTypeSize);
            return (
                String(row.item_sku_code || '').toLowerCase().includes(q) ||
                String(row.item_type_name || '').toLowerCase().includes(q) ||
                itemTypeSize.toLowerCase().includes(q) ||
                style.toLowerCase().includes(q) ||
                String(row.channel || '').toLowerCase().includes(q)
            );
        });
    }, [data, search, allChannelsSelected, selectedChannels]);

    useEffect(() => {
        if (!loading || !activeProgressId) return;

        let cancelled = false;
        const poll = async () => {
            try {
                const res = await unicommerceApi.getReportProgress(activeProgressId);
                if (cancelled) return;

                const payload = res.data || {};
                const nextPercent = Number(payload.percent || 0);
                if (Number.isFinite(nextPercent)) {
                    setBackendPercent((prev) => (nextPercent > prev ? nextPercent : prev));
                }

                const nextLabel = String(payload.label || '').trim();
                if (nextLabel) {
                    setBackendLabel(nextLabel);
                }

                if (payload.status === 'completed' || payload.status === 'failed') {
                    setActiveProgressId(null);
                }
            } catch {
                // Keep the main report request running even if progress polling intermittently fails.
            }
        };

        poll();
        const timer = setInterval(poll, 900);
        return () => {
            cancelled = true;
            clearInterval(timer);
        };
    }, [loading, activeProgressId]);

    const handleGenerate = useCallback(async () => {
        const progressId = createProgressId();
        setLoading(true);
        setError(null);
        setBackendPercent(1);
        setBackendLabel('Starting sales activity generation…');
        setActiveProgressId(progressId);
        try {
            const res = await unicommerceApi.getSalesActivity({
                from_date: effectiveRange.fromDate,
                to_date: effectiveRange.toDate,
                progress_id: progressId,
            });
            const items = res.data?.items || [];
            setData(items);
            setSelectedChannels([]);
            if (!items.length) {
                setError('No data found for the selected range. Try a different date range.');
            }
            setBackendPercent(100);
            setBackendLabel('Report ready');
        } catch (err: any) {
            const msg = err?.response?.data?.detail || err?.message || 'Failed to fetch demo report data';
            setError(msg);
            setBackendPercent(100);
            setBackendLabel('Report failed');
        } finally {
            setLoading(false);
            setActiveProgressId(null);
        }
    }, [effectiveRange.fromDate, effectiveRange.toDate]);

    const handleToggleChannel = (channel: string) => {
        if (!channels.length) return;

        if (allChannelsSelected) {
            setSelectedChannels(channels.filter((ch) => ch !== channel));
            return;
        }

        setSelectedChannels((prev) => {
            if (prev.includes(channel)) {
                const next = prev.filter((ch) => ch !== channel);
                return next.length ? next : [];
            }
            const merged = [...prev, channel];
            if (merged.length >= channels.length) return [];
            return merged;
        });
    };

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
                    Sales activity report with size-wise and style-wise metrics in one combined table and current inventory snapshot.
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
                    {dateMode !== 'custom' && (
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

                    <div>
                        <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">Start Date</label>
                        <input
                            type="date"
                            value={effectiveRange.fromDate}
                            readOnly
                            className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-sm"
                        />
                    </div>

                    <div>
                        <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">End Date</label>
                        <input
                            type="date"
                            value={effectiveRange.toDate}
                            readOnly
                            className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-sm"
                        />
                    </div>

                    <div className="lg:col-span-4">
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
                            placeholder="Search by SKU, item name, item type size, style or channel..."
                            className="w-full pl-10 pr-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm"
                        />
                    </div>

                    <div ref={channelMenuRef} className="relative w-full lg:w-72">
                        <button
                            type="button"
                            onClick={() => setChannelMenuOpen((open) => !open)}
                            className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-left"
                        >
                            {channelSummary}
                        </button>

                        {channelMenuOpen && (
                            <div className="absolute z-20 mt-2 w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-lg p-2 space-y-1 max-h-72 overflow-y-auto">
                                <label className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={allChannelsSelected}
                                        onChange={() => setSelectedChannels([])}
                                    />
                                    <span className="text-sm font-medium">Select All Channels</span>
                                </label>

                                {channels.map((ch) => {
                                    const checked = allChannelsSelected || selectedChannels.includes(ch);
                                    return (
                                        <label key={ch} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer">
                                            <input
                                                type="checkbox"
                                                checked={checked}
                                                onChange={() => handleToggleChannel(ch)}
                                            />
                                            <span className="text-sm">{ch}</span>
                                        </label>
                                    );
                                })}

                                {!channels.length && (
                                    <div className="px-2 py-2 text-xs text-slate-500 dark:text-slate-400">
                                        Generate report to load channels.
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    <button
                        onClick={handleGenerate}
                        disabled={loading}
                        className="px-5 py-2 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
                    >
                        {loading ? 'Generating...' : 'Generate Report'}
                    </button>
                </div>
            </div>

            <ProgressLoader
                loading={loading}
                stages={progressStages}
                progressPercent={Math.max(backendPercent, 0)}
                progressLabel={backendLabel || undefined}
                skeletonRows={6}
            />

            {error && (
                <div className="card border border-amber-200 dark:border-amber-800/50 bg-amber-50/80 dark:bg-amber-950/30 text-amber-700 dark:text-amber-300 text-sm">
                    {error}
                </div>
            )}

            <div className="card">
                <DemoReportTable
                    data={filteredData}
                    selectedChannelLabel={channelSummary}
                />
            </div>
        </div>
    );
}
