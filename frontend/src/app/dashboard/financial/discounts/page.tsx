'use client';

import { PageHeader } from '@/components/ui/Common';
import Link from 'next/link';

export default function DiscountsPage() {
  return (
    <div>
      <PageHeader
        title="Discount Management"
        description="Manage product discounts and promotional pricing"
      />
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <Link href="/dashboard/reports/sales/discount-general" className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-purple-500">
          <h3 className="mb-2 text-gray-900 dark:text-gray-100">General Discount Report</h3>
          <p className="text-gray-600 dark:text-gray-400 text-sm mb-4">View product-wise discount analysis with discount buckets</p>
          <button className="btn btn-primary">View Report</button>
        </Link>
        
        <Link href="/dashboard/reports/sales/discount-by-panel" className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-blue-500">
          <h3 className="mb-2 text-gray-900 dark:text-gray-100">Panel-wise Discounts</h3>
          <p className="text-gray-600 dark:text-gray-400 text-sm mb-4">Track discounts given by each panel</p>
          <button className="btn btn-primary">View Report</button>
        </Link>
      </div>
      
      <div className="card">
        <h2 className="mb-4 text-gray-900 dark:text-gray-100">Discount Analytics</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:shadow-lg transition-shadow">
            <p className="text-sm text-gray-600 dark:text-gray-400">Average Discount</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-2">0%</p>
          </div>
          <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:shadow-lg transition-shadow">
            <p className="text-sm text-gray-600 dark:text-gray-400">Total Discount Given</p>
            <p className="text-2xl font-bold text-red-600 dark:text-red-400 mt-2">₹0</p>
          </div>
          <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:shadow-lg transition-shadow">
            <p className="text-sm text-gray-600 dark:text-gray-400">Products with Discount</p>
            <p className="text-2xl font-bold text-blue-600 dark:text-blue-400 mt-2">0</p>
          </div>
        </div>
      </div>
    </div>
  );
}
