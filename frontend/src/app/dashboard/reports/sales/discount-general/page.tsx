'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { salesReports } from '@/lib/api/reports';
import { DataTable, Column } from '@/components/ui/DataTable';
import { PageHeader, LoadingSpinner, StatCard } from '@/components/ui/Common';
import { FilterInput, ReportFilters } from '@/components/ui/Filters';

export default function GeneralDiscountReportPage() {
  const [filters, setFilters] = useState({
    start_date: '',
    end_date: '',
  });

  const { data, isLoading } = useQuery({
    queryKey: ['generalDiscountReport', filters],
    queryFn: async () => {
      const response = await salesReports.getGeneralDiscountReport(filters);
      return response.data;
    },
  });

  const columns: Column<any>[] = [
    { key: 'sku', header: 'SKU', width: '15%' },
    { key: 'product_name', header: 'Product Name', width: '25%' },
    {key: 'mrp',
      header: 'MRP',
      render: (value) => <span className="text-gray-900 dark:text-gray-100">₹{value?.toFixed(2)}</span>,
    },
    {
      key: 'selling_price',
      header: 'Selling Price',
      render: (value) => <span className="text-gray-900 dark:text-gray-100">₹{value?.toFixed(2)}</span>,
    },
    {
      key: 'discount_percent',
      header: 'Discount %',
      render: (value) => {
        const percent = value?.toFixed(1);
        const colorClass =
          value > 30 ? 'text-red-600 dark:text-red-400' : value > 15 ? 'text-yellow-600 dark:text-yellow-400' : 'text-green-600 dark:text-green-400';
        return <span className={`font-bold ${colorClass}`}>{percent}%</span>;
      },
    },
    {
      key: 'discount_bucket',
      header: 'Discount Bucket',
      render: (value) => {
        const bucketColors: Record<string, string> = {
          '0-10%': 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200',
          '10-20%': 'bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200',
          '20-30%': 'bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200',
          '30-40%': 'bg-orange-100 dark:bg-orange-900 text-orange-800 dark:text-orange-200',
          '40%+': 'bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200',
        };
        return (
          <span
            className={`px-3 py-1 rounded-full text-xs font-medium ${
              bucketColors[value] || 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
            }`}
          >
            {value}
          </span>
        );
      },
    },
    {
      key: 'total_sold',
      header: 'Units Sold',
      render: (value) => <span className="font-semibold text-gray-900 dark:text-gray-100">{value}</span>,
    },
  ];

  // Calculate summary statistics
  const avgDiscount =
    data?.reduce((sum: number, item: any) => sum + (item.discount_percent || 0), 0) /
      (data?.length || 1) || 0;
  const totalRevenueLoss =
    data?.reduce(
      (sum: number, item: any) =>
        sum + (item.mrp - item.selling_price) * item.total_sold,
      0
    ) || 0;

  return (
    <div>
      <PageHeader
        title="General Discount Report"
        description="Comprehensive discount analysis across all products"
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
        <StatCard
          title="Average Discount"
          value={`${avgDiscount.toFixed(1)}%`}
          icon="💸"
          color="blue"
        />
        <StatCard
          title="Total Products"
          value={data?.length || 0}
          icon="📦"
          color="purple"
        />
        <StatCard
          title="Revenue Impact"
          value={`₹${totalRevenueLoss.toFixed(0)}`}
          icon="💰"
          color="red"
        />
      </div>

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
        <h2 className="mb-4 text-gray-900 dark:text-gray-100">Discount Details</h2>
        {isLoading ? (
          <LoadingSpinner message="Calculating discount analytics..." />
        ) : (
          <DataTable
            data={data || []}
            columns={columns}
            emptyMessage="No sales data available for the selected period"
          />
        )}
      </div>
    </div>
  );
}
