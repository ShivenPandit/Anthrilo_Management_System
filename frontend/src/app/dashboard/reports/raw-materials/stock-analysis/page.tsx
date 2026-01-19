'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { rawMaterialsReports } from '@/lib/api/reports';
import { DataTable, Column } from '@/components/ui/DataTable';
import { PageHeader, LoadingSpinner } from '@/components/ui/Common';
import { FilterInput, ReportFilters } from '@/components/ui/Filters';

export default function StockAnalysisPage() {
  const [filters, setFilters] = useState({ category: '' });

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['stockAnalysis', filters],
    queryFn: async () => {
      const response = await rawMaterialsReports.getStockAnalysis(filters);
      return response.data;
    },
  });

  const columns: Column<any>[] = [
    { key: 'item_name', header: 'Item Name', width: '20%' },
    { key: 'category', header: 'Category', width: '15%' },
    {
      key: 'quantity',
      header: 'Quantity',
      render: (value) => (
        <span className="font-semibold text-gray-900 dark:text-gray-100">{value?.toFixed(2) || '0.00'}</span>
      ),
    },
    { key: 'unit', header: 'Unit', width: '10%' },
    {
      key: 'value',
      header: 'Value',
      render: (value) => (
        <span className="text-green-600 dark:text-green-400 font-semibold">₹{value?.toFixed(2) || '0.00'}</span>
      ),
    },
    {
      key: 'stock_status',
      header: 'Status',
      render: (value) => {
        const statusColors = {
          Low: 'bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200',
          Normal: 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200',
          High: 'bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200',
        };
        return (
          <span
            className={`px-3 py-1 rounded-full text-xs font-medium ${
              statusColors[value as keyof typeof statusColors] || 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
            }`}
          >
            {value}
          </span>
        );
      },
    },
  ];

  return (
    <div>
      <PageHeader
        title="Raw Materials Stock Analysis"
        description="Monitor inventory levels and stock status of raw materials"
      />

      <ReportFilters onApplyFilters={setFilters}>
        <FilterInput
          label="Category"
          type="select"
          value={filters.category}
          onChange={(value) => setFilters({ ...filters, category: value })}
          options={[
            { label: 'Yarn', value: 'Yarn' },
            { label: 'Fabric', value: 'Fabric' },
            { label: 'Dyes', value: 'Dyes' },
            { label: 'Chemicals', value: 'Chemicals' },
          ]}
        />
      </ReportFilters>

      <div className="card">
        <h2 className="mb-4 text-gray-900 dark:text-gray-100">Stock Details</h2>
        {isLoading ? (
          <LoadingSpinner message="Loading stock data..." />
        ) : (
          <DataTable data={data || []} columns={columns} />
        )}
      </div>
    </div>
  );
}
