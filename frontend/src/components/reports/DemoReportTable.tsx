'use client';

import { useMemo, useState, useEffect } from 'react';
import { ChevronUp, ChevronDown } from 'lucide-react';
import type { SalesActivityRow } from './SizeWiseReportTable';

interface DemoReportRow {
    item_sku_code: string;
    name: string;
    type: string;
    title_group_key: string;
    tags: string;
    size: string;
    mrp: number;
    cost: number;
    sale_size_wise: number;
    return_size_wise: number;
    cancelled_size_wise: number;
    net_sale_size_wise: number;
    net_sale_amount_size_wise: number;
    sale_style_wise: number;
    return_style_wise: number;
    cancelled_style_wise: number;
    net_sale_style_wise: number;
    net_sale_amount_style_wise: number;
    good_inventory_size_wise: number;
    good_inventory_style_wise: number;
    virtual_inventory_size_wise: number;
    virtual_inventory_style_wise: number;
}

interface Props {
    data: SalesActivityRow[];
    selectedChannelLabel: string;
}

type SortKey = keyof DemoReportRow;
type SortDir = 'asc' | 'desc';

function toNum(value: unknown): number {
    const parsed = Number(value || 0);
    return Number.isFinite(parsed) ? parsed : 0;
}

function formatCurrency(value: number): string {
    return `Rs ${toNum(value).toLocaleString('en-IN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}`;
}

function normalizeText(value: unknown): string {
    return String(value || '').trim();
}

function isPlaceholder(value: string): boolean {
    const upper = value.toUpperCase();
    return !value || upper === 'UNKNOWN' || (value.startsWith('{') && value.endsWith('}'));
}

function deriveStyleKey(itemTypeName: string, itemTypeSize: string): string {
    const name = normalizeText(itemTypeName);
    const size = normalizeText(itemTypeSize);
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
        if (style) return style;
    }

    return name;
}

function normalizeSizeDisplay(value: unknown): string {
    const raw = normalizeText(value);
    if (!raw) return 'UNKNOWN';

    const compact = raw.replace(/\s*-\s*/g, '-');
    const parts = compact.split('-').map((p) => p.trim()).filter(Boolean);

    if (parts.length >= 2) {
        const head = parts[0];
        const tail = parts.slice(1).join('-').trim();
        const headHasDigit = /\d/.test(head);
        const tailHasDigit = /\d/.test(tail);
        if (!headHasDigit && tailHasDigit) {
            return tail || raw;
        }
    }

    return raw;
}

function escapeCsvCell(value: string): string {
    const escaped = value.replace(/"/g, '""');
    return /[",\n]/.test(escaped) ? `"${escaped}"` : escaped;
}

export default function DemoReportTable({ data, selectedChannelLabel }: Props) {
    const [sortKey, setSortKey] = useState<SortKey>('item_sku_code');
    const [sortDir, setSortDir] = useState<SortDir>('asc');
    const [page, setPage] = useState(1);
    const PAGE_SIZE = 50;

    const rows = useMemo(() => {
        const sizeMap: Record<string, DemoReportRow> = {};

        for (const row of data) {
            const sku = normalizeText(row.item_sku_code) || 'UNKNOWN';
            const itemTypeName = normalizeText(row.item_type_name);
            const name = itemTypeName || 'UNKNOWN';
            const size = normalizeSizeDisplay(row.item_type_size || row.size) || 'UNKNOWN';
            const styleName = normalizeText((row as any).style_name);
            const titleGroupKey = !isPlaceholder(styleName)
                ? styleName
                : !isPlaceholder(name)
                    ? deriveStyleKey(name, size)
                    : 'UNKNOWN';
            const key = `${sku}||${size}`;

            if (!sizeMap[key]) {
                const mrp = toNum((row as any).mrp);
                sizeMap[key] = {
                    item_sku_code: sku,
                    name,
                    type: normalizeText((row as any).type) || 'UNKNOWN',
                    title_group_key: titleGroupKey,
                    tags: String((row as any).tags || '').trim(),
                    size,
                    mrp,
                    cost: 0,
                    sale_size_wise: 0,
                    return_size_wise: 0,
                    cancelled_size_wise: 0,
                    net_sale_size_wise: 0,
                    net_sale_amount_size_wise: 0,
                    sale_style_wise: 0,
                    return_style_wise: 0,
                    cancelled_style_wise: 0,
                    net_sale_style_wise: 0,
                    net_sale_amount_style_wise: 0,
                    good_inventory_size_wise: 0,
                    good_inventory_style_wise: 0,
                    virtual_inventory_size_wise: 0,
                    virtual_inventory_style_wise: 0,
                };
            }

            const target = sizeMap[key];
            target.sale_size_wise += toNum(row.total_sale_qty);
            target.return_size_wise += toNum(row.return_qty);
            target.cancelled_size_wise += toNum(row.cancel_qty);
            target.net_sale_size_wise += toNum(row.net_sale);
            target.net_sale_amount_size_wise += toNum((row as any).net_sale_amount);
            target.good_inventory_size_wise = Math.max(target.good_inventory_size_wise, toNum((row as any).stock_good));
            target.virtual_inventory_size_wise = Math.max(target.virtual_inventory_size_wise, toNum((row as any).stock_virtual));

            const rowMrp = toNum((row as any).mrp);
            if (target.mrp <= 0 && rowMrp > 0) target.mrp = rowMrp;
            const rowCost = toNum((row as any).cost);
            if (rowCost > 0) target.cost = rowCost;
            if (!target.tags) {
                target.tags = String((row as any).tags || '').trim();
            }
            if (!target.name || target.name === 'UNKNOWN') {
                target.name = name;
            }
            const itemType = normalizeText((row as any).type);
            if ((!target.type || target.type === 'UNKNOWN') && itemType) {
                target.type = itemType;
            }
            if (target.title_group_key === 'UNKNOWN' && titleGroupKey !== 'UNKNOWN') {
                target.title_group_key = titleGroupKey;
            }
        }

        const sizeRows = Object.values(sizeMap);

        const styleMap: Record<
            string,
            {
                sale: number;
                ret: number;
                cancelled: number;
                net: number;
                netAmount: number;
                goodInv: number;
                virtualInv: number;
            }
        > = {};
        const styleInventorySkuSeen: Record<string, Set<string>> = {};

        for (const row of sizeRows) {
            const styleKey = row.title_group_key || 'UNKNOWN';
            if (!styleMap[styleKey]) {
                styleMap[styleKey] = {
                    sale: 0,
                    ret: 0,
                    cancelled: 0,
                    net: 0,
                    netAmount: 0,
                    goodInv: 0,
                    virtualInv: 0,
                };
                styleInventorySkuSeen[styleKey] = new Set<string>();
            }

            styleMap[styleKey].sale += row.sale_size_wise;
            styleMap[styleKey].ret += row.return_size_wise;
            styleMap[styleKey].cancelled += row.cancelled_size_wise;
            styleMap[styleKey].net += row.net_sale_size_wise;
            styleMap[styleKey].netAmount += row.net_sale_amount_size_wise;

            const styleSkuKey = `${styleKey}::${row.item_sku_code || 'UNKNOWN'}`;
            if (!styleInventorySkuSeen[styleKey].has(styleSkuKey)) {
                styleInventorySkuSeen[styleKey].add(styleSkuKey);
                styleMap[styleKey].goodInv += row.good_inventory_size_wise;
                styleMap[styleKey].virtualInv += row.virtual_inventory_size_wise;
            }
        }

        for (const row of sizeRows) {
            const style = styleMap[row.title_group_key || 'UNKNOWN'];
            row.sale_style_wise = style.sale;
            row.return_style_wise = style.ret;
            row.cancelled_style_wise = style.cancelled;
            row.net_sale_style_wise = style.net;
            row.net_sale_amount_style_wise = style.netAmount;
            row.good_inventory_style_wise = style.goodInv;
            row.virtual_inventory_style_wise = style.virtualInv;
        }

        return sizeRows;
    }, [data]);

    const columns = useMemo(
        () => [
            { key: 'item_sku_code', label: 'Item SKU' },
            { key: 'name', label: 'Name' },
            { key: 'type', label: 'Type' },
            { key: 'tags', label: 'Tags' },
            { key: 'size', label: 'Size' },
            { key: 'mrp', label: 'MRP', numeric: true },
            { key: 'cost', label: 'COST', numeric: true },
            { key: 'sale_size_wise', label: 'Sale (Size-wise)', numeric: true },
            { key: 'return_size_wise', label: 'Return (Size-wise)', numeric: true },
            { key: 'cancelled_size_wise', label: 'Cancelled (Size-wise)', numeric: true },
            { key: 'net_sale_size_wise', label: 'Net Sale (Size-wise)', numeric: true },
            { key: 'net_sale_amount_size_wise', label: 'Net Sale in Amount (Size-wise)', numeric: true },
            { key: 'sale_style_wise', label: 'Sale (Style-wise)', numeric: true },
            { key: 'return_style_wise', label: 'Return (Style-wise)', numeric: true },
            { key: 'cancelled_style_wise', label: 'Cancelled (Style-wise)', numeric: true },
            { key: 'net_sale_style_wise', label: 'Net Sale (Style-wise)', numeric: true },
            { key: 'net_sale_amount_style_wise', label: 'Net Sale in Amount (Style-wise)', numeric: true },
            { key: 'good_inventory_size_wise', label: 'Good Inventory (Size-wise)', numeric: true },
            { key: 'good_inventory_style_wise', label: 'Good Inventory (Style-wise)', numeric: true },
            { key: 'virtual_inventory_size_wise', label: 'Virtual Inventory (Size-wise)', numeric: true },
            { key: 'virtual_inventory_style_wise', label: 'Virtual Inventory (Style-wise)', numeric: true },
        ] as Array<{ key: SortKey; label: string; numeric?: boolean }>,
        []
    );

    const downloadCsv = () => {
        const headers = columns.map((col) => col.label);
        const moneyCols = new Set<SortKey>([
            'net_sale_amount_size_wise',
            'net_sale_amount_style_wise',
            'mrp',
            'cost',
        ]);

        const lines = [headers.map(escapeCsvCell).join(',')];
        for (const row of sorted) {
            const values = columns.map((col) => {
                const raw = row[col.key];
                if (raw === null || raw === undefined) return '';
                if (typeof raw === 'number') {
                    const formatted = moneyCols.has(col.key) ? toNum(raw).toFixed(2) : String(toNum(raw));
                    return escapeCsvCell(formatted);
                }
                return escapeCsvCell(String(raw));
            });
            lines.push(values.join(','));
        }

        const blob = new Blob(['\uFEFF' + lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `sales-activity-report-${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    const sorted = useMemo(() => {
        return [...rows].sort((a, b) => {
            const aVal = a[sortKey];
            const bVal = b[sortKey];

            if (typeof aVal === 'number' && typeof bVal === 'number') {
                return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
            }

            return sortDir === 'asc'
                ? String(aVal ?? '').localeCompare(String(bVal ?? ''))
                : String(bVal ?? '').localeCompare(String(aVal ?? ''));
        });
    }, [rows, sortKey, sortDir]);

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

        let saleStyle = 0;
        let retStyle = 0;
        let cancelledStyle = 0;
        let netStyle = 0;
        let netAmountStyle = 0;
        let goodInvStyle = 0;
        let virtualInvStyle = 0;

        for (const row of sorted) {
            sale += row.sale_size_wise;
            ret += row.return_size_wise;
            cancelled += row.cancelled_size_wise;
            net += row.net_sale_size_wise;
            netAmount += row.net_sale_amount_size_wise;
            goodInv += row.good_inventory_size_wise;
            virtualInv += row.virtual_inventory_size_wise;
        }

        const styleSeen = new Set<string>();
        for (const row of sorted) {
            const style = row.title_group_key || 'UNKNOWN';
            if (styleSeen.has(style)) continue;
            styleSeen.add(style);
            saleStyle += row.sale_style_wise;
            retStyle += row.return_style_wise;
            cancelledStyle += row.cancelled_style_wise;
            netStyle += row.net_sale_style_wise;
            netAmountStyle += row.net_sale_amount_style_wise;
            goodInvStyle += row.good_inventory_style_wise;
            virtualInvStyle += row.virtual_inventory_style_wise;
        }

        return {
            saleSize: sale,
            retSize: ret,
            cancelledSize: cancelled,
            netSize: net,
            netAmountSize: netAmount,
            saleStyle,
            retStyle,
            cancelledStyle,
            netStyle,
            netAmountStyle,
            goodInvSize: goodInv,
            goodInvStyle,
            virtualInvSize: virtualInv,
            virtualInvStyle,
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

    if (!data.length) {
        return (
            <div className="space-y-3">
                <div className="flex flex-col gap-1">
                    <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">
                        Demo Report <span className="text-primary-500">{'->'}</span>
                    </h3>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                        Channel: {selectedChannelLabel} | Inventory shown from current snapshot
                    </p>
                </div>
                <div className="rounded-xl border border-slate-200 dark:border-slate-700 p-6 text-sm text-slate-500 dark:text-slate-400 text-center">
                    No demo report rows yet. Select date/channel and click Generate Report.
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-col gap-1">
                    <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">
                        Demo Report <span className="text-primary-500">{'->'}</span>
                    </h3>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                        Channel: {selectedChannelLabel} | Inventory shown from current snapshot
                    </p>
                </div>
                <button
                    type="button"
                    onClick={downloadCsv}
                    className="px-3 py-2 rounded-lg text-xs font-medium bg-slate-900 text-white hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200"
                >
                    Download CSV
                </button>
            </div>

            <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700">
                <table className="w-full text-sm min-w-[2200px]">
                    <thead className="sticky top-0 z-10">
                        <tr className="bg-slate-50 dark:bg-slate-800/80">
                            {columns.map((col) => (
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
                            <tr key={`${row.item_sku_code}||${row.size}`} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                                {columns.map((col) => {
                                    const value = row[col.key];
                                    const numeric = !!col.numeric;
                                    const cls = numeric
                                        ? 'px-4 py-2.5 text-right text-slate-700 dark:text-slate-300'
                                        : 'px-4 py-2.5 text-slate-700 dark:text-slate-300';

                                    if (
                                        col.key === 'net_sale_amount_size_wise' ||
                                        col.key === 'net_sale_amount_style_wise' ||
                                        col.key === 'mrp' ||
                                        col.key === 'cost'
                                    ) {
                                        return (
                                            <td key={col.key} className={cls}>
                                                {formatCurrency(toNum(value))}
                                            </td>
                                        );
                                    }
                                    if (numeric) {
                                        return (
                                            <td key={col.key} className={cls}>
                                                {toNum(value).toLocaleString('en-IN')}
                                            </td>
                                        );
                                    }
                                    return (
                                        <td key={col.key} className={cls}>
                                            {String(value ?? '') || 'UNKNOWN'}
                                        </td>
                                    );
                                })}
                            </tr>
                        ))}
                    </tbody>

                    <tfoot>
                        <tr className="bg-slate-50 dark:bg-slate-800/80 font-semibold text-sm">
                            <td className="px-4 py-3" colSpan={6}>Total</td>
                            <td className="px-4 py-3 text-right">{totals.saleSize.toLocaleString('en-IN')}</td>
                            <td className="px-4 py-3 text-right">{totals.retSize.toLocaleString('en-IN')}</td>
                            <td className="px-4 py-3 text-right">{totals.cancelledSize.toLocaleString('en-IN')}</td>
                            <td className="px-4 py-3 text-right">{totals.netSize.toLocaleString('en-IN')}</td>
                            <td className="px-4 py-3 text-right">{formatCurrency(totals.netAmountSize)}</td>
                            <td className="px-4 py-3 text-right">{totals.saleStyle.toLocaleString('en-IN')}</td>
                            <td className="px-4 py-3 text-right">{totals.retStyle.toLocaleString('en-IN')}</td>
                            <td className="px-4 py-3 text-right">{totals.cancelledStyle.toLocaleString('en-IN')}</td>
                            <td className="px-4 py-3 text-right">{totals.netStyle.toLocaleString('en-IN')}</td>
                            <td className="px-4 py-3 text-right">{formatCurrency(totals.netAmountStyle)}</td>
                            <td className="px-4 py-3 text-right">{totals.goodInvSize.toLocaleString('en-IN')}</td>
                            <td className="px-4 py-3 text-right">{totals.goodInvStyle.toLocaleString('en-IN')}</td>
                            <td className="px-4 py-3 text-right">{totals.virtualInvSize.toLocaleString('en-IN')}</td>
                            <td className="px-4 py-3 text-right">{totals.virtualInvStyle.toLocaleString('en-IN')}</td>
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
        </div>
    );
}
