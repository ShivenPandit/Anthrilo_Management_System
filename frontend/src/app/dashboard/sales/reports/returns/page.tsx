'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { PageHeader, StatCard } from '@/components/ui/Common';
import { ucSales } from '@/lib/api/uc';

export default function DailyReturnReportPage() {
    const [reportDate, setReportDate] = useState<string>(() => {
        const yesterday = new Date();
        yesterday.setDate(yesterday.getDate() - 1);
        return yesterday.toISOString().split('T')[0];
    });
    const [returnType, setReturnType] = useState<string>('ALL');
    const [showReport, setShowReport] = useState(false);

    const { data, isLoading, refetch } = useQuery({
        queryKey: ['daily-return-report', reportDate, returnType],
        queryFn: async () => {
            const response = await ucSales.getDailyReturnReport(reportDate, returnType);
            return response.data;
        },
        enabled: showReport,
        staleTime: 5 * 60 * 1000,
    });

    const handleGenerate = () => { setShowReport(true); refetch(); };

    const handleDownloadCSV = () => {
        if (!data?.by_channel) return;
        const headers = ['Channel', 'Returns', 'Items', 'Value (₹)', 'RTO', 'CIR'];
        const rows = data.by_channel.map((ch: any) => [ch.channel, ch.returns, ch.items, ch.value, ch.rto, ch.cir]);
        rows.push(['TOTAL', data.totals.total_returns, data.totals.total_items, data.totals.total_value, data.totals.rto_count, data.totals.cir_count]);
        const csv = [headers.join(','), ...rows.map((r: any[]) => r.join(','))].join('\n');
        const blob = new Blob([csv], { type: 'text/csv' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `return-report-${reportDate}-${returnType}.csv`;
        link.click();
    };

    return (
        <div className="space-y-6">
            <PageHeader title="Daily Return Report" description="RTO & Customer-Initiated Returns from Unicommerce" />

            <div className="card">
                <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-6">Generate Return Report</h2>
                <div className="flex flex-wrap items-end gap-4 mb-4">
                    <div className="flex-1 min-w-[200px]">
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Select Date</label>
                        <input type="date" value={reportDate} onChange={(e) => setReportDate(e.target.value)}
                            max={new Date().toISOString().split('T')[0]}
                            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100" />
                    </div>
                    <div className="min-w-[160px]">
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Return Type</label>
                        <select value={returnType} onChange={(e) => setReturnType(e.target.value)}
                            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100">
                            <option value="ALL">All Returns</option>
                            <option value="RTO">RTO Only</option>
                            <option value="CIR">Customer Returns</option>
                        </select>
                    </div>
                    <button onClick={handleGenerate} disabled={isLoading}
                        className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors disabled:opacity-50 shadow-lg">
                        {isLoading ? '⏳ Generating...' : '📊 Generate Report'}
                    </button>
                    {showReport && data?.success && (
                        <button onClick={handleDownloadCSV}
                            className="px-6 py-2 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg transition-colors shadow-lg">
                            📥 Download CSV
                        </button>
                    )}
                </div>
                <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                    <h4 className="font-semibold text-blue-900 dark:text-blue-100 mb-2">📌 About This Report</h4>
                    <ul className="text-sm text-blue-800 dark:text-blue-200 space-y-1">
                        <li>• <strong>RTO</strong> = Return to Origin (undelivered shipments)</li>
                        <li>• <strong>CIR</strong> = Customer Initiated Returns</li>
                        <li>• Uses Unicommerce <code className="text-xs bg-blue-100 dark:bg-blue-900 px-1 rounded">return/search</code> + <code className="text-xs bg-blue-100 dark:bg-blue-900 px-1 rounded">return/get</code> APIs</li>
                    </ul>
                </div>
            </div>

            {isLoading && (
                <div className="card text-center py-12">
                    <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-blue-500 border-t-transparent"></div>
                    <p className="mt-4 text-gray-600 dark:text-gray-400 text-lg">Fetching return data...</p>
                </div>
            )}

            {showReport && data?.success && !isLoading && (
                <>
                    {/* Summary Cards */}
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                        <StatCard title="Total Returns" value={data.totals.total_returns} icon="📦" color="blue" />
                        <StatCard title="Total Items" value={data.totals.total_items} icon="🔢" color="purple" />
                        <StatCard title="Total Value" value={`₹${(data.totals.total_value / 1000).toFixed(1)}K`} icon="💰" color="red" />
                        <StatCard title="RTO" value={data.totals.rto_count} icon="🔄" color="yellow" />
                        <StatCard title="CIR" value={data.totals.cir_count} icon="↩️" color="indigo" />
                    </div>

                    {/* Report Header */}
                    <div className="card">
                        <div className="p-4 bg-gradient-to-r from-red-50 to-orange-50 dark:from-red-900/20 dark:to-orange-900/20 rounded-lg border border-red-200 dark:border-red-800">
                            <div className="flex items-center justify-between flex-wrap gap-4">
                                <div>
                                    <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-1">
                                        📅 {new Date(reportDate).toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                                    </h3>
                                    <p className="text-sm text-gray-600 dark:text-gray-400">
                                        Type: <span className="font-semibold">{returnType === 'ALL' ? 'RTO + CIR' : returnType}</span>
                                    </p>
                                </div>
                                <div className="text-right">
                                    <p className="text-sm text-gray-600 dark:text-gray-400">Total Return Value</p>
                                    <p className="text-3xl font-bold text-red-600 dark:text-red-400">₹{data.totals.total_value.toLocaleString('en-IN')}</p>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Channel Breakdown Table */}
                    {data.by_channel?.length > 0 && (
                        <div className="card">
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Channel-wise Returns</h3>
                            <div className="overflow-x-auto">
                                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                                    <thead className="bg-gray-50 dark:bg-gray-800">
                                        <tr>
                                            <th className="px-6 py-3 text-left text-xs font-bold text-gray-700 dark:text-gray-300 uppercase">Channel</th>
                                            <th className="px-6 py-3 text-right text-xs font-bold text-gray-700 dark:text-gray-300 uppercase">Returns</th>
                                            <th className="px-6 py-3 text-right text-xs font-bold text-gray-700 dark:text-gray-300 uppercase">Items</th>
                                            <th className="px-6 py-3 text-right text-xs font-bold text-gray-700 dark:text-gray-300 uppercase">Value (₹)</th>
                                            <th className="px-6 py-3 text-right text-xs font-bold text-gray-700 dark:text-gray-300 uppercase">RTO</th>
                                            <th className="px-6 py-3 text-right text-xs font-bold text-gray-700 dark:text-gray-300 uppercase">CIR</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                                        {data.by_channel.map((ch: any) => (
                                            <tr key={ch.channel} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                                                <td className="px-6 py-3 font-medium text-gray-900 dark:text-white">{ch.channel}</td>
                                                <td className="px-6 py-3 text-right font-semibold">{ch.returns}</td>
                                                <td className="px-6 py-3 text-right">{ch.items}</td>
                                                <td className="px-6 py-3 text-right text-red-600 dark:text-red-400 font-semibold">₹{ch.value.toLocaleString('en-IN')}</td>
                                                <td className="px-6 py-3 text-right">{ch.rto}</td>
                                                <td className="px-6 py-3 text-right">{ch.cir}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                    <tfoot className="bg-gray-100 dark:bg-gray-800 border-t-2">
                                        <tr>
                                            <td className="px-6 py-3 font-bold">TOTAL</td>
                                            <td className="px-6 py-3 text-right font-bold">{data.totals.total_returns}</td>
                                            <td className="px-6 py-3 text-right font-bold">{data.totals.total_items}</td>
                                            <td className="px-6 py-3 text-right font-bold text-red-600 dark:text-red-400">₹{data.totals.total_value.toLocaleString('en-IN')}</td>
                                            <td className="px-6 py-3 text-right font-bold">{data.totals.rto_count}</td>
                                            <td className="px-6 py-3 text-right font-bold">{data.totals.cir_count}</td>
                                        </tr>
                                    </tfoot>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* SKU Breakdown Table */}
                    {data.by_sku?.length > 0 && (
                        <div className="card">
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">SKU-wise Returns (Top {Math.min(data.by_sku.length, 20)})</h3>
                            <div className="overflow-x-auto">
                                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                                    <thead className="bg-gray-50 dark:bg-gray-800">
                                        <tr>
                                            <th className="px-6 py-3 text-left text-xs font-bold text-gray-700 dark:text-gray-300 uppercase">SKU</th>
                                            <th className="px-6 py-3 text-left text-xs font-bold text-gray-700 dark:text-gray-300 uppercase">Product Name</th>
                                            <th className="px-6 py-3 text-right text-xs font-bold text-gray-700 dark:text-gray-300 uppercase">Qty</th>
                                            <th className="px-6 py-3 text-right text-xs font-bold text-gray-700 dark:text-gray-300 uppercase">Value (₹)</th>
                                            <th className="px-6 py-3 text-right text-xs font-bold text-gray-700 dark:text-gray-300 uppercase">Returns</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                                        {data.by_sku.slice(0, 20).map((s: any) => (
                                            <tr key={s.sku} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                                                <td className="px-6 py-3 font-mono text-sm text-gray-900 dark:text-white">{s.sku}</td>
                                                <td className="px-6 py-3 text-sm text-gray-600 dark:text-gray-400 max-w-[200px] truncate">{s.name}</td>
                                                <td className="px-6 py-3 text-right font-semibold">{s.quantity}</td>
                                                <td className="px-6 py-3 text-right text-red-600 dark:text-red-400 font-semibold">₹{s.value.toLocaleString('en-IN')}</td>
                                                <td className="px-6 py-3 text-right">{s.return_count}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* Debug Info */}
                    {data.search_results && (
                        <div className="card bg-gray-50 dark:bg-gray-800/50">
                            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">🔍 API Debug Information</h3>

                            <div className="space-y-3">
                                <div>
                                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">Phase 1: Search Results</p>
                                    <div className="grid grid-cols-2 gap-4 text-sm">
                                        {Object.entries(data.search_results).map(([type, count]: [string, any]) => (
                                            <div key={type} className="flex justify-between bg-white dark:bg-gray-700 p-2 rounded">
                                                <span className="text-gray-600 dark:text-gray-400">{type} found in search:</span>
                                                <span className="font-semibold text-gray-900 dark:text-white">{count}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                {data.debug_info && (data.debug_info.total_failed_rto > 0 || data.debug_info.total_failed_cir > 0) && (
                                    <div>
                                        <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">Phase 2: Failed to Get Details</p>
                                        <div className="space-y-2">
                                            {data.debug_info.total_failed_rto > 0 && (
                                                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-3 rounded text-sm">
                                                    <p className="font-semibold text-red-800 dark:text-red-200">
                                                        ⚠️ {data.debug_info.total_failed_rto} RTOs failed to fetch details
                                                    </p>
                                                    {data.debug_info.failed_rto_codes && data.debug_info.failed_rto_codes.length > 0 && (
                                                        <p className="text-xs text-red-700 dark:text-red-300 mt-1 font-mono">
                                                            Sample codes: {data.debug_info.failed_rto_codes.join(', ')}
                                                        </p>
                                                    )}
                                                    <p className="text-xs text-red-600 dark:text-red-400 mt-2">
                                                        Possible reasons: RTO returns may not have complete data in Unicommerce, or the API returns unsuccessful responses for RTOs.
                                                    </p>
                                                </div>
                                            )}
                                            {data.debug_info.total_failed_cir > 0 && (
                                                <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 p-3 rounded text-sm">
                                                    <p className="font-semibold text-yellow-800 dark:text-yellow-200">
                                                        ⚠️ {data.debug_info.total_failed_cir} CIRs failed to fetch details
                                                    </p>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}

                                {data.totals.rto_count === 0 && data.search_results.RTO > 0 && (
                                    <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded p-3 text-xs text-yellow-800 dark:text-yellow-200">
                                        <p className="font-semibold mb-1">📊 RTO Analysis:</p>
                                        <p>• Found {data.search_results.RTO} RTOs in search (Phase 1)</p>
                                        <p>• But {data.debug_info?.total_failed_rto || data.search_results.RTO} failed to get detailed data (Phase 2)</p>
                                        <p>• This is likely because Unicommerce&apos;s return/get API doesn&apos;t return complete data for RTO-type returns.</p>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {data.totals.total_returns === 0 && (
                        <div className="card text-center py-8">
                            <p className="text-2xl mb-2">✅</p>
                            <p className="text-gray-600 dark:text-gray-400">No returns found for {reportDate} ({returnType})</p>
                            <p className="text-sm text-gray-500 dark:text-gray-500 mt-2">Try selecting a different date or check Unicommerce data.</p>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
