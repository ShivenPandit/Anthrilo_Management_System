'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { panelReports } from '@/lib/api/reports';
import { DataTable, Column } from '@/components/ui/DataTable';
import { PageHeader, LoadingSpinner } from '@/components/ui/Common';
import { FilterInput, ReportFilters } from '@/components/ui/Filters';

export default function PanelSettlementPage() {
  const [filters, setFilters] = useState({
    panel_id: '',
    start_date: '',
    end_date: '',
  });

  const { data, isLoading } = useQuery({
    queryKey: ['panelSettlement', filters],
    queryFn: async () => {
      const response = await panelReports.getPanelSettlement({
        panel_id: filters.panel_id ? parseInt(filters.panel_id) : undefined,
        start_date: filters.start_date,
        end_date: filters.end_date,
      });
      return response.data;
    },
  });

  const columns: Column<any>[] = [
    { key: 'panel_name', header: 'Panel Name', width: '20%' },
    { key: 'panel_code', header: 'Code', width: '12%' },
    {
      key: 'total_sales',
      header: 'Total Sales',
      render: (value) => <span className="font-semibold text-gray-900 dark:text-gray-100">{value}</span>,
    },
    {
      key: 'gross_revenue',
      header: 'Gross Revenue',
      render: (value) => <span className="text-gray-900 dark:text-gray-100">₹{value?.toFixed(2)}</span>,
    },
    {
      key: 'commission',
      header: 'Commission (10%)',
      render: (value) => (
        <span className="text-blue-600 dark:text-blue-400 font-semibold">₹{value?.toFixed(2)}</span>
      ),
    },
    {
      key: 'logistics_cost',
      header: 'Logistics (5%)',
      render: (value) => (
        <span className="text-orange-600 dark:text-orange-400">₹{value?.toFixed(2)}</span>
      ),
    },
    {
      key: 'net_payable',
      header: 'Net Payable',
      render: (value) => (
        <span className="text-green-600 dark:text-green-400 font-bold text-lg">₹{value?.toFixed(2)}</span>
      ),
    },
    {
      key: 'settlement_status',
      header: 'Status',
      render: (value) => {
        const statusColors = {
          Pending: 'bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200',
          Paid: 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200',
          Processing: 'bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200',
        };
        return (
          <span
            className={`px-3 py-1 rounded-full text-xs font-medium ${
              statusColors[value as keyof typeof statusColors] ||
              'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
            }`}
          >
            {value || 'Pending'}
          </span>
        );
      },
    },
  ];

  const totalPayable =
    data?.reduce((sum: number, item: any) => sum + (item.net_payable || 0), 0) || 0;
  const totalCommission =
    data?.reduce((sum: number, item: any) => sum + (item.commission || 0), 0) || 0;

  return (
    <div>
      <PageHeader
        title="Panel Settlement Report"
        description="Calculate settlements with 10% commission and 5% logistics deductions"
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
        <div className="card bg-green-50 dark:bg-green-900/20">
          <p className="text-sm text-gray-600 dark:text-gray-400">Total Payable</p>
          <p className="text-3xl font-bold text-green-600 dark:text-green-400 mt-2">
            ₹{totalPayable.toFixed(2)}
          </p>
        </div>
        <div className="card bg-blue-50 dark:bg-blue-900/20">
          <p className="text-sm text-gray-600 dark:text-gray-400">Total Commission</p>
          <p className="text-3xl font-bold text-blue-600 dark:text-blue-400 mt-2">
            ₹{totalCommission.toFixed(2)}
          </p>
        </div>
        <div className="card bg-purple-50 dark:bg-purple-900/20">
          <p className="text-sm text-gray-600 dark:text-gray-400">Panels to Settle</p>
          <p className="text-3xl font-bold text-purple-600 dark:text-purple-400 mt-2">{data?.length || 0}</p>
        </div>
      </div>

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
        <h2 className="mb-4 text-gray-900 dark:text-gray-100">Settlement Details</h2>
        {isLoading ? (
          <LoadingSpinner message="Calculating settlements..." />
        ) : (
          <DataTable
            data={data || []}
            columns={columns}
            emptyMessage="No panel sales data available for settlement"
          />
        )}
      </div>
    </div>
  );
}
