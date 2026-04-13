'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ucSales } from '@/features/sales/api';
import { DataTable, Column } from '@/components/ui/DataTable';
import { PageHeader, ProgressLoader, StatCard, ErrorPanel } from '@/components/ui/Common';

export default function TopSellersPage() {
  const [period, setPeriod] = useState('last_7_days');

  const formatChannelName = (channel: string) =>
    (channel || 'UNKNOWN').replace(/_/g, ' ');

  const { data, isLoading, error } = useQuery({
    queryKey: ['uc-top-sellers', period],
    queryFn: async () => {
      const response = await ucSales.getSalesBySku({ period });
      return response.data;
    },
    staleTime: 120_000,
  });

  const allSkus = useMemo(() => data?.skus ?? [], [data?.skus]);
  const topByQty = allSkus.slice(0, 50);
  const summary = useMemo(() => data?.summary ?? {}, [data?.summary]);

  const avgRevenuePerSku = summary.total_skus > 0 ? summary.total_revenue / summary.total_skus : 0;
  const avgQtyPerSku = summary.total_skus > 0 ? summary.total_quantity / summary.total_skus : 0;

  const rankedData = topByQty.map((item: any, idx: number) => ({ ...item, rank: idx + 1 }));

  const channelTopProducts = useMemo(() => {
    const rows: any[] = [];

    allSkus.forEach((skuItem: any) => {
      const channels = skuItem?.channels || {};

      Object.entries(channels).forEach(([channelName, chData]: any) => {
        rows.push({
          channel_name: channelName,
          sku: skuItem.sku,
          name: skuItem.name,
          total_quantity: chData?.quantity || 0,
          total_revenue: chData?.revenue || 0,
        });
      });
    });

    const grouped: Record<string, any[]> = {};
    rows.forEach((row) => {
      if (!grouped[row.channel_name]) grouped[row.channel_name] = [];
      grouped[row.channel_name].push(row);
    });

    const flattened: any[] = [];
    Object.entries(grouped).forEach(([channelName, items]: any) => {
      const channelRevenue = items.reduce((acc: number, item: any) => acc + (item.total_revenue || 0), 0);
      const sorted = [...items]
        .sort((a, b) => {
          if (b.total_revenue !== a.total_revenue) {
            return b.total_revenue - a.total_revenue;
          }
          if (b.total_quantity !== a.total_quantity) {
            return b.total_quantity - a.total_quantity;
          }
          return String(a.sku).localeCompare(String(b.sku));
        })
        .slice(0, 5);

      sorted.forEach((item, idx) => {
        const sharePct = channelRevenue > 0 ? ((item.total_revenue / channelRevenue) * 100) : 0;
        flattened.push({
          ...item,
          channel_label: formatChannelName(channelName),
          channel_rank: idx + 1,
          channel_share_pct: Number(sharePct.toFixed(1)),
        });
      });
    });

    return flattened.sort((a, b) => {
      if (a.channel_label === b.channel_label) return a.channel_rank - b.channel_rank;
      return a.channel_label.localeCompare(b.channel_label);
    });
  }, [allSkus]);

  const columns: Column<any>[] = [
    {
      key: 'rank',
      header: '#',
      width: '5%',
      render: (value: any) => <span className="font-bold text-gray-500">{value}</span>,
    },
    { key: 'sku', header: 'SKU', width: '14%' },
    { key: 'name', header: 'Product Name', width: '22%' },
    {
      key: 'total_quantity',
      header: 'Units Sold',
      width: '10%',
      render: (value) => <span className="font-bold text-gray-900 dark:text-gray-100">{value}</span>,
    },
    {
      key: 'total_revenue',
      header: 'Revenue',
      width: '13%',
      render: (value) => (
        <span className="text-green-600 dark:text-green-400 font-bold">₹{(value || 0).toFixed(2)}</span>
      ),
    },
    { key: 'order_count', header: 'Orders', width: '8%' },
    {
      key: 'avg_selling_price',
      header: 'Avg Price',
      width: '10%',
      render: (value) => <span className="text-gray-900 dark:text-gray-100">₹{(value || 0).toFixed(0)}</span>,
    },
    {
      key: 'channels',
      header: 'Top Channel',
      width: '13%',
      render: (value) => {
        if (!value || typeof value !== 'object') return '-';
        const sorted = Object.entries(value).sort(
          (a: any, b: any) => (b[1]?.quantity || 0) - (a[1]?.quantity || 0),
        );
        const top = sorted[0];
        return top ? (
          <span className="px-2 py-0.5 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded text-xs font-medium">
            {top[0]}: {(top[1] as any)?.quantity || 0}
          </span>
        ) : (
          '-'
        );
      },
    },
  ];

  const channelColumns: Column<any>[] = [
    {
      key: 'channel_label',
      header: 'Channel',
      width: '16%',
      render: (value: any) => <span className="font-medium text-gray-800 dark:text-gray-200">{value}</span>,
    },
    {
      key: 'channel_rank',
      header: 'Rank',
      width: '6%',
      render: (value: any) => <span className="font-bold text-gray-500">#{value}</span>,
    },
    { key: 'sku', header: 'SKU', width: '12%' },
    { key: 'name', header: 'Product Name', width: '26%' },
    {
      key: 'total_quantity',
      header: 'Units Sold',
      width: '10%',
      render: (value) => <span className="font-bold text-gray-900 dark:text-gray-100">{value}</span>,
    },
    {
      key: 'total_revenue',
      header: 'Revenue',
      width: '14%',
      render: (value) => <span className="text-green-600 dark:text-green-400 font-bold">₹{(value || 0).toFixed(2)}</span>,
    },
    {
      key: 'channel_share_pct',
      header: 'Channel Share',
      width: '10%',
      render: (value) => <span className="text-gray-700 dark:text-gray-300">{value}%</span>,
    },
  ];

  return (
    <div>
      <PageHeader
        title="Top Selling Products"
        description="Best performing SKUs from Unicommerce sales data"
      />

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
        <StatCard title="Total SKUs Sold" value={summary.total_skus || 0} icon="📦" color="blue" />
        <StatCard title="Total Units" value={summary.total_quantity || 0} icon="🛒" color="purple" />
        <StatCard title="Avg Revenue/SKU" value={`₹${avgRevenuePerSku.toFixed(0)}`} icon="📊" color="green" />
        <StatCard title="Avg Qty/SKU" value={avgQtyPerSku.toFixed(1)} icon="📈" color="yellow" />
      </div>

      <div className="card mb-4">
        <div className="flex gap-2">
          {[
            { key: 'today', label: 'Today' },
            { key: 'yesterday', label: 'Yesterday' },
            { key: 'last_7_days', label: '7 Days' },
            { key: 'last_30_days', label: '30 Days' },
          ].map((p) => (
            <button
              key={p.key}
              onClick={() => setPeriod(p.key)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${period === p.key
                ? 'bg-primary-600 text-white'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {error && <ErrorPanel message={(error as any)?.message || 'Failed to load data'} />}

      <div className="card">
        <h2 className="mb-4 text-gray-900 dark:text-gray-100">Top 50 by Units Sold</h2>
        <ProgressLoader loading={isLoading} stages={[
          { at: 0, label: 'Connecting to Unicommerce…' },
          { at: 20, label: 'Fetching sales data…' },
          { at: 50, label: 'Ranking top sellers…' },
          { at: 80, label: 'Finalizing…' },
        ]} />
        {!isLoading && (
          <DataTable data={rankedData} columns={columns} emptyMessage="No sales data for this period." />
        )}
      </div>

      <div className="card mt-6">
        <h2 className="mb-1 text-gray-900 dark:text-gray-100">Channel-wise Top Performing Products</h2>
        <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">
          Top 5 products by revenue within each channel for the selected period.
        </p>
        <ProgressLoader loading={isLoading} stages={[
          { at: 0, label: 'Grouping by channel…' },
          { at: 40, label: 'Ranking products per channel…' },
          { at: 80, label: 'Preparing table…' },
        ]} />
        {!isLoading && (
          <DataTable
            data={channelTopProducts}
            columns={channelColumns}
            emptyMessage="No channel-wise product data for this period."
          />
        )}
      </div>
    </div>
  );
}
