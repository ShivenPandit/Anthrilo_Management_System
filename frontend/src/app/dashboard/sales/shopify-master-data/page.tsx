'use client';

import { useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, CheckCircle2, FileSpreadsheet, Loader2, RefreshCw, Search, Upload } from 'lucide-react';

import { shopifyMasterDataApi } from '@/lib/api';

interface ShopifyMasterDataItem {
    id: number;
    variant_sku: string;
    title?: string | null;
    type?: string | null;
    tags?: string | null;
    option1_value?: string | null;
    cost_per_item?: number | null;
    created_at: string;
    updated_at: string;
}

interface ShopifyMasterDataResponse {
    items: ShopifyMasterDataItem[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
}

interface ImportSummary {
    inserted: number;
    updated: number;
    skipped: number;
    errors: Array<{ row?: number; error?: string }>;
}

const PAGE_SIZE = 50;

export default function ShopifyMasterDataPage() {
    const qc = useQueryClient();
    const inputRef = useRef<HTMLInputElement | null>(null);

    const [search, setSearch] = useState('');
    const [debouncedSearch, setDebouncedSearch] = useState('');
    const [page, setPage] = useState(1);
    const [summary, setSummary] = useState<ImportSummary | null>(null);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);

    const skip = (page - 1) * PAGE_SIZE;

    const listQuery = useQuery<ShopifyMasterDataResponse>({
        queryKey: ['shopify-master-data', skip, PAGE_SIZE, debouncedSearch],
        queryFn: async () => {
            const response = await shopifyMasterDataApi.getAll({
                skip,
                limit: PAGE_SIZE,
                search: debouncedSearch || undefined,
            });
            return response.data as ShopifyMasterDataResponse;
        },
    });

    const uploadMutation = useMutation({
        mutationFn: async (file: File) => {
            const response = await shopifyMasterDataApi.import(file);
            return response.data as ImportSummary;
        },
        onSuccess: (payload) => {
            setSummary(payload);
            setErrorMessage(null);
            qc.invalidateQueries({ queryKey: ['shopify-master-data'] });
        },
        onError: (err: any) => {
            setSummary(null);
            const detail = err?.response?.data?.detail;
            if (typeof detail === 'string') {
                setErrorMessage(detail);
            } else {
                setErrorMessage('Upload failed. Please check file format and headers.');
            }
        },
    });

    const rows = listQuery.data?.items ?? [];
    const total = listQuery.data?.total ?? 0;
    const totalPages = Math.max(1, listQuery.data?.total_pages ?? 1);

    const uploading = uploadMutation.isPending;
    const loading = listQuery.isLoading || listQuery.isFetching;

    const onSearchChange = (value: string) => {
        setSearch(value);
        setPage(1);
        window.clearTimeout((onSearchChange as any)._timer);
        (onSearchChange as any)._timer = window.setTimeout(() => {
            setDebouncedSearch(value.trim());
        }, 300);
    };

    const handleChooseFile = () => {
        inputRef.current?.click();
    };

    const handleUpload = (file: File | null) => {
        if (!file) return;
        setSummary(null);
        setErrorMessage(null);
        uploadMutation.mutate(file);
        if (inputRef.current) {
            inputRef.current.value = '';
        }
    };

    const rangeLabel = useMemo(() => {
        if (!total) return '0 records';
        const from = skip + 1;
        const to = Math.min(skip + PAGE_SIZE, total);
        return `${from}-${to} of ${total} records`;
    }, [skip, total]);

    return (
        <div className="space-y-6">
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Shopify Master Data</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400">
                        Upload and manage Variant SKU master data for Type, Tags and Cost enrichment.
                    </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                    <button
                        type="button"
                        onClick={handleChooseFile}
                        disabled={uploading}
                        className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-60"
                    >
                        {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                        Upload CSV/XLSX
                    </button>
                    <input
                        ref={inputRef}
                        type="file"
                        accept=".csv,.xlsx"
                        className="hidden"
                        onChange={(e) => handleUpload(e.target.files?.[0] ?? null)}
                    />
                    <button
                        type="button"
                        onClick={() => listQuery.refetch()}
                        className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800"
                    >
                        <RefreshCw className="h-4 w-4" /> Refresh
                    </button>
                </div>
            </div>

            <div className="card space-y-3">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                        <input
                            type="text"
                            value={search}
                            onChange={(e) => onSearchChange(e.target.value)}
                            placeholder="Search by SKU, title, type, tags or option value"
                            className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 pl-9 pr-3 py-2 text-sm"
                        />
                    </div>
                    <div className="text-xs text-slate-500 dark:text-slate-400 flex items-center lg:justify-end">
                        Required column: Variant SKU. Optional: Title, Type, Tags, Option1 Value, Cost per item.
                    </div>
                </div>

                {summary && (
                    <div className="rounded-lg border border-emerald-200 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/20 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300 flex items-center gap-2">
                        <CheckCircle2 className="h-4 w-4" />
                        Inserted: {summary.inserted}, Updated: {summary.updated}, Skipped: {summary.skipped}
                        {summary.errors?.length ? `, Errors: ${summary.errors.length}` : ''}
                    </div>
                )}

                {errorMessage && (
                    <div className="rounded-lg border border-rose-200 dark:border-rose-700 bg-rose-50 dark:bg-rose-900/20 px-3 py-2 text-sm text-rose-700 dark:text-rose-300 flex items-center gap-2">
                        <AlertCircle className="h-4 w-4" /> {errorMessage}
                    </div>
                )}
            </div>

            <div className="card p-0 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                        <thead>
                            <tr className="bg-slate-50 dark:bg-slate-800/60">
                                <th className="px-4 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">Variant SKU</th>
                                <th className="px-4 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">Title</th>
                                <th className="px-4 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">Type</th>
                                <th className="px-4 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">Tags</th>
                                <th className="px-4 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">Option1 Value</th>
                                <th className="px-4 py-3 text-right font-semibold text-slate-600 dark:text-slate-300">Cost per item</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                <tr>
                                    <td colSpan={6} className="px-4 py-8 text-center text-slate-500 dark:text-slate-400">
                                        <span className="inline-flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> Loading...</span>
                                    </td>
                                </tr>
                            ) : rows.length === 0 ? (
                                <tr>
                                    <td colSpan={6} className="px-4 py-8 text-center text-slate-500 dark:text-slate-400">
                                        <span className="inline-flex items-center gap-2"><FileSpreadsheet className="h-4 w-4" /> No Shopify master data found.</span>
                                    </td>
                                </tr>
                            ) : (
                                rows.map((r) => (
                                    <tr key={r.id} className="border-t border-slate-100 dark:border-slate-800">
                                        <td className="px-4 py-3 font-mono text-xs text-slate-700 dark:text-slate-300">{r.variant_sku}</td>
                                        <td className="px-4 py-3 text-slate-700 dark:text-slate-300">{r.title || '-'}</td>
                                        <td className="px-4 py-3 text-slate-700 dark:text-slate-300">{r.type || '-'}</td>
                                        <td className="px-4 py-3 text-slate-700 dark:text-slate-300 max-w-[520px] truncate" title={r.tags || ''}>{r.tags || '-'}</td>
                                        <td className="px-4 py-3 text-slate-700 dark:text-slate-300">{r.option1_value || '-'}</td>
                                        <td className="px-4 py-3 text-right text-slate-700 dark:text-slate-300">{r.cost_per_item == null ? '-' : Number(r.cost_per_item).toFixed(2)}</td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                <div className="flex items-center justify-between border-t border-slate-200 dark:border-slate-800 px-4 py-3 text-xs text-slate-500 dark:text-slate-400">
                    <span>{rangeLabel}</span>
                    <div className="flex items-center gap-2">
                        <button
                            type="button"
                            disabled={page <= 1}
                            onClick={() => setPage((p) => Math.max(1, p - 1))}
                            className="rounded-md border border-slate-300 dark:border-slate-700 px-2 py-1 disabled:opacity-50"
                        >
                            Prev
                        </button>
                        <span>Page {page} / {totalPages}</span>
                        <button
                            type="button"
                            disabled={page >= totalPages}
                            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                            className="rounded-md border border-slate-300 dark:border-slate-700 px-2 py-1 disabled:opacity-50"
                        >
                            Next
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
