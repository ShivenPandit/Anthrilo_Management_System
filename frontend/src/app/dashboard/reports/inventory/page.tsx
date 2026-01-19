'use client';

import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { useState } from 'react';

export default function InventoryReportsPage() {
  const [reportType, setReportType] = useState<'slow' | 'fast'>('slow');
  const [daysPeriod, setDaysPeriod] = useState(90);

  const { data: slowReport, isLoading: loadingSlow } = useQuery({
    queryKey: ['inventoryReport', 'slow', daysPeriod],
    queryFn: async () => {
      const response = await apiClient.get('/reports/inventory/slow-moving', {
        params: { days_period: daysPeriod },
      });
      return response.data;
    },
    enabled: reportType === 'slow',
  });

  const { data: fastReport, isLoading: loadingFast } = useQuery({
    queryKey: ['inventoryReport', 'fast', daysPeriod],
    queryFn: async () => {
      const response = await apiClient.get('/reports/inventory/fast-moving', {
        params: { days_period: daysPeriod },
      });
      return response.data;
    },
    enabled: reportType === 'fast',
  });

  const isLoading = loadingSlow || loadingFast;
  const currentReport = reportType === 'slow' ? slowReport : fastReport;

  return (
    <div>
      <h1 className="mb-6">Inventory Analysis</h1>

      <div className="card mb-6">
        <h3 className="mb-4">Select Analysis Type</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <button
            onClick={() => setReportType('slow')}
            className={`p-4 border-2 rounded-lg transition-all ${
              reportType === 'slow'
                ? 'border-primary-600 bg-primary-50'
                : 'border-gray-200 hover:border-primary-300'
            }`}
          >
            <div className="text-2xl mb-2">🐌</div>
            <div className="font-semibold">Slow Moving</div>
            <div className="text-sm text-gray-500">Low turnover items</div>
          </button>

          <button
            onClick={() => setReportType('fast')}
            className={`p-4 border-2 rounded-lg transition-all ${
              reportType === 'fast'
                ? 'border-primary-600 bg-primary-50'
                : 'border-gray-200 hover:border-primary-300'
            }`}
          >
            <div className="text-2xl mb-2">🚀</div>
            <div className="font-semibold">Fast Moving</div>
            <div className="text-sm text-gray-500">High turnover items</div>
          </button>
        </div>

        <div className="mt-4">
          <label className="block text-sm font-medium mb-2">
            Analysis Period (Days)
          </label>
          <select
            value={daysPeriod}
            onChange={(e) => setDaysPeriod(Number(e.target.value))}
            className="input max-w-xs"
          >
            <option value={30}>Last 30 Days</option>
            <option value={60}>Last 60 Days</option>
            <option value={90}>Last 90 Days</option>
            <option value={180}>Last 6 Months</option>
            <option value={365}>Last Year</option>
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="card text-center py-12">Loading...</div>
      ) : currentReport ? (
        <div className="space-y-6">
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="card">
              <div className="text-sm text-gray-600 mb-1">
                {reportType === 'slow' ? 'Slow Moving Items' : 'Fast Moving Items'}
              </div>
              <div className="text-3xl font-bold text-primary-600">
                {currentReport.items_count}
              </div>
            </div>
            <div className="card">
              <div className="text-sm text-gray-600 mb-1">Analysis Period</div>
              <div className="text-3xl font-bold text-primary-600">
                {currentReport.analysis_period_days} days
              </div>
            </div>
            <div className="card">
              <div className="text-sm text-gray-600 mb-1">Threshold</div>
              <div className="text-3xl font-bold text-primary-600">
                {currentReport.threshold}
              </div>
            </div>
          </div>

          {/* Items Table */}
          {currentReport.items && currentReport.items.length > 0 ? (
            <div className="card">
              <h3 className="mb-4">Inventory Items</h3>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        SKU
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Garment
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Size
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Stock
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Sales ({daysPeriod}d)
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Turnover Rate
                      </th>
                      {reportType === 'fast' && (
                        <>
                          <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                            Days of Stock
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                            Reorder Qty
                          </th>
                        </>
                      )}
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {currentReport.items.map((item: any) => (
                      <tr key={item.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 text-sm font-medium">{item.sku}</td>
                        <td className="px-4 py-3 text-sm">{item.garment_name}</td>
                        <td className="px-4 py-3 text-sm">{item.size}</td>
                        <td className="px-4 py-3 text-sm text-right">
                          <span className={item.current_stock < 10 ? 'text-red-600 font-medium' : ''}>
                            {item.current_stock}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm text-right">{item.sales_count}</td>
                        <td className="px-4 py-3 text-sm text-right">
                          <span
                            className={`px-2 py-1 rounded text-xs ${
                              item.turnover_rate > 1
                                ? 'bg-green-100 text-green-800'
                                : item.turnover_rate < 0.1
                                ? 'bg-red-100 text-red-800'
                                : 'bg-yellow-100 text-yellow-800'
                            }`}
                          >
                            {item.turnover_rate.toFixed(3)}
                          </span>
                        </td>
                        {reportType === 'fast' && (
                          <>
                            <td className="px-4 py-3 text-sm text-right">
                              {item.days_of_stock_remaining?.toFixed(1) || '-'}
                            </td>
                            <td className="px-4 py-3 text-sm text-right font-medium text-blue-600">
                              {item.recommended_reorder_quantity || '-'}
                            </td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Legend */}
              <div className="mt-4 p-4 bg-gray-50 rounded-lg">
                <h4 className="text-sm font-medium mb-2">Understanding Turnover Rate</h4>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-1 bg-red-100 text-red-800 rounded text-xs">
                      &lt; 0.1
                    </span>
                    <span className="text-gray-600">Slow Moving</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-1 bg-yellow-100 text-yellow-800 rounded text-xs">
                      0.1 - 1.0
                    </span>
                    <span className="text-gray-600">Moderate</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-1 bg-green-100 text-green-800 rounded text-xs">
                      &gt; 1.0
                    </span>
                    <span className="text-gray-600">Fast Moving</span>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="card text-center py-12 text-gray-500">
              No {reportType === 'slow' ? 'slow' : 'fast'} moving items found
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
