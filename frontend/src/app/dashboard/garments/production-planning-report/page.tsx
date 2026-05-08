'use client';

import { ChangeEvent, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Download, History, Loader2, Plus, RefreshCw, Search, Upload } from 'lucide-react';

import { apiClient, getApiOrigin } from '@/lib/api-client';
import { useToast } from '@/shared/components';

type PlanningRow = {
  sku: string;
  style_code: string | null;
  cutting_plan: number;
  cutting: number;
  stitching: number;
  finishing: number;
  updated_at: string;
  created_at: string;
};

type HistoryRow = {
  sku: string;
  old_cutting_plan: number;
  new_cutting_plan: number;
  old_cutting: number;
  new_cutting: number;
  old_stitching: number;
  new_stitching: number;
  old_finishing: number;
  new_finishing: number;
  updated_quantity_difference: number;
  update_source: 'CSV' | 'MANUAL';
  updated_at: string;
};

const PAGE_SIZE = 20;

const initialManual = {
  sku: '',
  style_code: '',
  cutting_plan: '0',
  cutting: '0',
  stitching: '0',
  finishing: '0',
};

export default function ProductionPlanningReportPage() {
  const { success, error: toastError } = useToast();
  const csvInputRef = useRef<HTMLInputElement | null>(null);

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [updatedFrom, setUpdatedFrom] = useState('');
  const [updatedTo, setUpdatedTo] = useState('');

  const [showManualModal, setShowManualModal] = useState(false);
  const [manualForm, setManualForm] = useState(initialManual);

  const [historySku, setHistorySku] = useState<string | null>(null);
  const [historyPage, setHistoryPage] = useState(1);

  const listQuery = useQuery({
    queryKey: ['production-planning-list', page, search, updatedFrom, updatedTo],
    queryFn: async () => {
      const response = await apiClient.get('/production-planning', {
        params: {
          page,
          page_size: PAGE_SIZE,
          search: search || undefined,
          updated_from: updatedFrom || undefined,
          updated_to: updatedTo || undefined,
        },
      });
      return response.data as {
        items: PlanningRow[];
        page: number;
        page_size: number;
        total: number;
        total_pages: number;
      };
    },
    staleTime: 0,
  });

  const historyQuery = useQuery({
    queryKey: ['production-planning-history', historySku, historyPage],
    queryFn: async () => {
      const response = await apiClient.get(`/production-planning/${encodeURIComponent(historySku || '')}/history`, {
        params: { page: historyPage, page_size: 20 },
      });
      return response.data as {
        items: HistoryRow[];
        page: number;
        page_size: number;
        total: number;
        total_pages: number;
      };
    },
    enabled: !!historySku,
  });

  const manualMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        sku: manualForm.sku,
        style_code: manualForm.style_code || null,
        cutting_plan: Number(manualForm.cutting_plan || 0),
        cutting: Number(manualForm.cutting || 0),
        stitching: Number(manualForm.stitching || 0),
        finishing: Number(manualForm.finishing || 0),
      };
      const response = await apiClient.post('/production-planning/manual-entry', payload);
      return response.data;
    },
    onSuccess: (data) => {
      setShowManualModal(false);
      setManualForm(initialManual);
      listQuery.refetch();
      success(
        data?.operation === 'created'
          ? `SKU ${data?.item?.sku} created successfully`
          : `SKU ${data?.item?.sku} updated cumulatively`,
      );
    },
    onError: (err: any) => {
      const message = err?.response?.data?.detail || 'Manual entry failed';
      toastError(String(message));
    },
  });

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append('file', file);
      const response = await apiClient.post('/production-planning/upload-csv', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return response.data as {
        total_rows_processed: number;
        new_skus_created: number;
        existing_skus_updated: number;
        failed_rows_count: number;
      };
    },
    onSuccess: (data) => {
      listQuery.refetch();
      success(
        `${data.new_skus_created} new SKUs added, ${data.existing_skus_updated} SKUs updated, ${data.failed_rows_count} rows failed`,
      );
    },
    onError: (err: any) => {
      const message = err?.response?.data?.detail || 'CSV upload failed';
      toastError(String(message));
    },
  });

  const totalPages = listQuery.data?.total_pages || 1;
  const rows = listQuery.data?.items || [];

  const canSubmitManual = useMemo(() => {
    if (!manualForm.sku.trim()) return false;
    const nums = [manualForm.cutting_plan, manualForm.cutting, manualForm.stitching, manualForm.finishing];
    return nums.every((n) => Number(n) >= 0);
  }, [manualForm]);

  const onCsvSelected = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    uploadMutation.mutate(file);
    e.target.value = '';
  };

  const handleExportCsv = async () => {
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (updatedFrom) params.set('updated_from', updatedFrom);
      if (updatedTo) params.set('updated_to', updatedTo);

      const origin = getApiOrigin();
      const token = localStorage.getItem('access_token');
      const res = await fetch(`${origin}/api/v1/production-planning/export/csv?${params.toString()}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'production-planning-report.csv';
      a.click();
      URL.revokeObjectURL(url);
      success('CSV exported successfully');
    } catch (e: any) {
      toastError(e?.message || 'Export failed');
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Production Planning Report</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          SKU-wise cumulative production tracking for cutting plan, cutting, stitching, and finishing.
        </p>
      </div>

      <div className="card space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="relative md:col-span-2">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search SKU or style code"
              className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
            />
          </div>
          <input
            type="date"
            value={updatedFrom}
            onChange={(e) => {
              setUpdatedFrom(e.target.value);
              setPage(1);
            }}
            className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
          />
          <input
            type="date"
            value={updatedTo}
            onChange={(e) => {
              setUpdatedTo(e.target.value);
              setPage(1);
            }}
            className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => csvInputRef.current?.click()}
            className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-60"
            disabled={uploadMutation.isPending}
          >
            {uploadMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            Upload CSV
          </button>
          <input ref={csvInputRef} type="file" accept=".csv" className="hidden" onChange={onCsvSelected} />

          <button
            type="button"
            onClick={() => setShowManualModal(true)}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800"
          >
            <Plus className="h-4 w-4" />
            Manual Entry
          </button>

          <button
            type="button"
            onClick={handleExportCsv}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800"
          >
            <Download className="h-4 w-4" />
            Export CSV
          </button>

          <button
            type="button"
            onClick={() => listQuery.refetch()}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </div>

      <div className="card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800/60">
              <tr>
                {['SKU', 'Style Code', 'Cutting Plan', 'Cutting', 'Stitching', 'Finishing', 'Last Updated', 'Actions'].map((h) => (
                  <th key={h} className="px-4 py-3 text-left whitespace-nowrap font-semibold text-slate-600 dark:text-slate-300">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {listQuery.isLoading ? (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-slate-500">
                    <Loader2 className="h-5 w-5 animate-spin inline mr-2" />
                    Loading rows...
                  </td>
                </tr>
              ) : rows.length ? (
                rows.map((row) => (
                  <tr key={row.sku} className="border-t border-slate-200 dark:border-slate-800">
                    <td className="px-4 py-3 font-mono text-xs">{row.sku}</td>
                    <td className="px-4 py-3">{row.style_code || '-'}</td>
                    <td className="px-4 py-3 text-right">{row.cutting_plan}</td>
                    <td className="px-4 py-3 text-right">{row.cutting}</td>
                    <td className="px-4 py-3 text-right">{row.stitching}</td>
                    <td className="px-4 py-3 text-right">{row.finishing}</td>
                    <td className="px-4 py-3 whitespace-nowrap">{new Date(row.updated_at).toLocaleString()}</td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => {
                          setHistorySku(row.sku);
                          setHistoryPage(1);
                        }}
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-300 dark:border-slate-700 px-2.5 py-1.5 text-xs font-medium hover:bg-slate-50 dark:hover:bg-slate-800"
                      >
                        <History className="h-3.5 w-3.5" />
                        History
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-slate-500">
                    No rows found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex items-center justify-between text-sm">
        <div className="text-slate-500">
          Total: <span className="font-semibold text-slate-900 dark:text-white">{listQuery.data?.total || 0}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="rounded-lg border border-slate-300 dark:border-slate-700 px-3 py-1.5 disabled:opacity-40"
          >
            Previous
          </button>
          <span>
            Page {page} / {totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            className="rounded-lg border border-slate-300 dark:border-slate-700 px-3 py-1.5 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>

      {showManualModal && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
          <div className="w-full max-w-xl rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">Manual SKU Entry</h3>
              <button type="button" onClick={() => setShowManualModal(false)} className="text-sm text-slate-500">
                Close
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <input
                placeholder="SKU *"
                value={manualForm.sku}
                onChange={(e) => setManualForm((s) => ({ ...s, sku: e.target.value }))}
                className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
              />
              <input
                placeholder="Style Code (optional)"
                value={manualForm.style_code}
                onChange={(e) => setManualForm((s) => ({ ...s, style_code: e.target.value }))}
                className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
              />
              {(['cutting_plan', 'cutting', 'stitching', 'finishing'] as const).map((field) => (
                <input
                  key={field}
                  type="number"
                  min={0}
                  step={1}
                  placeholder={field.replace('_', ' ')}
                  value={manualForm[field]}
                  onChange={(e) => setManualForm((s) => ({ ...s, [field]: e.target.value }))}
                  className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                />
              ))}
            </div>
            <button
              type="button"
              disabled={!canSubmitManual || manualMutation.isPending}
              onClick={() => manualMutation.mutate()}
              className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-60"
            >
              {manualMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Save (Additive Upsert)
            </button>
          </div>
        </div>
      )}

      {historySku && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
          <div className="w-full max-w-5xl rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">History · {historySku}</h3>
              <button type="button" onClick={() => setHistorySku(null)} className="text-sm text-slate-500">
                Close
              </button>
            </div>
            <div className="overflow-x-auto max-h-[55vh]">
              <table className="min-w-full text-xs">
                <thead className="bg-slate-50 dark:bg-slate-800/60 sticky top-0">
                  <tr>
                    {['Old CP', 'New CP', 'Old C', 'New C', 'Old S', 'New S', 'Old F', 'New F', 'Diff', 'Source', 'Updated At'].map((h) => (
                      <th key={h} className="px-3 py-2 text-left whitespace-nowrap">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {historyQuery.isLoading ? (
                    <tr>
                      <td colSpan={11} className="px-4 py-6 text-center">
                        <Loader2 className="h-4 w-4 animate-spin inline mr-2" />
                        Loading history...
                      </td>
                    </tr>
                  ) : (historyQuery.data?.items || []).length ? (
                    (historyQuery.data?.items || []).map((r, idx) => (
                      <tr key={`${r.updated_at}-${idx}`} className="border-t border-slate-200 dark:border-slate-800">
                        <td className="px-3 py-2">{r.old_cutting_plan}</td>
                        <td className="px-3 py-2">{r.new_cutting_plan}</td>
                        <td className="px-3 py-2">{r.old_cutting}</td>
                        <td className="px-3 py-2">{r.new_cutting}</td>
                        <td className="px-3 py-2">{r.old_stitching}</td>
                        <td className="px-3 py-2">{r.new_stitching}</td>
                        <td className="px-3 py-2">{r.old_finishing}</td>
                        <td className="px-3 py-2">{r.new_finishing}</td>
                        <td className="px-3 py-2">{r.updated_quantity_difference}</td>
                        <td className="px-3 py-2">{r.update_source}</td>
                        <td className="px-3 py-2 whitespace-nowrap">{new Date(r.updated_at).toLocaleString()}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={11} className="px-4 py-6 text-center text-slate-500">
                        No history rows.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between text-sm">
              <div>
                Total: <span className="font-semibold">{historyQuery.data?.total || 0}</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={historyPage <= 1}
                  onClick={() => setHistoryPage((p) => Math.max(1, p - 1))}
                  className="rounded-lg border border-slate-300 dark:border-slate-700 px-3 py-1.5 disabled:opacity-40"
                >
                  Prev
                </button>
                <span>
                  {historyPage} / {historyQuery.data?.total_pages || 1}
                </span>
                <button
                  type="button"
                  disabled={historyPage >= (historyQuery.data?.total_pages || 1)}
                  onClick={() => setHistoryPage((p) => Math.min(historyQuery.data?.total_pages || 1, p + 1))}
                  className="rounded-lg border border-slate-300 dark:border-slate-700 px-3 py-1.5 disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
