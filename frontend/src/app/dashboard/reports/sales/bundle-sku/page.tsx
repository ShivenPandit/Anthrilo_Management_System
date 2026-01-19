'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { salesReports } from '@/lib/api/reports';
import { DataTable, Column } from '@/components/ui/DataTable';
import { PageHeader, LoadingSpinner } from '@/components/ui/Common';
import { FilterInput, ReportFilters } from '@/components/ui/Filters';

export default function BundleSKUSalesPage() {
  const [filters, setFilters] = useState({
    start_date: '',
    end_date: '',
  });

  const { data, isLoading } = useQuery({
    queryKey: ['bundleSKUSales', filters],
    queryFn: async () => {
      const response = await salesReports.getBundleSKUSales(filters);
      return response.data;
    },
  });

  const columns: Column<any>[] = [
    { key: 'bundle_sku', header: 'Bundle SKU', width: '15%' },
    { key: 'bundle_name', header: 'Bundle Name', width: '20%' },
    {
      key: 'total_quantity',
      header: 'Total Qty Sold',
      render: (value) => <span className="font-semibold text-gray-900 dark:text-gray-100">{value}</span>,
    },
    {
      key: 'size_breakdown',
      header: 'Size Breakdown',
      width: '30%',
      render: (value) => {
        if (!value || typeof value !== 'object') return <span className="text-gray-500 dark:text-gray-400">-</span>;
        return (
          <div className="flex flex-wrap gap-2">
            {Object.entries(value).map(([size, qty]) => (
              <span
                key={size}
                className="px-2 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded-lg text-xs font-medium"
              >
                {size}: {qty as number}
              </span>
            ))}
          </div>
        );
      },
    },
    {
      key: 'total_revenue',
      header: 'Total Revenue',
      render: (value) => (
        <span className="text-green-600 dark:text-green-400 font-bold">₹{value?.toFixed(2)}</span>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Bundle SKU Sales Report"
        description="Size-wise breakdown of bundle sales performance"
      />

      <ReportFilters onApplyFilters={setFilters}>
        <FilterInput
          label="Start Date"
          type="date"
          value={filters.start_date}
          onChange={(value) => setFilters({ ...filters, start_date: value })}
        />
        <FilterInput
          label="End Date"
          type="date"
          value={filters.end_date}
          onChange={(value) => setFilters({ ...filters, end_date: value })}
        />
      </ReportFilters>

      <div className="card">
        <h2 className="mb-4 text-gray-900 dark:text-gray-100">Bundle Sales Analysis</h2>
        {isLoading ? (
          <LoadingSpinner message="Loading bundle sales data..." />
        ) : (
          <DataTable
            data={data || []}
            columns={columns}
            emptyMessage="No bundle sales data available for the selected period"
          />
        )}
      </div>
    </div>
  );
}
