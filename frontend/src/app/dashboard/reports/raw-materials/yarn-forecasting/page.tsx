'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { rawMaterialsReports } from '@/lib/api/reports';
import { DataTable, Column } from '@/components/ui/DataTable';
import { PageHeader, LoadingSpinner } from '@/components/ui/Common';
import { FilterInput, ReportFilters } from '@/components/ui/Filters';

export default function YarnForecastingPage() {
  const [filters, setFilters] = useState({ forecast_days: '30' });

  const { data, isLoading } = useQuery({
    queryKey: ['yarnForecasting', filters],
    queryFn: async () => {
      const response = await rawMaterialsReports.getYarnForecasting({
        forecast_days: parseInt(filters.forecast_days),
      });
      return response.data;
    },
  });

  const columns: Column<any>[] = [
    { key: 'yarn_type', header: 'Yarn Type', width: '25%' },
    {
      key: 'current_stock',
      header: 'Current Stock',
      render: (value) => <span className="font-semibold text-gray-900 dark:text-gray-100">{value?.toFixed(2)}</span>,
    },
    {
      key: 'avg_daily_consumption',
      header: 'Avg Daily Usage',
      render: (value) => <span className="text-gray-700 dark:text-gray-300">{value?.toFixed(2)}</span>,
    },
    {
      key: 'forecasted_demand',
      header: 'Forecasted Demand',
      render: (value) => (
        <span className="text-blue-600 dark:text-blue-400 font-semibold">{value?.toFixed(2)}</span>
      ),
    },
    {
      key: 'days_until_stockout',
      header: 'Days to Stockout',
      render: (value) => {
        const days = Math.round(value);
        const colorClass =
          days < 7 ? 'text-red-600 dark:text-red-400' : days < 15 ? 'text-yellow-600 dark:text-yellow-400' : 'text-green-600 dark:text-green-400';
        return <span className={`font-bold ${colorClass}`}>{days}</span>;
      },
    },
    {
      key: 'recommended_order',
      header: 'Recommended Order',
      render: (value) => (
        <span className="text-purple-600 dark:text-purple-400 font-semibold">{value?.toFixed(2)}</span>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Yarn Forecasting Report"
        description="AI-powered demand forecasting for yarn inventory planning"
      />

      <ReportFilters onApplyFilters={setFilters}>
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
        <h2 className="mb-4 text-gray-900 dark:text-gray-100">Forecast Analysis</h2>
        {isLoading ? (
          <LoadingSpinner message="Calculating forecasts..." />
        ) : (
          <DataTable data={data || []} columns={columns} />
        )}
      </div>
    </div>
  );
}
