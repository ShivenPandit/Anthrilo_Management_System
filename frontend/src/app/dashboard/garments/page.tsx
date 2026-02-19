'use client';

import { useQuery } from '@tanstack/react-query';
import { ucCatalog, ucSales } from '@/lib/api/uc';
import { PageHeader, StatCard, LoadingSpinner } from '@/components/ui/Common';
import Link from 'next/link';

export default function GarmentsPage() {
  const { data: catalogData, isLoading: loadingCatalog } = useQuery({
    queryKey: ['uc-garments-overview'],
    queryFn: async () => {
      const response = await ucCatalog.searchItems({
        displayStart: 0,
        displayLength: 1,
        getInventorySnapshot: true,
      });
      return response.data;
    },
    staleTime: 5 * 60 * 1000,
  });

  const { data: todayData, isLoading: loadingToday } = useQuery({
    queryKey: ['unicommerce-today'],
    queryFn: async () => {
      const response = await ucSales.getToday();
      return response.data;
    },
    staleTime: 2 * 60 * 1000,
  });

  const totalProducts = catalogData?.totalRecords || 0;
  const todayOrders = todayData?.summary?.total_orders || 0;
  const todayRevenue = todayData?.summary?.total_revenue || 0;
  const isLoading = loadingCatalog || loadingToday;

  const modules = [
    {
      title: 'Master Data',
      description: 'Manage garment products, SKUs, and pricing',
      icon: '👕',
      href: '/dashboard/garments/master',
      color: 'from-blue-500 to-indigo-500',
    },
    {
      title: 'Inventory',
      description: 'Track finished goods inventory',
      icon: '📦',
      href: '/dashboard/garments/inventory',
      color: 'from-emerald-500 to-teal-500',
    },
    {
      title: 'Orders',
      description: 'Real-time orders from Unicommerce',
      icon: '🛒',
      href: '/dashboard/garments/production',
      color: 'from-purple-500 to-violet-500',
    },
    {
      title: 'Best SKUs',
      description: 'Top-performing SKUs by month',
      icon: '🏆',
      href: '/dashboard/garments/best-skus',
      color: 'from-amber-500 to-orange-500',
    },
    {
      title: 'SKU Velocity',
      description: 'Fast & slow moving SKUs by month',
      icon: '📈',
      href: '/dashboard/garments/sku-velocity',
      color: 'from-rose-500 to-pink-500',
    },
  ];

  return (
    <div>
      <PageHeader
        title="Garment Management"
        description="Manage garment products, inventory, and production"
      />

      {/* Stats from real UC data */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <StatCard
          title="Total Products"
          value={isLoading ? '...' : totalProducts.toLocaleString()}
          icon="📦"
          color="blue"
        />
        <StatCard
          title="Today's Orders"
          value={isLoading ? '...' : todayOrders.toLocaleString()}
          icon="🛒"
          color="green"
        />
        <StatCard
          title="Today's Revenue"
          value={isLoading ? '...' : `₹${(todayRevenue / 1000).toFixed(1)}K`}
          icon="💰"
          color="purple"
        />
        <StatCard
          title="Avg Order Value"
          value={isLoading ? '...' : `₹${todayOrders > 0 ? (todayRevenue / todayOrders).toFixed(0) : '0'}`}
          icon="📊"
          color="yellow"
        />
      </div>

      {/* Management Modules */}
      <div>
        <h2 className="text-xl font-semibold mb-4 text-slate-900 dark:text-white">Management Modules</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
          {modules.map((module) => (
            <Link
              key={module.href}
              href={module.href}
              className="card group hover:shadow-2xl transition-all duration-300 relative overflow-hidden"
            >
              <div className={`absolute inset-0 bg-gradient-to-br ${module.color} opacity-0 group-hover:opacity-5 transition-opacity duration-300`} />
              <div className="relative">
                <div className="text-4xl mb-4 transform group-hover:scale-110 transition-transform duration-300">{module.icon}</div>
                <h3 className="text-lg font-semibold mb-2 text-slate-900 dark:text-white group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">{module.title}</h3>
                <p className="text-sm text-slate-600 dark:text-slate-400">{module.description}</p>
                <div className="mt-4 text-primary-600 dark:text-primary-400 text-sm font-medium flex items-center gap-1">
                  Open Module
                  <svg className="w-4 h-4 transform group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
