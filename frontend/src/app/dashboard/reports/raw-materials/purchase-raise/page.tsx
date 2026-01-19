'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { rawMaterialsReports } from '@/lib/api/reports';
import { DataTable, Column } from '@/components/ui/DataTable';
import { PageHeader, LoadingSpinner } from '@/components/ui/Common';
import { FilterInput, ReportFilters } from '@/components/ui/Filters';

export default function PurchaseRaiseYarnPage() {
  const [filters, setFilters] = useState({ threshold: '20', forecast_days: '30' });

  const { data, isLoading } = useQuery({
    queryKey: ['purchaseRaiseYarn', filters],
    queryFn: async () => {
      const response = await rawMaterialsReports.getPurchaseRaiseForYarn({
        threshold: parseInt(filters.threshold),
        forecast_days: parseInt(filters.forecast_days),
      });
      return response.data;
    },
  });

  const columns: Column<any>[] = [
    { 
      key: 'yarn_count', 
      header: 'Yarn Count',
      width: '12%',
    },
    { 
      key: 'composition', 
      header: 'Composition',
      width: '18%',
    },
    {
      key: 'current_stock',
      header: 'Current Stock',
      render: (value) => <span className="text-gray-900 dark:text-gray-100">{value?.toFixed(2)}</span>,
    },
    {
      key: 'minimum_threshold',
      header: 'Min Threshold',
      render: (value) => <span className="text-orange-600 dark:text-orange-400 font-medium">{value?.toFixed(2)}</span>,
    },
    {
      key: 'shortage',
      header: 'Shortage',
      render: (value) => (
        <span className="font-bold text-red-600 dark:text-red-400">{value?.toFixed(2)}</span>
      ),
    },
    {
      key: 'recommended_order_quantity',
      header: 'Order Qty',
      render: (value) => (
        <span className="font-semibold text-blue-600 dark:text-blue-400">{value?.toFixed(2)}</span>
      ),
    },
    {
      key: 'priority',
      header: 'Priority',
      render: (value) => {
        const priorityColors = {
          HIGH: 'bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200 border border-red-300 dark:border-red-600',
          MEDIUM: 'bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200 border border-yellow-300 dark:border-yellow-600',
          LOW: 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 border border-green-300 dark:border-green-600',
        };
        return (
          <span
            className={`px-3 py-1 rounded-full text-xs font-bold ${
              priorityColors[value as keyof typeof priorityColors] ||
              'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
            }`}
          >
            {value}
          </span>
        );
      },
    },
    {
      key: 'estimated_order_value',
      header: 'Order Value',
      render: (value) => (
        <span className="text-green-600 dark:text-green-400 font-semibold">₹{value?.toFixed(2)}</span>
      ),
    },
  ];

  const purchaseData = data?.purchase_recommendations || [];
  const highPriorityCount = purchaseData?.filter((item: any) => item.priority === 'HIGH').length || 0;

  return (
    <div>
      <PageHeader
        title="Purchase Raise for Yarn"
        description="Automated purchase recommendations based on stock levels and forecasts"
      />

      {highPriorityCount > 0 && (
        <div className="bg-red-50 dark:bg-red-900/20 border-l-4 border-red-500 dark:border-red-400 p-4 mb-6 rounded-lg">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <svg
                className="h-5 w-5 text-red-400 dark:text-red-300"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
            <div className="ml-3">
              <p className="text-sm text-red-700 dark:text-red-300">
                <strong>Urgent Action Required:</strong> {highPriorityCount} yarn type(s)
                require immediate purchase orders.
              </p>
            </div>
          </div>
        </div>
      )}

      <ReportFilters onApplyFilters={setFilters}>
        <FilterInput
          label="Stock Threshold (%)"
          type="number"
          value={filters.threshold}
          onChange={(value) => setFilters({ ...filters, threshold: value })}
          min="10"
          max="50"
          placeholder="20"
        />
        <FilterInput
          label="Forecast Period (Days)"
          type="number"
          value={filters.forecast_days}
          onChange={(value) => setFilters({ ...filters, forecast_days: value })}
          min="7"
          max="90"
          placeholder="30"
        />
      </ReportFilters>

      <div className="card">
        <h2 className="mb-4 text-gray-900 dark:text-gray-100">Purchase Recommendations</h2>
        {isLoading ? (
          <LoadingSpinner message="Analyzing inventory and generating recommendations..." />
        ) : (
          <DataTable
            data={purchaseData}
            columns={columns}
            emptyMessage="All yarn stocks are at healthy levels"
          />
        )}
      </div>
    </div>
  );
}
