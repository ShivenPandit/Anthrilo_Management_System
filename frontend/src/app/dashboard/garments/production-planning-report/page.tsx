'use client';

import { ChangeEvent, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { History, Loader2, Pencil, Plus, RefreshCw, Search, Trash2, Upload } from 'lucide-react';

import { apiClient } from '@/lib/api-client';
import { useToast } from '@/shared/components';

type PlanningRow = {
  sku: string;
  style_code: string | null;
  name: string | null;
  size: string | null;
  type: string | null;
  cutting_plan: number;
  cutting: number;
  stitching: number;
  finishing: number;
  tags?: string;
  scanning?: number;
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
  name: '',
  size: '',
  type: '',
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

  const [showManualModal, setShowManualModal] = useState(false);
  const [manualForm, setManualForm] = useState(initialManual);
  const [editingSku, setEditingSku] = useState<string | null>(null);
  const [editForm, setEditForm] = useState(initialManual);

  const [historySku, setHistorySku] = useState<string | null>(null);
  const [historyPage, setHistoryPage] = useState(1);

  const listQuery = useQuery({
    queryKey: ['production-planning-list', page, search],
    queryFn: async () => {
      const response = await apiClient.get('/production-planning', {
        params: {
          page,
          page_size: PAGE_SIZE,
          search: search || undefined,
          _t: Date.now(),
        },
        headers: {
          'Cache-Control': 'no-cache',
          Pragma: 'no-cache',
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
        name: manualForm.name || null,
        size: manualForm.size || null,
        type: manualForm.type || null,
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
      const response = await apiClient.post('/production-planning/upload-csv', form);
      return response.data as {
        total_rows_processed: number;
        new_skus_created: number;
        existing_skus_updated: number;
        failed_rows_count: number;
      };
    },
    onSuccess: (data) => {
      setPage(1);
      setSearch('');
      listQuery.refetch();
      success(
        `${data.total_rows_processed} rows processed: ${data.new_skus_created} new SKUs, ${data.existing_skus_updated} updated, ${data.failed_rows_count} failed`,
      );
    },
    onError: (err: any) => {
      const message = err?.response?.data?.detail || 'CSV upload failed';
      toastError(String(message));
    },
  });

  const editMutation = useMutation({
    mutationFn: async () => {
      if (!editingSku) throw new Error('No SKU selected');
      const payload = {
        sku: editingSku,
        style_code: editForm.style_code || null,
        name: editForm.name || null,
        size: editForm.size || null,
        type: editForm.type || null,
        cutting_plan: Number(editForm.cutting_plan || 0),
        cutting: Number(editForm.cutting || 0),
        stitching: Number(editForm.stitching || 0),
        finishing: Number(editForm.finishing || 0),
      };
      const response = await apiClient.put(`/production-planning/${encodeURIComponent(editingSku)}`, payload);
      return response.data;
    },
    onSuccess: (data) => {
      setEditingSku(null);
      setEditForm(initialManual);
      listQuery.refetch();
      success(`SKU ${data?.item?.sku} updated successfully`);
    },
    onError: (err: any) => {
      const message = err?.response?.data?.detail || 'Edit failed';
      toastError(String(message));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (sku: string) => {
      const response = await apiClient.delete(`/production-planning/${encodeURIComponent(sku)}`);
      return response.data;
    },
    onSuccess: (data) => {
      listQuery.refetch();
      success(`SKU ${data?.sku || ''} deleted successfully`);
    },
    onError: (err: any) => {
      const message = err?.response?.data?.detail || 'Delete failed';
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

  const canSubmitEdit = useMemo(() => {
    if (!editingSku) return false;
    const nums = [editForm.cutting_plan, editForm.cutting, editForm.stitching, editForm.finishing];
    return nums.every((n) => Number(n) >= 0);
  }, [editForm, editingSku]);

  const onCsvSelected = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    uploadMutation.mutate(file);
    e.target.value = '';
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
        <div className="grid grid-cols-1 gap-3">
          <div className="relative">
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
                {[
                  { label: 'sku code', className: 'text-left' },
                  { label: 'name', className: 'text-left' },
                  { label: 'type', className: 'text-left' },
                  { label: 'tags', className: 'text-left' },
                  { label: 'size', className: 'text-left' },
                  { label: 'Cutting Plan', className: 'text-right' },
                  { label: 'Cutting', className: 'text-right' },
                  { label: 'Stitching', className: 'text-right' },
                  { label: 'Finishing', className: 'text-right' },
                  { label: 'scanning', className: 'text-right' },
                  { label: 'Last Updated', className: 'text-left' },
                  { label: 'Actions', className: 'text-left' },
                ].map((h) => (
                  <th
                    key={h.label}
                    className={`px-4 py-3 whitespace-nowrap font-semibold text-slate-600 dark:text-slate-300 ${h.className}`}
                  >
                    {h.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {listQuery.isLoading ? (
                <tr>
                  <td colSpan={12} className="px-4 py-10 text-center text-slate-500">
                    <Loader2 className="h-5 w-5 animate-spin inline mr-2" />
                    Loading rows...
                  </td>
                </tr>
              ) : rows.length ? (
                rows.map((row) => (
                  <tr key={row.sku} className="border-t border-slate-200 dark:border-slate-800">
                    <td className="px-4 py-3 font-mono text-xs">{row.sku}</td>
                    <td className="px-4 py-3">{row.name || row.style_code || '-'}</td>
                    <td className="px-4 py-3">{row.type || '-'}</td>
                    <td className="px-4 py-3">{row.tags || ''}</td>
                    <td className="px-4 py-3">{row.size || '-'}</td>
                    <td className="px-4 py-3 text-right">{row.cutting_plan}</td>
                    <td className="px-4 py-3 text-right">{row.cutting}</td>
                    <td className="px-4 py-3 text-right">{row.stitching}</td>
                    <td className="px-4 py-3 text-right">{row.finishing}</td>
                    <td className="px-4 py-3 text-right">{row.scanning ?? 0}</td>
                    <td className="px-4 py-3 whitespace-nowrap">{new Date(row.updated_at).toLocaleString()}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
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
                        <button
                          type="button"
                          onClick={() => {
                            setEditingSku(row.sku);
                            setEditForm({
                              sku: row.sku,
                              style_code: row.style_code || '',
                              name: row.name || '',
                              size: row.size || '',
                              type: row.type || '',
                              cutting_plan: String(row.cutting_plan),
                              cutting: String(row.cutting),
                              stitching: String(row.stitching),
                              finishing: String(row.finishing),
                            });
                          }}
                          className="inline-flex items-center gap-1 rounded-lg border border-slate-300 dark:border-slate-700 px-2.5 py-1.5 text-xs font-medium hover:bg-slate-50 dark:hover:bg-slate-800"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            if (!window.confirm(`Delete SKU ${row.sku}? This cannot be undone.`)) return;
                            deleteMutation.mutate(row.sku);
                          }}
                          disabled={deleteMutation.isPending}
                          className="inline-flex items-center gap-1 rounded-lg border border-rose-300 text-rose-700 dark:border-rose-800 dark:text-rose-300 px-2.5 py-1.5 text-xs font-medium hover:bg-rose-50 dark:hover:bg-rose-900/20 disabled:opacity-60"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={12} className="px-4 py-10 text-center text-slate-500">
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
                placeholder="Name (optional)"
                value={manualForm.name}
                onChange={(e) => setManualForm((s) => ({ ...s, name: e.target.value }))}
                className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
              />
              <input
                placeholder="Size (optional)"
                value={manualForm.size}
                onChange={(e) => setManualForm((s) => ({ ...s, size: e.target.value }))}
                className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
              />
              <input
                placeholder="Type (optional)"
                value={manualForm.type}
                onChange={(e) => setManualForm((s) => ({ ...s, type: e.target.value }))}
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

      {editingSku && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
          <div className="w-full max-w-xl rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">Edit SKU · {editingSku}</h3>
              <button
                type="button"
                onClick={() => {
                  setEditingSku(null);
                  setEditForm(initialManual);
                }}
                className="text-sm text-slate-500"
              >
                Close
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <input
                value={editingSku}
                disabled
                className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-slate-500"
              />
              <input
                placeholder="Name (optional)"
                value={editForm.name}
                onChange={(e) => setEditForm((s) => ({ ...s, name: e.target.value }))}
                className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
              />
              <input
                placeholder="Size (optional)"
                value={editForm.size}
                onChange={(e) => setEditForm((s) => ({ ...s, size: e.target.value }))}
                className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
              />
              <input
                placeholder="Type (optional)"
                value={editForm.type}
                onChange={(e) => setEditForm((s) => ({ ...s, type: e.target.value }))}
                className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
              />
              {(['cutting_plan', 'cutting', 'stitching', 'finishing'] as const).map((field) => (
                <input
                  key={field}
                  type="number"
                  min={0}
                  step={1}
                  placeholder={field.replace('_', ' ')}
                  value={editForm[field]}
                  onChange={(e) => setEditForm((s) => ({ ...s, [field]: e.target.value }))}
                  className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                />
              ))}
            </div>
            <button
              type="button"
              disabled={!canSubmitEdit || editMutation.isPending}
              onClick={() => editMutation.mutate()}
              className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-60"
            >
              {editMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Save Changes
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
