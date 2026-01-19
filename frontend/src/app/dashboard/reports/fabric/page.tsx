'use client';

import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { useState } from 'react';

export default function FabricReportsPage() {
  const [reportType, setReportType] = useState<'total' | 'type' | 'period' | 'cost'>('total');
  const [fabricType, setFabricType] = useState('JERSEY');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const { data: totalReport, isLoading: loadingTotal } = useQuery({
    queryKey: ['fabricReport', 'total'],
    queryFn: async () => {
      const response = await apiClient.get('/reports/fabric/stock-sheet/total');
      return response.data;
    },
    enabled: reportType === 'total',
  });

  const { data: typeReport, isLoading: loadingType } = useQuery({
    queryKey: ['fabricReport', 'type', fabricType],
    queryFn: async () => {
      const response = await apiClient.get(`/reports/fabric/stock-sheet/by-type/${fabricType}`);
      return response.data;
    },
    enabled: reportType === 'type',
  });

  const { data: periodReport, isLoading: loadingPeriod } = useQuery({
    queryKey: ['fabricReport', 'period', startDate, endDate],
    queryFn: async () => {
      const response = await apiClient.get('/reports/fabric/stock-sheet/by-period', {
        params: { start_date: startDate, end_date: endDate },
      });
      return response.data;
    },
    enabled: reportType === 'period' && !!startDate && !!endDate,
  });

  const { data: costReport, isLoading: loadingCost } = useQuery({
    queryKey: ['fabricReport', 'cost'],
    queryFn: async () => {
      const response = await apiClient.get('/reports/fabric/cost-sheet');
      return response.data;
    },
    enabled: reportType === 'cost',
  });

  const isLoading = loadingTotal || loadingType || loadingPeriod || loadingCost;
  const currentReport = reportType === 'total' ? totalReport : 
                        reportType === 'type' ? typeReport :
                        reportType === 'period' ? periodReport : costReport;

  const downloadReport = () => {
    const dataStr = JSON.stringify(currentReport, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `fabric-report-${reportType}-${new Date().toISOString()}.json`;
    link.click();
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1>Fabric Reports</h1>
        {currentReport && (
          <button onClick={downloadReport} className="btn btn-secondary">
            📥 Download Report
          </button>
        )}
      </div>

      {/* Report Type Selector */}
      <div className="card mb-6">
        <h3 className="mb-4">Select Report Type</h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <button
            onClick={() => setReportType('total')}
            className={`p-4 border-2 rounded-lg transition-all ${
              reportType === 'total'
                ? 'border-primary-600 bg-primary-50'
                : 'border-gray-200 hover:border-primary-300'
            }`}
          >
            <div className="text-2xl mb-2">📊</div>
            <div className="font-semibold">Total Stock</div>
            <div className="text-sm text-gray-500">All fabrics</div>
          </button>

          <button
            onClick={() => setReportType('type')}
            className={`p-4 border-2 rounded-lg transition-all ${
              reportType === 'type'
                ? 'border-primary-600 bg-primary-50'
                : 'border-gray-200 hover:border-primary-300'
            }`}
          >
            <div className="text-2xl mb-2">🏷️</div>
            <div className="font-semibold">By Type</div>
            <div className="text-sm text-gray-500">Filter by fabric type</div>
          </button>

          <button
            onClick={() => setReportType('period')}
            className={`p-4 border-2 rounded-lg transition-all ${
              reportType === 'period'
                ? 'border-primary-600 bg-primary-50'
                : 'border-gray-200 hover:border-primary-300'
            }`}
          >
            <div className="text-2xl mb-2">📅</div>
            <div className="font-semibold">By Period</div>
            <div className="text-sm text-gray-500">Date range</div>
          </button>

          <button
            onClick={() => setReportType('cost')}
            className={`p-4 border-2 rounded-lg transition-all ${
              reportType === 'cost'
                ? 'border-primary-600 bg-primary-50'
                : 'border-gray-200 hover:border-primary-300'
            }`}
          >
            <div className="text-2xl mb-2">💰</div>
            <div className="font-semibold">Cost Sheet</div>
            <div className="text-sm text-gray-500">Cost breakdown</div>
          </button>
        </div>

        {/* Additional Filters */}
        {reportType === 'type' && (
          <div className="mt-4">
            <label className="block text-sm font-medium mb-2">Fabric Type</label>
            <select
              value={fabricType}
              onChange={(e) => setFabricType(e.target.value)}
              className="input max-w-xs"
            >
              <option value="JERSEY">Jersey</option>
              <option value="TERRY">Terry</option>
              <option value="FLEECE">Fleece</option>
            </select>
          </div>
        )}

        {reportType === 'period' && (
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
        <div className="card text-center py-12">
          <div className="text-gray-500">Loading report...</div>
        </div>
      ) : currentReport ? (
        <div className="space-y-6">
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {currentReport.summary && (
              <>
                {currentReport.summary.total_fabric_types !== undefined && (
                  <div className="card">
                    <div className="text-sm text-gray-600 mb-1">Total Fabric Types</div>
                    <div className="text-3xl font-bold text-primary-600">
                      {currentReport.summary.total_fabric_types}
                    </div>
                  </div>
                )}
                {currentReport.summary.total_stock_quantity !== undefined && (
                  <div className="card">
                    <div className="text-sm text-gray-600 mb-1">Total Stock</div>
                    <div className="text-3xl font-bold text-primary-600">
                      {currentReport.summary.total_stock_quantity.toFixed(2)} kg
                    </div>
                  </div>
                )}
                {currentReport.summary.total_stock_value !== undefined && (
                  <div className="card">
                    <div className="text-sm text-gray-600 mb-1">Total Value</div>
                    <div className="text-3xl font-bold text-primary-600">
                      ₹{currentReport.summary.total_stock_value.toFixed(2)}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Detailed Table */}
          <div className="card overflow-hidden">
            <h3 className="mb-4">{currentReport.report_type}</h3>
            <div className="text-sm text-gray-500 mb-4">
              Generated: {new Date(currentReport.generated_at).toLocaleString()}
            </div>
            
            {currentReport.fabrics && currentReport.fabrics.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Type
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Subtype
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        GSM
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Color
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Stock (kg)
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Cost/Unit
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Value
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {currentReport.fabrics.map((fabric: any, idx: number) => (
                      <tr key={idx} className="hover:bg-gray-50">
                        <td className="px-4 py-3 text-sm">{fabric.fabric_type}</td>
                        <td className="px-4 py-3 text-sm">{fabric.subtype}</td>
                        <td className="px-4 py-3 text-sm">{fabric.gsm}</td>
                        <td className="px-4 py-3 text-sm">{fabric.color || '-'}</td>
                        <td className="px-4 py-3 text-sm text-right">
                          {fabric.stock_quantity.toFixed(2)}
                        </td>
                        <td className="px-4 py-3 text-sm text-right">
                          ₹{fabric.cost_per_unit.toFixed(2)}
                        </td>
                        <td className="px-4 py-3 text-sm text-right font-medium">
                          ₹{fabric.stock_value.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : currentReport.detailed_costs ? (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Type
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Subtype
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Stock (kg)
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Cost/Unit
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Total Value
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {currentReport.detailed_costs.map((item: any, idx: number) => (
                      <tr key={idx} className="hover:bg-gray-50">
                        <td className="px-4 py-3 text-sm">{item.fabric_type}</td>
                        <td className="px-4 py-3 text-sm">{item.subtype}</td>
                        <td className="px-4 py-3 text-sm text-right">
                          {item.stock_quantity.toFixed(2)}
                        </td>
                        <td className="px-4 py-3 text-sm text-right">
                          ₹{item.cost_per_unit.toFixed(2)}
                        </td>
                        <td className="px-4 py-3 text-sm text-right font-medium">
                          ₹{item.total_value.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500">No data available</div>
            )}
          </div>
        </div>
      ) : (
        <div className="card text-center py-12">
          <div className="text-gray-500">Select report parameters to generate report</div>
        </div>
      )}
    </div>
  );
}
