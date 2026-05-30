'use client';

import { useState, useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ucCatalog } from '@/features/sales/api';

const PAGE_SIZE = 25;

/* tiny helpers */
const fmt = (n?: number) => (n ?? 0).toLocaleString('en-IN');
const inr = (n?: number) => `₹${(n ?? 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

export default function GarmentMasterPage() {
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(0);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [showCategories, setShowCategories] = useState(false);
  const [stockFilter, setStockFilter] = useState<'all' | 'in_stock' | 'out_of_stock'>('all');

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(0);
    }, 400);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => { setPage(0); }, [selectedCategory]);
  useEffect(() => { setPage(0); }, [stockFilter]);

  /* 1a) Accurate inventory summary from dedicated API (all SKUs) */
  const { data: summaryData, isLoading: summaryLoading } = useQuery({
    queryKey: ['uc-inventory-summary'],
    queryFn: async () => {
      const res = await ucCatalog.getInventorySummary();
      return res.data;
    },
    staleTime: 15 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    refetchOnWindowFocus: false,
  });

  /* 2) Paginated catalog */
  const needsInventory = stockFilter !== 'all';
  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ['uc-catalog', page, debouncedSearch, selectedCategory, stockFilter],
    queryFn: async () => {
      const response = await ucCatalog.searchItems({
        displayStart: page * PAGE_SIZE,
        displayLength: PAGE_SIZE,
        getInventorySnapshot: needsInventory,
        keyword: (debouncedSearch || selectedCategory) || undefined,
        stockFilter: stockFilter,
      });
      return response.data;
    },
    staleTime: 2 * 60 * 1000,
    placeholderData: (prev: any) => prev,
  });

  /* derived data */
  const items = useMemo(() => {
    return (data?.elements || []).map((item: any) => {
      const snap = item.inventorySnapshots?.[0];
      return {
        skuCode: item.skuCode || '-',
        name: item.name || '-',
        description: item.description || '',
        categoryName: item.categoryName || '-',
        categoryCode: item.categoryCode || '',
        color: item.color || '-',
        size: item.size || '-',
        brand: item.brand || '-',
        price: item.price || 0,
        hsnCode: item.hsnCode || '-',
        weight: item.weight || 0,
        enabled: item.enabled,
        ean: item.ean || item.scanIdentifier || '-',
        inventory: snap?.inventory ?? snap?.goodInventory ?? 0,
      };
    });
  }, [data]);

  const totalRecords = data?.totalRecords || 0;
  const totalPages = Math.ceil(totalRecords / PAGE_SIZE);
  const currentPage = page + 1;

  /* accurate stats from inventory summary API (DB snapshot exactly matches UC export rows) */
  const accurateStats = useMemo(() => {
    if (!summaryData?.successful) return null;
    return {
      totalCatalog: summaryData.totalSKUs ?? summaryData.totalProducts ?? 0,
      enabled: summaryData.activeSKUs ?? 0,
      facilitySKUs: summaryData.facilitySKUs ?? 0,
      inStock: summaryData.skusWithStock ?? 0,
      outOfStock: summaryData.skusOutOfStock ?? 0,
      totalInventory: summaryData.totalRealInventory ?? 0,
      blocked: summaryData.totalVirtualInventory ?? 0,
      outOfStockPercent: summaryData.outOfStockPercent ?? 0,
      totalStockValue: summaryData.totalStockValue ?? 0,
      categories: (summaryData.categories ?? []) as { name: string; skus: number; inventory: number; inStock: number; outOfStock: number }[],
    };
  }, [summaryData]);

  const categories = accurateStats?.categories ?? [];

  /* RENDER */
  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">
          Product Master Data
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          {fmt(accurateStats?.totalCatalog || totalRecords)} SKUs across {categories.length} categories
          <span className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
            Anthrilo
          </span>
        </p>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3">
        {[
          { label: 'Total Catalog', value: accurateStats ? fmt(accurateStats.totalCatalog) : (summaryLoading ? '…' : fmt(totalRecords)), icon: '📦', bg: 'bg-blue-50 dark:bg-blue-950/30', ring: 'ring-blue-200/50 dark:ring-blue-800/30' },
          { label: 'Facility SKUs', value: accurateStats ? fmt(accurateStats.facilitySKUs) : (summaryLoading ? '…' : '-'), icon: '🏭', bg: 'bg-cyan-50 dark:bg-cyan-950/30', ring: 'ring-cyan-200/50 dark:ring-cyan-800/30' },
          { label: 'In Stock', value: accurateStats ? fmt(accurateStats.inStock) : (summaryLoading ? '…' : '-'), icon: '✅', bg: 'bg-green-50 dark:bg-green-950/30', ring: 'ring-green-200/50 dark:ring-green-800/30' },
          { label: 'Out of Stock', value: accurateStats ? `${fmt(accurateStats.outOfStock)} (${accurateStats.outOfStockPercent}%)` : (summaryLoading ? '…' : '-'), icon: '⚠️', bg: 'bg-rose-50 dark:bg-rose-950/30', ring: 'ring-rose-200/50 dark:ring-rose-800/30' },
          { label: 'Total Inventory', value: accurateStats ? fmt(accurateStats.totalInventory) : (summaryLoading ? '…' : '-'), icon: '📊', bg: 'bg-violet-50 dark:bg-violet-950/30', ring: 'ring-violet-200/50 dark:ring-violet-800/30' },
          { label: 'Enabled SKUs', value: accurateStats ? fmt(accurateStats.enabled) : (summaryLoading ? '…' : '-'), icon: '🔓', bg: 'bg-emerald-50 dark:bg-emerald-950/30', ring: 'ring-emerald-200/50 dark:ring-emerald-800/30' },
          { label: 'Categories', value: summaryLoading ? '…' : categories.length.toString(), icon: '🏷️', bg: 'bg-indigo-50 dark:bg-indigo-950/30', ring: 'ring-indigo-200/50 dark:ring-indigo-800/30' },
        ].map((s) => (
          <div key={s.label}
            className={`relative overflow-hidden rounded-2xl ring-1 ${s.ring} ${s.bg} p-4
              hover:shadow-md hover:-translate-y-0.5 transition-all duration-200`}>
            <div className="flex items-start justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">{s.label}</p>
                <p className="text-xl font-extrabold text-slate-900 dark:text-white mt-1 tabular-nums">
                  {s.value}
                  {summaryLoading && s.value === '…' && (
                    <span className="ml-1 inline-block w-2.5 h-2.5 border-2 border-primary-400 border-t-transparent rounded-full animate-spin align-middle" />
                  )}
                </p>
              </div>
              <span className="text-xl leading-none">{s.icon}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Search & Category Bar */}
      <div className="rounded-2xl border border-slate-200/60 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
        <div className="flex gap-3 items-center flex-wrap">
          {/* Stock filter pills */}
          <div className="flex gap-1 bg-slate-100 dark:bg-slate-800 rounded-xl p-1">
            {([
              { key: 'all' as const, label: 'All' },
              { key: 'in_stock' as const, label: 'In Stock' },
              { key: 'out_of_stock' as const, label: 'Out of Stock' },
            ]).map((f) => (
              <button key={f.key} onClick={() => setStockFilter(f.key)}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${stockFilter === f.key
                  ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
                  }`}>
                {f.label}
              </button>
            ))}
          </div>

          {/* Search */}
          <div className="relative flex-1 min-w-[220px]">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Search SKU, product name, category, brand…"
              className="w-full pl-10 pr-4 py-2.5 rounded-xl text-sm border border-slate-200 dark:border-slate-700
                bg-slate-50 dark:bg-slate-800/60 text-slate-900 dark:text-slate-100
                placeholder:text-slate-400 dark:placeholder:text-slate-500
                focus:outline-none focus:ring-2 focus:ring-primary-500/30 focus:border-primary-400 transition-all"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setSelectedCategory(null); }}
            />
            {search && (
              <button onClick={() => setSearch('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          {/* Category toggle */}
          <button
            onClick={() => setShowCategories(!showCategories)}
            className={`inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${showCategories || selectedCategory
              ? 'bg-primary-600 text-white shadow-sm shadow-primary-600/25'
              : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
          >
            <span className="text-base">🏷️</span>
            {selectedCategory || 'Categories'}
            {selectedCategory && (
              <svg className="w-3.5 h-3.5 ml-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 9l-7 7-7-7" />
              </svg>
            )}
          </button>

          {selectedCategory && (
            <button
              onClick={() => { setSelectedCategory(null); setSearch(''); }}
              className="px-3 py-2.5 rounded-xl text-sm font-medium bg-rose-50 dark:bg-rose-900/20 text-rose-600 dark:text-rose-400
                hover:bg-rose-100 dark:hover:bg-rose-900/30 transition-colors"
            >
              ✕ Clear
            </button>
          )}

          {/* Page info */}
          <span className="text-xs text-slate-400 dark:text-slate-500 whitespace-nowrap ml-auto tabular-nums">
            {fmt(totalRecords)} results · Page {currentPage}/{totalPages || 1}
            {isFetching && !isLoading && (
              <span className="ml-1.5 inline-block w-3 h-3 border-2 border-primary-400 border-t-transparent rounded-full animate-spin" />
            )}
          </span>
        </div>

        {/* Category Chips */}
        {showCategories && categories.length > 0 && (
          <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800">
            <div className="flex flex-wrap gap-2 max-h-52 overflow-y-auto pr-1">
              <button
                onClick={() => { setSelectedCategory(null); setSearch(''); setShowCategories(false); }}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${!selectedCategory
                  ? 'bg-primary-600 text-white shadow-sm'
                  : 'bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-700'
                  }`}
              >
                All ({fmt(accurateStats?.totalCatalog || totalRecords)})
              </button>
              {categories.map((cat) => (
                <button
                  key={cat.name}
                  onClick={() => {
                    setSelectedCategory(cat.name === selectedCategory ? null : cat.name);
                    setSearch('');
                    setShowCategories(false);
                  }}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${selectedCategory === cat.name
                    ? 'bg-primary-600 text-white shadow-sm'
                    : 'bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700 hover:border-primary-300 dark:hover:border-primary-700 hover:bg-primary-50 dark:hover:bg-primary-950/20'
                    }`}
                >
                  {cat.name}
                  <span className="ml-1 opacity-50">({cat.skus})</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-2xl border border-rose-200 dark:border-rose-800/50 bg-rose-50 dark:bg-rose-900/20 p-4">
          <p className="text-sm text-rose-600 dark:text-rose-400">
            <span className="font-semibold">Error:</span> {(error as any)?.message || 'Failed to load catalog'}
          </p>
        </div>
      )}

      {/* Product Table */}
      <div className="rounded-2xl border border-slate-200/60 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
        {/* Table header bar */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100 dark:border-slate-800">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
            Product Catalog
            {selectedCategory && (
              <span className="text-xs font-medium px-2.5 py-0.5 rounded-lg bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400">
                📂 {selectedCategory}
              </span>
            )}
          </h2>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Synced
            </span>
          </div>
        </div>

        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="w-10 h-10 border-[3px] border-slate-200 dark:border-slate-700 border-t-primary-500 rounded-full animate-spin" />
            <p className="mt-4 text-sm text-slate-400">Fetching product catalog…</p>
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-20">
            <div className="text-4xl mb-3">📭</div>
            <p className="text-sm text-slate-500 dark:text-slate-400">No products found for this search.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr className="bg-slate-50/70 dark:bg-slate-800/40">
                  {[...(needsInventory ? ['Stock'] : []), 'SKU Code', 'Product Name', 'Category', 'Color', 'Size', 'Brand', 'IN Stock', 'MRP', 'Weight', 'Status'].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100/80 dark:divide-slate-800/60">
                {items.map((item: any, i: number) => (
                  <tr key={item.skuCode + i}
                    className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors duration-100">
                    {/* Stock (shown when filter active) */}
                    {needsInventory && (
                      <td className="px-4 py-3">
                        <span className={`font-bold text-sm tabular-nums ${item.inventory > 0 ? 'text-emerald-600 dark:text-emerald-400' :
                          'text-rose-600 dark:text-rose-400'
                          }`}>
                          {item.inventory}
                        </span>
                      </td>
                    )}
                    {/* SKU */}
                    <td className="px-4 py-3">
                      <span className="font-mono text-xs font-bold text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/20 px-2 py-0.5 rounded-md">
                        {item.skuCode}
                      </span>
                    </td>
                    {/* Product Name */}
                    <td className="px-4 py-3 max-w-[260px]">
                      <p className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">{item.name}</p>
                      {item.description && item.description !== '-' && (
                        <p className="text-[11px] text-slate-400 dark:text-slate-500 truncate mt-0.5">{item.description}</p>
                      )}
                    </td>
                    {/* Category */}
                    <td className="px-4 py-3">
                      <button
                        onClick={() => { setSelectedCategory(item.categoryName); setSearch(''); }}
                        className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold
                          bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400
                          hover:bg-indigo-100 dark:hover:bg-indigo-900/40 transition-colors cursor-pointer"
                      >
                        {item.categoryName}
                      </button>
                    </td>
                    {/* Color */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <span className="w-3 h-3 rounded-full border border-slate-200 dark:border-slate-600 flex-shrink-0"
                          style={{ backgroundColor: item.color !== '-' ? item.color.toLowerCase().replace(/\s+/g, '') : '#94a3b8' }} />
                        <span className="text-xs text-slate-600 dark:text-slate-400">{item.color}</span>
                      </div>
                    </td>
                    {/* Size */}
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-[11px] font-semibold text-slate-600 dark:text-slate-400">
                        {item.size}
                      </span>
                    </td>
                    {/* Brand */}
                    <td className="px-4 py-3 text-xs font-medium text-slate-700 dark:text-slate-300">{item.brand}</td>
                    {/* IN Stock */}
                    <td className="px-4 py-3">
                      <span className={`text-sm font-bold tabular-nums ${item.inventory > 0
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : 'text-rose-600 dark:text-rose-400'}`}>
                          {fmt(item.inventory)}
                      </span>
                    </td>
                    {/* MRP */}
                    <td className="px-4 py-3">
                      <span className="text-sm font-bold text-slate-900 dark:text-white tabular-nums">{inr(item.price)}</span>
                    </td>
                    {/* Weight */}
                    <td className="px-4 py-3 text-xs text-slate-400 tabular-nums">
                      {item.weight > 0 ? `${item.weight}g` : '-'}
                    </td>
                    {/* Status */}
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold ${item.enabled
                        ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400'
                        : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-500'
                        }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${item.enabled ? 'bg-emerald-500' : 'bg-slate-400'}`} />
                        {item.enabled ? 'Active' : 'Off'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <button disabled={page <= 0} onClick={() => setPage(page - 1)}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium
              bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800
              text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800
              disabled:opacity-40 disabled:pointer-events-none transition-all shadow-sm">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Previous
          </button>

          <div className="flex items-center gap-1">
            {(() => {
              const pages: (number | '...')[] = [];
              if (totalPages <= 7) {
                for (let i = 1; i <= totalPages; i++) pages.push(i);
              } else {
                pages.push(1);
                if (currentPage > 3) pages.push('...');
                for (let i = Math.max(2, currentPage - 1); i <= Math.min(totalPages - 1, currentPage + 1); i++) pages.push(i);
                if (currentPage < totalPages - 2) pages.push('...');
                pages.push(totalPages);
              }
              return pages.map((p, idx) =>
                p === '...' ? (
                  <span key={`dots-${idx}`} className="px-1 text-slate-400 text-xs">…</span>
                ) : (
                  <button key={p} onClick={() => setPage((p as number) - 1)}
                    className={`min-w-[32px] h-8 rounded-lg text-xs font-semibold transition-all ${p === currentPage
                      ? 'bg-primary-600 text-white shadow-sm shadow-primary-600/25'
                      : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                      }`}>
                    {p}
                  </button>
                )
              );
            })()}
          </div>

          <button disabled={page >= totalPages - 1} onClick={() => setPage(page + 1)}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium
              bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800
              text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800
              disabled:opacity-40 disabled:pointer-events-none transition-all shadow-sm">
            Next
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      )}

      {/* Category Distribution Grid */}
      {categories.length > 0 && (
        <div className="rounded-2xl border border-slate-200/60 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
              📊 Category Distribution
              <span className="text-[11px] font-normal text-slate-400 dark:text-slate-500">
                ({categories.length} categories · top {Math.min(20, categories.length)} shown)
              </span>
            </h2>
            {accurateStats && (
              <span className="text-[11px] text-slate-400 tabular-nums">
                {fmt(accurateStats.totalCatalog)} total SKUs
              </span>
            )}
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {categories.slice(0, 20).map((cat) => {
              const totalInv = accurateStats?.totalInventory || categories.reduce((s: number, c: any) => s + c.inventory, 0);
              const pct = totalInv > 0 ? (cat.inventory / totalInv) * 100 : 0;
              return (
                <button
                  key={cat.name}
                  onClick={() => { setSelectedCategory(cat.name); setSearch(''); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
                  className="group relative p-3 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200/60 dark:border-slate-700/60
                    hover:border-primary-300 dark:hover:border-primary-700 hover:shadow-md hover:-translate-y-0.5
                    transition-all duration-200 text-left overflow-hidden"
                >
                  <p className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 truncate group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">
                    {cat.name}
                  </p>
                  <p className="text-lg font-extrabold text-slate-900 dark:text-white mt-1 tabular-nums">
                    {fmt(cat.inventory)}
                    <span className="text-[10px] font-medium text-slate-400 ml-1">units</span>
                  </p>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-[10px] text-slate-400 tabular-nums">{cat.skus} SKUs</span>
                    <span className="text-[10px] font-semibold text-primary-600 dark:text-primary-400 tabular-nums">{pct.toFixed(1)}%</span>
                  </div>
                  <div className="flex items-center gap-2 mt-1.5">
                    <span className="text-[10px] text-emerald-600 dark:text-emerald-400 tabular-nums">{fmt(cat.inStock)} in</span>
                    <span className="text-[10px] text-rose-500 dark:text-rose-400 tabular-nums">{fmt(cat.outOfStock)} out</span>
                  </div>
                  {/* Progress bar */}
                  <div className="w-full h-1 bg-slate-200 dark:bg-slate-700 rounded-full mt-2 overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-primary-400 to-primary-600 rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(pct, 100)}%` }} />
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
