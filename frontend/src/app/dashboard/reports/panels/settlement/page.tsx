'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ucSales } from '@/features/sales/api';
import { DataTable, Column } from '@/components/ui/DataTable';
import { PageHeader, ProgressLoader } from '@/components/ui/Common';
import {
  ReportDateMode,
  getTodayYmd,
  getYesterdayYmd,
  resolveReportDateRange,
} from '@/lib/report-date-range';

export default function ChannelRevenuePage() {
  const [mode, setMode] = useState<ReportDateMode>('weekly');
  const [anchorDate, setAnchorDate] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() - 1);
    return date.toISOString().split('T')[0];
  });
  const [fromDate, setFromDate] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() - 7);
    return date.toISOString().split('T')[0];
  });
  const [toDate, setToDate] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() - 1);
    return date.toISOString().split('T')[0];
  });

  const effectiveRange = useMemo(() => resolveReportDateRange({
    mode,
    anchorDate,
    fromDate,
    toDate,
  }), [mode, anchorDate, fromDate, toDate]);

  const period = useMemo(() => {
    const today = getTodayYmd();
    const yesterday = getYesterdayYmd();

    if (mode === 'daily' && effectiveRange.fromDate === today) return 'today';
    if (mode === 'daily' && effectiveRange.fromDate === yesterday) return 'yesterday';
    return 'last_7_days';
  }, [mode, effectiveRange.fromDate]);

  const { data, isLoading, error } = useQuery({
    queryKey: ['uc-channel-revenue', period],
    queryFn: async () => {
      const response = await ucSales.getChannelRevenue(period);
      return response.data;
    },
    staleTime: 120_000,
  });

  const channels = (data?.channels || []).map((ch: any) => ({
    ...ch,
    commission_est: (ch.revenue || 0) * 0.10,
    logistics_est: (ch.revenue || 0) * 0.05,
    net_payable: (ch.revenue || 0) * 0.85,
  }));

  const totalRevenue = data?.total_revenue || 0;
  const totalOrders = data?.total_orders || 0;

  const columns: Column<any>[] = [
    {
      key: 'channel', header: 'Channel / Marketplace', width: '18%',
      render: (value) => (
        <span className="px-3 py-1 rounded bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-medium">{value}</span>
      ),
    },
    {
      key: 'orders', header: 'Orders', width: '10%',
      render: (value) => <span className="font-semibold text-gray-900 dark:text-gray-100">{value}</span>,
    },
    {
      key: 'revenue', header: 'Gross Revenue', width: '14%',
      render: (value) => <span className="text-gray-900 dark:text-gray-100 font-semibold">₹{(value || 0).toFixed(2)}</span>,
    },
    {
      key: 'percentage', header: 'Share %', width: '10%',
      render: (value) => <span className="font-bold text-primary-600 dark:text-primary-400">{(value || 0).toFixed(1)}%</span>,
    },
    {
      key: 'commission_est', header: 'Commission (~10%)', width: '14%',
      render: (value) => <span className="text-blue-600 dark:text-blue-400 font-semibold">₹{(value || 0).toFixed(2)}</span>,
    },
    {
      key: 'logistics_est', header: 'Logistics (~5%)', width: '14%',
      render: (value) => <span className="text-orange-600 dark:text-orange-400">₹{(value || 0).toFixed(2)}</span>,
    },
    {
      key: 'net_payable', header: 'Est. Net (~85%)', width: '14%',
      render: (value) => <span className="text-green-600 dark:text-green-400 font-bold text-lg">₹{(value || 0).toFixed(2)}</span>,
    },
  ];

  return (
    <div className="page-section-gap">
      <PageHeader title="Channel Revenue & Settlement" description="Marketplace-wise revenue from Anthrilo with estimated deductions" />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <div className="card bg-green-50 dark:bg-green-900/20">
          <p className="text-sm text-gray-600 dark:text-gray-400">Total Revenue</p>
          <p className="text-3xl font-bold text-green-600 dark:text-green-400 mt-2">₹{(totalRevenue / 1000).toFixed(1)}K</p>
        </div>
        <div className="card bg-blue-50 dark:bg-blue-900/20">
          <p className="text-sm text-gray-600 dark:text-gray-400">Total Orders</p>
          <p className="text-3xl font-bold text-blue-600 dark:text-blue-400 mt-2">{totalOrders}</p>
        </div>
        <div className="card bg-purple-50 dark:bg-purple-900/20">
          <p className="text-sm text-gray-600 dark:text-gray-400">Active Channels</p>
          <p className="text-3xl font-bold text-purple-600 dark:text-purple-400 mt-2">{channels.length}</p>
        </div>
      </div>

      <div className="card">
        <div className="space-y-2">
          <div className="tab-strip">
            {[
              { key: 'daily', label: 'Daily' },
              { key: 'weekly', label: 'Weekly' },
              { key: 'monthly', label: 'Monthly' },
              { key: 'custom', label: 'Custom' },
            ].map((p) => (
              <button key={p.key} onClick={() => setMode(p.key as ReportDateMode)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${mode === p.key ? 'bg-primary-600 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'}`}>
                {p.label}
              </button>
            ))}
          </div>

          {mode === 'daily' && (
            <input
              type="date"
              value={anchorDate}
              onChange={(e) => setAnchorDate(e.target.value)}
              className="input w-full sm:w-auto"
            />
          )}

          {mode === 'custom' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} className="input w-full" />
              <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} className="input w-full" />
            </div>
          )}

          <div className="text-xs text-gray-500 dark:text-gray-400">{effectiveRange.label}</div>
        </div>
      </div>

      {error && (
        <div className="card bg-red-50 dark:bg-red-900/20 mb-4">
          <p className="text-red-600 dark:text-red-400">Error: {(error as any)?.message || 'Failed to load channel data'}</p>
        </div>
      )}

      <div className="card">
        <h2 className="mb-4 text-gray-900 dark:text-gray-100">Channel Settlement Details</h2>
        <ProgressLoader loading={isLoading} stages={[
          { at: 0, label: 'Connecting to Unicommerce…' },
          { at: 25, label: 'Fetching channel revenue…' },
          { at: 60, label: 'Building report…' },
          { at: 85, label: 'Finalizing…' },
        ]} />
        {!isLoading && (
          <DataTable data={channels} columns={columns} emptyMessage="No channel revenue data for this period." />
        )}
      </div>
    </div>
  );
}
