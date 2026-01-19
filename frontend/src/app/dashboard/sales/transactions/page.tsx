'use client';

import { PageHeader } from '@/components/ui/Common';

export default function SalesTransactionsPage() {
  return (
    <div>
      <PageHeader
        title="Sales Transactions"
        description="Record and manage all sales transactions"
        action={{
          label: '+ New Sale',
          onClick: () => {},
        }}
      />
      
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Today's Sales</p>
          <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-2">0</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">This Week</p>
          <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-2">0</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">This Month</p>
          <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-2">0</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Revenue</p>
          <p className="text-3xl font-bold text-green-600 dark:text-green-400 mt-2">₹0</p>
        </div>
      </div>
      
      <div className="card">
        <h2 className="mb-4 text-gray-900 dark:text-gray-100">Recent Transactions</h2>
        <p className="text-gray-600 dark:text-gray-400">No sales transactions recorded yet.</p>
      </div>
    </div>
  );
}
