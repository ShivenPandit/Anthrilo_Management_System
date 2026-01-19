'use client';

import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { useState } from 'react';

export default function SalesReportsPage() {
  const [reportDate, setReportDate] = useState(new Date().toISOString().split('T')[0]);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [reportType, setReportType] = useState<'daily' | 'panel' | 'inactive'>('daily');

  const { data: dailyReport, isLoading: loadingDaily } = useQuery({
    queryKey: ['salesReport', 'daily', reportDate],
    queryFn: async () => {
      const response = await apiClient.get(`/reports/sales/daily/${reportDate}`);
      return response.data;
    },
    enabled: reportType === 'daily' && !!reportDate,
  });

  const { data: panelReport, isLoading: loadingPanel } = useQuery({
    queryKey: ['salesReport', 'panel', startDate, endDate],
    queryFn: async () => {
      const response = await apiClient.get('/reports/sales/panel-wise', {
        params: { start_date: startDate, end_date: endDate },
      });
      return response.data;
    },
    enabled: reportType === 'panel' && !!startDate && !!endDate,
  });

  const { data: inactiveReport, isLoading: loadingInactive } = useQuery({
    queryKey: ['salesReport', 'inactive'],
    queryFn: async () => {
      const response = await apiClient.get('/reports/sales/inactive-panels', {
        params: { days_threshold: 30 },
      });
      return response.data;
    },
    enabled: reportType === 'inactive',
  });

  const isLoading = loadingDaily || loadingPanel || loadingInactive;
  const currentReport = reportType === 'daily' ? dailyReport :
                        reportType === 'panel' ? panelReport : inactiveReport;

  return (
    <div>
      <h1 className="mb-6">Sales Reports</h1>

      {/* Report Type Selector */}
      <div className="card mb-6">
        <h3 className="mb-4">Select Report Type</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <button
            onClick={() => setReportType('daily')}
            className={`p-4 border-2 rounded-lg transition-all ${
              reportType === 'daily'
                ? 'border-primary-600 bg-primary-50'
                : 'border-gray-200 hover:border-primary-300'
            }`}
          >
            <div className="text-2xl mb-2">📅</div>
            <div className="font-semibold">Daily Sales</div>
            <div className="text-sm text-gray-500">Single day report</div>
          </button>

          <button
            onClick={() => setReportType('panel')}
            className={`p-4 border-2 rounded-lg transition-all ${
              reportType === 'panel'
                ? 'border-primary-600 bg-primary-50'
                : 'border-gray-200 hover:border-primary-300'
            }`}
          >
            <div className="text-2xl mb-2">🏪</div>
            <div className="font-semibold">Panel-Wise</div>
            <div className="text-sm text-gray-500">By sales channel</div>
          </button>

          <button
            onClick={() => setReportType('inactive')}
            className={`p-4 border-2 rounded-lg transition-all ${
              reportType === 'inactive'
                ? 'border-primary-600 bg-primary-50'
                : 'border-gray-200 hover:border-primary-300'
            }`}
          >
            <div className="text-2xl mb-2">⚠️</div>
            <div className="font-semibold">Inactive Panels</div>
            <div className="text-sm text-gray-500">No recent activity</div>
          </button>
        </div>

        {/* Filters */}
        {reportType === 'daily' && (
          <div className="mt-4">
            <label className="block text-sm font-medium mb-2">Report Date</label>
            <input
              type="date"
              value={reportDate}
              onChange={(e) => setReportDate(e.target.value)}
              className="input max-w-xs"
            />
          </div>
        )}

        {reportType === 'panel' && (
          <div className="mt-4 grid grid-cols-2 gap-4 max-w-md">
            <div>
              <label className="block text-sm font-medium mb-2">Start Date</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="input"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">End Date</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="input"
              />
            </div>
          </div>
        )}
      </div>

      {/* Report Display */}
      {isLoading ? (
        <div className="card text-center py-12">Loading...</div>
      ) : currentReport ? (
        <div className="space-y-6">
          {/* Summary for Daily Report */}
          {reportType === 'daily' && currentReport.summary && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                <div className="card">
                  <div className="text-sm text-gray-600 mb-1">Net Sales</div>
                  <div className="text-3xl font-bold text-green-600">
                    ₹{currentReport.summary.net_sales_value.toFixed(2)}
                  </div>
                </div>
                <div className="card">
                  <div className="text-sm text-gray-600 mb-1">Transactions</div>
                  <div className="text-3xl font-bold text-primary-600">
                    {currentReport.summary.total_transactions}
                  </div>
                </div>
                <div className="card">
                  <div className="text-sm text-gray-600 mb-1">Units Sold</div>
                  <div className="text-3xl font-bold text-primary-600">
                    {currentReport.summary.net_units}
                  </div>
                </div>
                <div className="card">
                  <div className="text-sm text-gray-600 mb-1">Returns</div>
                  <div className="text-3xl font-bold text-red-600">
                    {currentReport.summary.total_returns}
                  </div>
                </div>
              </div>

              <div className="card">
                <h3 className="mb-4">Transactions</h3>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Invoice
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Size
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                          Qty
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                          Price
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                          Discount %
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                          Total
                        </th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                          Type
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {currentReport.transactions.map((txn: any) => (
                        <tr key={txn.id} className="hover:bg-gray-50">
                          <td className="px-4 py-3 text-sm">{txn.invoice_number || '-'}</td>
                          <td className="px-4 py-3 text-sm">{txn.size}</td>
                          <td className="px-4 py-3 text-sm text-right">{txn.quantity}</td>
                          <td className="px-4 py-3 text-sm text-right">₹{txn.unit_price}</td>
                          <td className="px-4 py-3 text-sm text-right">{txn.discount_percentage}%</td>
                          <td className="px-4 py-3 text-sm text-right font-medium">
                            ₹{txn.total_amount}
                          </td>
                          <td className="px-4 py-3 text-sm text-center">
                            {txn.is_return ? (
                              <span className="px-2 py-1 text-xs bg-red-100 text-red-800 rounded">
                                Return
                              </span>
                            ) : (
                              <span className="px-2 py-1 text-xs bg-green-100 text-green-800 rounded">
                                Sale
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}

          {/* Panel-wise Report */}
          {reportType === 'panel' && currentReport.panels && (
            <div className="card">
              <h3 className="mb-4">Panel Performance</h3>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Panel Name
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Type
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Transactions
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Units Sold
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Gross Sales
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Returns
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Net Sales
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {Object.entries(currentReport.panels).map(([panelId, data]: [string, any]) => (
                      <tr key={panelId} className="hover:bg-gray-50">
                        <td className="px-4 py-3 text-sm font-medium">{data.panel_name}</td>
                        <td className="px-4 py-3 text-sm">{data.panel_type}</td>
                        <td className="px-4 py-3 text-sm text-right">{data.total_transactions}</td>
                        <td className="px-4 py-3 text-sm text-right">{data.total_units_sold}</td>
                        <td className="px-4 py-3 text-sm text-right">
                          ₹{data.gross_sales_value.toFixed(2)}
                        </td>
                        <td className="px-4 py-3 text-sm text-right text-red-600">
                          ₹{data.returns_value.toFixed(2)}
                        </td>
                        <td className="px-4 py-3 text-sm text-right font-medium text-green-600">
                          ₹{data.net_sales_value.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Inactive Panels */}
          {reportType === 'inactive' && currentReport.inactive_panels && (
            <div className="card">
              <h3 className="mb-4">Inactive Panels ({currentReport.inactive_panels_count})</h3>
              {currentReport.inactive_panels.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Panel Name
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Type
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Last Sale
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                          Days Inactive
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {currentReport.inactive_panels.map((panel: any) => (
                        <tr key={panel.id} className="hover:bg-gray-50">
                          <td className="px-4 py-3 text-sm font-medium">{panel.panel_name}</td>
                          <td className="px-4 py-3 text-sm">{panel.panel_type}</td>
                          <td className="px-4 py-3 text-sm">
                            {panel.last_sale_date || 'Never'}
                          </td>
                          <td className="px-4 py-3 text-sm text-right text-red-600">
                            {panel.days_since_last_sale || 'N/A'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-8 text-green-600">
                  ✓ All panels are active!
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="card text-center py-12 text-gray-500">
          Select report parameters
        </div>
      )}
    </div>
  );
}
