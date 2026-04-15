'use client';

import { useState, useMemo, useEffect } from 'react';
import { ChevronUp, ChevronDown } from 'lucide-react';

export interface SalesActivityRow {
  item_sku_code: string;
  item_type_name: string;
  size: string;
  item_type_size?: string;
  channel: string;
  total_sale_qty: number;
  cancel_qty: number;
  return_qty: number;
  net_sale: number;
  sale_amount?: number;
  cancel_amount?: number;
  return_amount?: number;
  net_sale_amount?: number;
  stock_good: number;
  stock_virtual: number;
}

interface SizeWiseRow {
  item_sku_code: string;
  item_type_name: string;
  size: string;
  total_sale_qty: number;
  cancel_qty: number;
  return_qty: number;
  net_sale: number;
  stock_good: number;
  stock_virtual: number;
}

interface Props {
  data: SalesActivityRow[];
}

type SortKey = keyof SizeWiseRow;
type SortDir = 'asc' | 'desc';

const COLS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: 'item_sku_code', label: 'Item SKU Code' },
  { key: 'item_type_name', label: 'Item Type Name' },
  { key: 'size', label: 'Size' },
  { key: 'total_sale_qty', label: 'Total Sale Qty', numeric: true },
  { key: 'cancel_qty', label: 'Cancel', numeric: true },
  { key: 'return_qty', label: 'Return', numeric: true },
  { key: 'net_sale', label: 'Net Sale', numeric: true },
  { key: 'stock_good', label: 'Stock in Hand (Good)', numeric: true },
  { key: 'stock_virtual', label: 'Stock in Hand (Virtual)', numeric: true },
];

export default function SizeWiseReportTable({ data }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('item_sku_code');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 50;

  const grouped = useMemo(() => {
    const map: Record<string, SizeWiseRow> = {};
    for (const row of data) {
      const key = `${row.item_sku_code}||${row.size}`;
      if (!map[key]) {
        map[key] = {
          item_sku_code: row.item_sku_code,
          item_type_name: row.item_type_name,
          size: row.size,
          total_sale_qty: 0, cancel_qty: 0, return_qty: 0, net_sale: 0,
          stock_good: row.stock_good, stock_virtual: row.stock_virtual,
        };
      }
      map[key].total_sale_qty += row.total_sale_qty;
      map[key].cancel_qty += row.cancel_qty;
      map[key].return_qty += row.return_qty;
      map[key].net_sale += row.net_sale;
      if (!map[key].item_type_name && row.item_type_name) {
        map[key].item_type_name = row.item_type_name;
      }
    }
    return Object.values(map);
  }, [data]);

  const sorted = useMemo(() => {
    return [...grouped].sort((a, b) => {
      const aVal = a[sortKey] ?? '';
      const bVal = b[sortKey] ?? '';
      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
      }
      return sortDir === 'asc'
        ? String(aVal).localeCompare(String(bVal))
        : String(bVal).localeCompare(String(aVal));
    });
  }, [grouped, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const paged = useMemo(() => sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE), [sorted, page]);

  // Reset page when data or sort changes
  useEffect(() => { setPage(1); }, [data, sortKey, sortDir]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('asc'); }
  };

  const totals = useMemo(() => {
    let total_sale_qty = 0, cancel_qty = 0, return_qty = 0, net_sale = 0;
    for (const r of sorted) {
      total_sale_qty += r.total_sale_qty;
      cancel_qty += r.cancel_qty;
      return_qty += r.return_qty;
      net_sale += r.net_sale;
    }
    return { total_sale_qty, cancel_qty, return_qty, net_sale };
  }, [sorted]);

  if (!data.length) return null;

  return (
    <div>
      <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-3">
        Size Wise <span className="text-primary-500">→</span>
      </h3>
      <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10">
            <tr className="bg-slate-50 dark:bg-slate-800/80">
              {COLS.map((col) => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  className={`px-4 py-3 font-semibold text-xs uppercase tracking-wider cursor-pointer select-none
                    text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700
                    hover:text-slate-700 dark:hover:text-slate-200 transition-colors
                    ${col.numeric ? 'text-right' : 'text-left'}`}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.label}
                    {sortKey === col.key && (sortDir === 'asc'
                      ? <ChevronUp className="w-3 h-3" />
                      : <ChevronDown className="w-3 h-3" />)}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {paged.map((row) => (
              <tr key={`${row.item_sku_code}||${row.size}`} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                <td className="px-4 py-2.5 font-mono text-xs text-slate-700 dark:text-slate-300">{row.item_sku_code || '—'}</td>
                <td className="px-4 py-2.5 text-slate-700 dark:text-slate-300">{row.item_type_name || '—'}</td>
                <td className="px-4 py-2.5 text-slate-600 dark:text-slate-400">{row.size || '—'}</td>
                <td className="px-4 py-2.5 text-right font-medium text-slate-800 dark:text-slate-200">{row.total_sale_qty}</td>
                <td className="px-4 py-2.5 text-right text-red-600 dark:text-red-400">{row.cancel_qty}</td>
                <td className="px-4 py-2.5 text-right text-orange-600 dark:text-orange-400">{row.return_qty}</td>
                <td className="px-4 py-2.5 text-right font-semibold text-emerald-600 dark:text-emerald-400">{row.net_sale}</td>
                <td className="px-4 py-2.5 text-right text-slate-600 dark:text-slate-400">{row.stock_good}</td>
                <td className="px-4 py-2.5 text-right text-slate-600 dark:text-slate-400">{row.stock_virtual}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-slate-50 dark:bg-slate-800/80 font-semibold text-sm">
              <td className="px-4 py-3" colSpan={3}>Total</td>
              <td className="px-4 py-3 text-right">{totals.total_sale_qty}</td>
              <td className="px-4 py-3 text-right text-red-600 dark:text-red-400">{totals.cancel_qty}</td>
              <td className="px-4 py-3 text-right text-orange-600 dark:text-orange-400">{totals.return_qty}</td>
              <td className="px-4 py-3 text-right text-emerald-600 dark:text-emerald-400">{totals.net_sale}</td>
              <td className="px-4 py-3 text-right" colSpan={2}></td>
            </tr>
          </tfoot>
        </table>
      </div>
      <div className="flex items-center justify-between mt-3 text-xs text-slate-500 dark:text-slate-400">
        <span>{sorted.length} rows · Page {page} of {totalPages}</span>
        <div className="flex items-center gap-1">
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}
            className="px-2.5 py-1 rounded-md border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">Prev</button>
          {Array.from({ length: totalPages }, (_, i) => i + 1)
            .filter(p => p === 1 || p === totalPages || Math.abs(p - page) <= 2)
            .reduce<(number | string)[]>((acc, p, idx, arr) => {
              if (idx > 0 && p - (arr[idx - 1] as number) > 1) acc.push('...');
              acc.push(p);
              return acc;
            }, [])
            .map((p, i) =>
              typeof p === 'string'
                ? <span key={`e${i}`} className="px-1">…</span>
                : <button key={p} onClick={() => setPage(p)}
                    className={`px-2.5 py-1 rounded-md border transition-colors ${
                      p === page
                        ? 'bg-primary-600 text-white border-primary-600'
                        : 'border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800'
                    }`}>{p}</button>
            )}
          <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
            className="px-2.5 py-1 rounded-md border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">Next</button>
        </div>
      </div>
    </div>
  );
}
