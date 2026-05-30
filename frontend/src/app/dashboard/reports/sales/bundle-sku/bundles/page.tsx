'use client';

import React, { useState, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ucSales } from '@/features/sales/api';
import { Column } from '@/components/ui/DataTable';
import { PageHeader, ProgressLoader, StatCard } from '@/components/ui/Common';

const PAGE_SIZE = 20;

export default function BundleSkuPage() {
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('all');
  const [page, setPage] = useState(0);
  const [showEnabledOnly, setShowEnabledOnly] = useState(false);
  const [expandedSku, setExpandedSku] = useState<string | null>(null);

  const [debouncedSearch, setDebouncedSearch] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(0);
    }, 500);
    return () => clearTimeout(timer);
  }, [search]);

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['uc-bundle-skus', page, debouncedSearch, category, showEnabledOnly],
    queryFn: async () => {
      const response = await ucSales.getBundleSkus({
        page: page,
        limit: PAGE_SIZE,
        search: debouncedSearch,
        category: category === 'all' ? undefined : category,
        enabled_only: showEnabledOnly
      });
      return response.data;
    },
    staleTime: 300_000,
  });

  const summary = useMemo(() => data?.summary ?? {}, [data?.summary]);
  const categories: Record<string, number> = summary.categories || {};

  const paginated = useMemo(() => data?.bundles ?? [], [data?.bundles]);
  const totalPages = data?.total_pages || 1;
  const filteredLength = data?.total_records || 0;

  const handleRefresh = useCallback(() => {
    refetch();
  }, [refetch]);

  const columns: Column<any>[] = [
    {
      key: 'skuCode',
      header: 'SKU Code',
      width: '11%',
      render: (value) => (
        <span className="font-mono text-xs font-semibold text-slate-900 dark:text-slate-100">
          {value}
        </span>
      ),
    },
    {
      key: 'itemName',
      header: 'Bundle Name',
      width: '20%',
      render: (value) => (
        <span className="text-sm text-slate-800 dark:text-slate-200 line-clamp-2">
          {value}
        </span>
      ),
    },
    {
      key: 'category',
      header: 'Category',
      width: '11%',
      render: (value) => (
        <span className="px-2 py-0.5 bg-violet-50 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 rounded-lg text-xs font-medium">
          {value || '-'}
        </span>
      ),
    },
    {
      key: 'mrp',
      header: 'MRP',
      width: '8%',
      render: (value) => (
        <span className="text-slate-900 dark:text-slate-100 font-medium">
          ₹{(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
        </span>
      ),
    },
    {
      key: 'basePrice',
      header: 'Base Price',
      width: '8%',
      render: (value) => (
        <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
          ₹{(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
        </span>
      ),
    },
    {
      key: 'costPrice',
      header: 'Cost Price',
      width: '8%',
      render: (value) => (
        <span className="text-slate-600 dark:text-slate-400">
          ₹{(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
        </span>
      ),
    },
    {
      key: 'size',
      header: 'Size',
      width: '7%',
      render: (value) => (
        <span className="text-xs text-slate-700 dark:text-slate-300">{value || '-'}</span>
      ),
    },
    {
      key: 'components',
      header: 'Components',
      width: '14%',
      render: (_value, row) => {
        const comps: any[] = row?.components || [];
        if (comps.length === 0) return <span className="text-slate-400">-</span>;
        return (
          <div className="flex flex-wrap gap-1">
            {comps.slice(0, 3).map((c: any, i: number) => (
              <span
                key={i}
                className="px-1.5 py-0.5 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-[10px] font-medium"
                title={`${c.sku} × ${c.quantity}`}
              >
                {c.sku}
              </span>
            ))}
            {comps.length > 3 && (
              <span className="px-1.5 py-0.5 bg-slate-100 dark:bg-slate-700 text-slate-500 rounded text-[10px]">
                +{comps.length - 3}
              </span>
            )}
          </div>
        );
      },
    },
    {
      key: 'componentCount',
      header: '#',
      width: '4%',
      render: (value) => (
        <span className="text-xs font-medium text-slate-600 dark:text-slate-400">{value ?? '-'}</span>
      ),
    },
    {
      key: 'enabled',
      header: 'Status',
      width: '6%',
      render: (value) => (
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${value
            ? 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400'
            : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-500'
            }`}
        >
          {value ? 'Active' : 'Off'}
        </span>
      ),
    },
  ];

  return (
    <div className="page-section-gap">
      <PageHeader
        title="Bundle SKU Catalog"
        description="All bundle/combo SKUs from Unicommerce Item Master — deduplicated with component details"
      />

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
        <StatCard
          title="Total Bundles"
          value={(summary.total_bundles || 0).toLocaleString('en-IN')}
          icon="📦"
          color="blue"
        />
        <StatCard
          title="Active"
          value={(summary.enabled || 0).toLocaleString('en-IN')}
          icon="✅"
          color="green"
        />
        <StatCard
          title="Disabled"
          value={(summary.disabled || 0).toLocaleString('en-IN')}
          icon="🚫"
          color="red"
        />
        <StatCard
          title="Avg MRP"
          value={`₹${(summary.avg_mrp || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}
          icon="💰"
          color="purple"
        />
        <StatCard
          title="Categories"
          value={(summary.total_categories || 0).toLocaleString('en-IN')}
          icon="🏷️"
          color="yellow"
        />
      </div>

      {/* Filters */}
      <div className="card">
        <div className="flex gap-4 items-center flex-wrap">
          <input
            type="text"
            placeholder="Search SKU, name, category, brand, component..."
            className="input w-full sm:flex-1"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }}
          />
          <select
            value={category}
            onChange={(e) => { setCategory(e.target.value); setPage(0); }}
            className="input w-full sm:w-56"
          >
            <option value="all">All Categories ({Object.keys(categories).length})</option>
            {Object.entries(categories).map(([cat, count]) => (
              <option key={cat} value={cat}>
                {cat} ({count})
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showEnabledOnly}
              onChange={(e) => { setShowEnabledOnly(e.target.checked); setPage(0); }}
              className="accent-emerald-500 w-4 h-4"
            />
            Active only
          </label>
          <button
            onClick={handleRefresh}
            disabled={isFetching}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors w-full sm:w-auto ${isFetching
              ? 'bg-slate-200 dark:bg-slate-700 text-slate-400 cursor-not-allowed'
              : 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'
              }`}
          >
            {isFetching ? 'Refreshing…' : '🔄 Refresh'}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="card bg-rose-50 dark:bg-rose-900/20 mb-4">
          <p className="text-rose-600 dark:text-rose-400">
            Error: {(error as any)?.message || 'Failed to load bundle data'}
          </p>
        </div>
      )}

      {/* Table */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
            Bundle SKUs
          </h2>
          <span className="text-sm text-slate-500 dark:text-slate-400">
            {filteredLength.toLocaleString('en-IN')} bundle{filteredLength !== 1 ? 's' : ''}
            {category !== 'all' && ` in ${category}`}
            <span className="ml-2 text-xs text-slate-400">(click a row to see components)</span>
          </span>
        </div>
        <ProgressLoader loading={isLoading || isFetching} stages={[
          { at: 0, label: 'Connecting to Unicommerce…' },
          { at: 15, label: 'Fetching item master…' },
          { at: 40, label: 'Identifying bundle SKUs…' },
          { at: 70, label: 'Resolving components…' },
          { at: 90, label: 'Finalizing…' },
        ]} />
        {isLoading || isFetching ? null : paginated.length === 0 ? (
          <div className="text-center py-16">
            <p className="text-sm text-slate-500 dark:text-slate-400">No bundle SKUs match the current filters.</p>
          </div>
        ) : (
          <div className="table-scroll-wrap rounded-xl border border-slate-200/80 dark:border-slate-700/80">
            <table className="min-w-full">
              <thead>
                <tr className="bg-slate-50/80 dark:bg-slate-800/50">
                  {columns.map((col) => (
                    <th key={col.key} className="px-4 py-3 text-left text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider" style={{ width: col.width }}>
                      {col.header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                {paginated.map((row: any) => {
                  const isExpanded = expandedSku === row.skuCode;
                  const comps: any[] = row.components || [];
                  return (
                    <React.Fragment key={row.skuCode}>
                      <tr
                        onClick={() => setExpandedSku(isExpanded ? null : row.skuCode)}
                        className={`cursor-pointer transition-colors duration-150 ${isExpanded
                          ? 'bg-indigo-50/60 dark:bg-indigo-900/15'
                          : 'hover:bg-slate-50/80 dark:hover:bg-slate-800/50'
                          }`}
                      >
                        {columns.map((col) => (
                          <td key={col.key} className="px-4 py-3 text-sm text-slate-700 dark:text-slate-300">
                            {col.render ? col.render(row[col.key], row) : row[col.key]}
                          </td>
                        ))}
                      </tr>
                      {isExpanded && comps.length > 0 && (
                        <tr>
                          <td colSpan={columns.length} className="px-0 py-0 bg-slate-50/50 dark:bg-slate-800/30">
                            <div className="px-6 py-4">
                              <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-3">
                                Component Items ({comps.length})
                              </h4>
                              <div className="overflow-x-auto rounded-lg border border-slate-200/60 dark:border-slate-700/60">
                                <table className="min-w-full">
                                  <thead>
                                    <tr className="bg-slate-100/80 dark:bg-slate-700/50">
                                      <th className="px-4 py-2 text-left text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider w-[5%]">#</th>
                                      <th className="px-4 py-2 text-left text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider w-[35%]">Component SKU</th>
                                      <th className="px-4 py-2 text-left text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider w-[30%]">Quantity per Bundle</th>
                                      <th className="px-4 py-2 text-left text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider w-[30%]">Component Price</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-slate-100 dark:divide-slate-700/40">
                                    {comps.map((c: any, i: number) => (
                                      <tr key={i} className="hover:bg-white/60 dark:hover:bg-slate-800/40">
                                        <td className="px-4 py-2.5 text-xs text-slate-400">{i + 1}</td>
                                        <td className="px-4 py-2.5">
                                          <span className="font-mono text-xs font-semibold text-indigo-700 dark:text-indigo-300">{c.sku}</span>
                                        </td>
                                        <td className="px-4 py-2.5">
                                          <span className="inline-flex items-center px-2 py-0.5 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-full text-xs font-semibold">
                                            × {c.quantity || 1}
                                          </span>
                                        </td>
                                        <td className="px-4 py-2.5 text-sm text-slate-700 dark:text-slate-300 font-medium">
                                          {c.price ? `₹${Number(c.price).toLocaleString('en-IN', { maximumFractionDigits: 0 })}` : '-'}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                      {isExpanded && comps.length === 0 && (
                        <tr>
                          <td colSpan={columns.length} className="px-6 py-4 bg-slate-50/50 dark:bg-slate-800/30">
                            <p className="text-sm text-slate-400 italic">No component data available for this bundle.</p>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 mt-4">
          <button
            disabled={page === 0}
            onClick={() => setPage(page - 1)}
            className="btn btn-secondary disabled:opacity-40"
          >
            ← Previous
          </button>
          <span className="text-sm text-slate-600 dark:text-slate-400">
            Page {page + 1} of {totalPages}
          </span>
          <button
            disabled={page >= totalPages - 1}
            onClick={() => setPage(page + 1)}
            className="btn btn-secondary disabled:opacity-40"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}