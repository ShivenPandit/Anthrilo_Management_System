'use client';

import { useMemo, useState, useEffect } from 'react';
import { ChevronUp, ChevronDown } from 'lucide-react';
import type { SalesActivityRow } from './SizeWiseReportTable';

interface DemoReportRow {
    item_sku_code: string;
    name: string;
    type: string;
    item_type_size: string;
    channel: string;
    sale_size_wise: number;
    return_size_wise: number;
    cancelled_size_wise: number;
    net_sale_size_wise: number;
    net_sale_amount_size_wise: number;
    good_inventory_size_wise: number;
    virtual_inventory_size_wise: number;
}

interface Props {
    data: SalesActivityRow[];
    selectedChannel: string;
}

type SortKey = keyof DemoReportRow;
type SortDir = 'asc' | 'desc';

const COLS: { key: SortKey; label: string; numeric?: boolean }[] = [
    { key: 'item_sku_code', label: 'Item SKU' },
    { key: 'name', label: 'Name' },
    { key: 'type', label: 'Type' },
    { key: 'item_type_size', label: 'Item Type Size' },
    { key: 'channel', label: 'Channel' },
    { key: 'sale_size_wise', label: 'Sale (Size-wise)', numeric: true },
    { key: 'return_size_wise', label: 'Return (Size-wise)', numeric: true },
    { key: 'cancelled_size_wise', label: 'Cancelled (Size-wise)', numeric: true },
    { key: 'net_sale_size_wise', label: 'Net Sale (Size-wise)', numeric: true },
    { key: 'net_sale_amount_size_wise', label: 'Net Sale in Amount (Size-wise)', numeric: true },
    { key: 'good_inventory_size_wise', label: 'Good Inventory (Size-wise)', numeric: true },
    { key: 'virtual_inventory_size_wise', label: 'Virtual Inventory (Size-wise)', numeric: true },
];

function deriveType(itemTypeName: string, itemTypeSize: string): string {
    const name = (itemTypeName || '').trim();
    const size = (itemTypeSize || '').trim();
    if (!name) return 'UNKNOWN';

    if (size && size.toUpperCase() !== 'UNKNOWN') {
        const suffix = ` - ${size}`;
        if (name.endsWith(suffix)) {
            const t = name.slice(0, -suffix.length).trim();
            return t || name;
        }
    }

    const idx = name.lastIndexOf(' - ');
    if (idx > 0) {
        const t = name.slice(0, idx).trim();
        return t || name;
    }

    return name;
}

function formatCurrency(value: number): string {
    return `Rs ${Number(value || 0).toLocaleString('en-IN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}`;
}

export default function DemoReportTable({ data, selectedChannel }: Props) {
    const [sortKey, setSortKey] = useState<SortKey>('item_sku_code');
    const [sortDir, setSortDir] = useState<SortDir>('asc');
    const [page, setPage] = useState(1);
    const PAGE_SIZE = 50;

    const grouped = useMemo(() => {
        const map: Record<string, DemoReportRow> = {};

        for (const row of data) {
            const sku = (row.item_sku_code || '').trim();
            const name = (row.item_type_name || '').trim() || 'UNKNOWN';
            const itemTypeSize = (row.item_type_size || row.size || 'UNKNOWN').trim() || 'UNKNOWN';
            const channel = (row.channel || 'UNKNOWN').trim() || 'UNKNOWN';

            const key = `${sku}||${itemTypeSize}||${channel}`;
            if (!map[key]) {
                map[key] = {
                    item_sku_code: sku,
                    name,
                    type: deriveType(name, itemTypeSize),
                    item_type_size: itemTypeSize,
                    channel,
                    sale_size_wise: 0,
                    return_size_wise: 0,
                    cancelled_size_wise: 0,
                    net_sale_size_wise: 0,
                    net_sale_amount_size_wise: 0,
                    good_inventory_size_wise: Number(row.stock_good || 0),
                    virtual_inventory_size_wise: Number(row.stock_virtual || 0),
                };
            }

            map[key].sale_size_wise += Number(row.total_sale_qty || 0);
            map[key].return_size_wise += Number(row.return_qty || 0);
            map[key].cancelled_size_wise += Number(row.cancel_qty || 0);
            map[key].net_sale_size_wise += Number(row.net_sale || 0);
            map[key].net_sale_amount_size_wise += Number(row.net_sale_amount || 0);

            if (!map[key].name || map[key].name === 'UNKNOWN') {
                map[key].name = name;
            }
            if (!map[key].type || map[key].type === 'UNKNOWN') {
                map[key].type = deriveType(name, itemTypeSize);
            }
        }

        return Object.values(map);
    }, [data]);

    const sorted = useMemo(() => {
        return [...grouped].sort((a, b) => {
            const aVal = a[sortKey];
            const bVal = b[sortKey];

            if (typeof aVal === 'number' && typeof bVal === 'number') {
                return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
            }

            return sortDir === 'asc'
                ? String(aVal ?? '').localeCompare(String(bVal ?? ''))
                : String(bVal ?? '').localeCompare(String(aVal ?? ''));
        });
    }, [grouped, sortKey, sortDir]);

    const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
    const paged = useMemo(() => sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE), [sorted, page]);

    useEffect(() => {
        setPage(1);
    }, [data, sortKey, sortDir]);

    const totals = useMemo(() => {
        let sale = 0;
        let ret = 0;
        let cancelled = 0;
        let net = 0;
        let netAmount = 0;
        let goodInv = 0;
        let virtualInv = 0;

        const seenSku = new Set<string>();
        for (const row of sorted) {
            sale += row.sale_size_wise;
            ret += row.return_size_wise;
            cancelled += row.cancelled_size_wise;
            net += row.net_sale_size_wise;
            netAmount += row.net_sale_amount_size_wise;

            if (row.item_sku_code && !seenSku.has(row.item_sku_code)) {
                seenSku.add(row.item_sku_code);
                goodInv += row.good_inventory_size_wise;
                virtualInv += row.virtual_inventory_size_wise;
            }
        }

        return {
            sale,
            ret,
            cancelled,
            net,
            netAmount,
            goodInv,
            virtualInv,
        };
    }, [sorted]);

    const handleSort = (key: SortKey) => {
        if (sortKey === key) {
            setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
        } else {
            setSortKey(key);
            setSortDir('asc');
        }
    };

    return (
        <div className="space-y-3">
            <div className="flex flex-col gap-1">
                <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">
                    Demo Report <span className="text-primary-500">{'->'}</span>
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                    Channel: {selectedChannel === 'ALL' ? 'All Channels' : selectedChannel} | Inventory shown from current snapshot
                </p>
            </div>

            {!data.length ? (
                <div className="rounded-xl border border-slate-200 dark:border-slate-700 p-6 text-sm text-slate-500 dark:text-slate-400 text-center">
                    No demo report rows yet. Select date/channel and click Generate.
                </div>
            ) : (
                <>

                    <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700">
                        <table className="w-full text-sm min-w-[1700px]">
                            <thead className="sticky top-0 z-10">
                                <tr className="bg-slate-50 dark:bg-slate-800/80">
                                    {COLS.map((col) => (
                                        <th
                                            key={col.key}
                                            onClick={() => handleSort(col.key)}
                                            className={`px-4 py-3 font-semibold text-xs uppercase tracking-wider cursor-pointer select-none
                    text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700
                    hover:text-slate-700 dark:hover:text-slate-200 transition-colors ${col.numeric ? 'text-right' : 'text-left'}`}
                                        >
                                            <span className="inline-flex items-center gap-1">
                                                {col.label}
                                                {sortKey === col.key && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
                                            </span>
                                        </th>
                                    ))}
                                </tr>
                            </thead>

                            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                                {paged.map((row) => (
                                    <tr key={`${row.item_sku_code}||${row.item_type_size}||${row.channel}`} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                                        <td className="px-4 py-2.5 font-mono text-xs text-slate-700 dark:text-slate-300">{row.item_sku_code || 'UNKNOWN'}</td>
                                        <td className="px-4 py-2.5 text-slate-700 dark:text-slate-300">{row.name || 'UNKNOWN'}</td>
                                        <td className="px-4 py-2.5 text-slate-600 dark:text-slate-400">{row.type || 'UNKNOWN'}</td>
                                        <td className="px-4 py-2.5 text-slate-600 dark:text-slate-400">{row.item_type_size || 'UNKNOWN'}</td>
                                        <td className="px-4 py-2.5 text-slate-600 dark:text-slate-400">{row.channel || 'UNKNOWN'}</td>
                                        <td className="px-4 py-2.5 text-right text-slate-800 dark:text-slate-200">{row.sale_size_wise.toLocaleString('en-IN')}</td>
                                        <td className="px-4 py-2.5 text-right text-orange-600 dark:text-orange-400">{row.return_size_wise.toLocaleString('en-IN')}</td>
                                        <td className="px-4 py-2.5 text-right text-red-600 dark:text-red-400">{row.cancelled_size_wise.toLocaleString('en-IN')}</td>
                                        <td className="px-4 py-2.5 text-right font-semibold text-emerald-600 dark:text-emerald-400">{row.net_sale_size_wise.toLocaleString('en-IN')}</td>
                                        <td className="px-4 py-2.5 text-right font-medium text-slate-800 dark:text-slate-200">{formatCurrency(row.net_sale_amount_size_wise)}</td>
                                        <td className="px-4 py-2.5 text-right text-slate-600 dark:text-slate-400">{row.good_inventory_size_wise.toLocaleString('en-IN')}</td>
                                        <td className="px-4 py-2.5 text-right text-slate-600 dark:text-slate-400">{row.virtual_inventory_size_wise.toLocaleString('en-IN')}</td>
                                    </tr>
                                ))}
                            </tbody>

                            <tfoot>
                                <tr className="bg-slate-50 dark:bg-slate-800/80 font-semibold text-sm">
                                    <td className="px-4 py-3" colSpan={5}>Total</td>
                                    <td className="px-4 py-3 text-right">{totals.sale.toLocaleString('en-IN')}</td>
                                    <td className="px-4 py-3 text-right text-orange-600 dark:text-orange-400">{totals.ret.toLocaleString('en-IN')}</td>
                                    <td className="px-4 py-3 text-right text-red-600 dark:text-red-400">{totals.cancelled.toLocaleString('en-IN')}</td>
                                    <td className="px-4 py-3 text-right text-emerald-600 dark:text-emerald-400">{totals.net.toLocaleString('en-IN')}</td>
                                    <td className="px-4 py-3 text-right">{formatCurrency(totals.netAmount)}</td>
                                    <td className="px-4 py-3 text-right">{totals.goodInv.toLocaleString('en-IN')}</td>
                                    <td className="px-4 py-3 text-right">{totals.virtualInv.toLocaleString('en-IN')}</td>
                                </tr>
                            </tfoot>
                        </table>
                    </div>

                    <div className="flex items-center justify-between mt-2 text-xs text-slate-500 dark:text-slate-400">
                        <span>{sorted.length} rows | Page {page} of {totalPages}</span>
                        <div className="flex items-center gap-1">
                            <button
                                onClick={() => setPage((p) => Math.max(1, p - 1))}
                                disabled={page <= 1}
                                className="px-2.5 py-1 rounded-md border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                            >
                                Prev
                            </button>
                            {Array.from({ length: totalPages }, (_, i) => i + 1)
                                .filter((p) => p === 1 || p === totalPages || Math.abs(p - page) <= 2)
                                .reduce<(number | string)[]>((acc, p, idx, arr) => {
                                    if (idx > 0 && p - (arr[idx - 1] as number) > 1) acc.push('...');
                                    acc.push(p);
                                    return acc;
                                }, [])
                                .map((p, i) =>
                                    typeof p === 'string' ? (
                                        <span key={`e${i}`} className="px-1">...</span>
                                    ) : (
                                        <button
                                            key={p}
                                            onClick={() => setPage(p)}
                                            className={`px-2.5 py-1 rounded-md border transition-colors ${p === page
                                                    ? 'bg-primary-600 text-white border-primary-600'
                                                    : 'border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800'
                                                }`}
                                        >
                                            {p}
                                        </button>
                                    )
                                )}
                            <button
                                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                                disabled={page >= totalPages}
                                className="px-2.5 py-1 rounded-md border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                            >
                                Next
                            </button>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}
