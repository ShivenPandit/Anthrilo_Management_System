'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { salesReports } from '@/lib/api/reports';
import { DataTable, Column } from '@/components/ui/DataTable';
import { PageHeader, LoadingSpinner } from '@/components/ui/Common';
import { FilterInput, ReportFilters } from '@/components/ui/Filters';

export default function DiscountByPanelPage() {
  const [filters, setFilters] = useState({
    panel_id: '',
    start_date: '',
    end_date: '',
  });

  const { data, isLoading } = useQuery({
    queryKey: ['discountByPanel', filters],
    queryFn: async () => {
      const response = await salesReports.getDiscountByPanel({
        panel_id: filters.panel_id ? parseInt(filters.panel_id) : undefined,
        start_date: filters.start_date,
        end_date: filters.end_date,
      });
      return response.data;
    },
  });

  const columns: Column<any>[] = [
    { key: 'panel_name', header: 'Panel Name', width: '25%' },
    { key: 'panel_code', header: 'Panel Code', width: '15%' },
    {
      key: 'total_sales',
      header: 'Total Sales',
      render: (value) => <span className="font-semibold text-gray-900 dark:text-gray-100">{value}</span>,
    },
    {
      key: 'avg_discount',
      header: 'Avg Discount',
      render: (value) => {
        const colorClass =
          value > 25 ? 'text-red-600 dark:text-red-400' : value > 15 ? 'text-yellow-600 dark:text-yellow-400' : 'text-green-600 dark:text-green-400';
        return <span className={`font-bold ${colorClass}`}>{value?.toFixed(1)}%</span>;
      },
    },
    {
      key: 'total_discount_amount',
      header: 'Total Discount Given',
      render: (value) => (
        <span className="text-red-600 dark:text-red-400 font-semibold">₹{value?.toFixed(2)}</span>
      ),
    },
    {
      key: 'revenue',
      header: 'Revenue',
      render: (value) => (
        <span className="text-green-600 dark:text-green-400 font-bold">₹{value?.toFixed(2)}</span>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Discount by Panel Report"
        description="Panel-wise discount analysis and performance tracking"
      />

      <ReportFilters onApplyFilters={setFilters}>
        <FilterInput
          label="Panel ID"
          type="number"
          value={filters.panel_id}
          onChange={(value) => setFilters({ ...filters, panel_id: value })}
          placeholder="All Panels"
        />
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
        <h2 className="mb-4 text-gray-900 dark:text-gray-100">Panel Discount Analysis</h2>
        {isLoading ? (
          <LoadingSpinner message="Analyzing panel discounts..." />
        ) : (
          <DataTable
            data={data || []}
            columns={columns}
            emptyMessage="No panel sales data available"
          />
        )}
      </div>
    </div>
  );
}
