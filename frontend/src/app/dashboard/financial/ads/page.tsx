'use client';

import { PageHeader } from '@/components/ui/Common';

export default function PaidAdsPage() {
  return (
    <div>
      <PageHeader
        title="Paid Advertising"
        description="Manage and track paid marketing campaigns"
        action={{
          label: '+ New Campaign',
          onClick: () => {},
        }}
      />
      
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Active Campaigns</p>
          <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-2">0</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Total Spend</p>
          <p className="text-3xl font-bold text-red-600 dark:text-red-400 mt-2">₹0</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Impressions</p>
          <p className="text-3xl font-bold text-blue-600 dark:text-blue-400 mt-2">0</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Conversions</p>
          <p className="text-3xl font-bold text-green-600 dark:text-green-400 mt-2">0</p>
        </div>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="mb-4 text-gray-900 dark:text-gray-100">Campaign Performance</h3>
          <p className="text-gray-600 dark:text-gray-400">No active campaigns. Create a campaign to start tracking performance.</p>
        </div>
        
        <div className="card">
          <h3 className="mb-4 text-gray-900 dark:text-gray-100">Platform Distribution</h3>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-700 dark:text-gray-300">Facebook</span>
              <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">₹0</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-700 dark:text-gray-300">Instagram</span>
              <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">₹0</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-700 dark:text-gray-300">Google Ads</span>
              <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">₹0</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
