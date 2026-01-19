'use client';

import { PageHeader } from '@/components/ui/Common';

export default function PanelsPage() {
  return (
    <div>
      <PageHeader
        title="Panel Management"
        description="Manage retail panels and distributors"
        action={{
          label: '+ Add Panel',
          onClick: () => {},
        }}
      />
      
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Active Panels</p>
          <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-2">0</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Retail Panels</p>
          <p className="text-3xl font-bold text-blue-600 dark:text-blue-400 mt-2">0</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Wholesale Panels</p>
          <p className="text-3xl font-bold text-purple-600 dark:text-purple-400 mt-2">0</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Total Sales</p>
          <p className="text-3xl font-bold text-green-600 dark:text-green-400 mt-2">₹0</p>
        </div>
      </div>
      
      <div className="card">
        <h2 className="mb-4 text-gray-900 dark:text-gray-100">Panel Directory</h2>
        <p className="text-gray-600 dark:text-gray-400">No panels registered yet. Add panels to start tracking sales.</p>
      </div>
    </div>
  );
}
