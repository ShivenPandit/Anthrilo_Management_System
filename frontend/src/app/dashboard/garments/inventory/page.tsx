'use client';

import { PageHeader } from '@/components/ui/Common';

export default function GarmentInventoryPage() {
  return (
    <div>
      <PageHeader
        title="Garment Inventory"
        description="Track finished goods inventory across all locations"
      />
      
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Total Stock</p>
          <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-2">0</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Low Stock Items</p>
          <p className="text-3xl font-bold text-yellow-600 dark:text-yellow-400 mt-2">0</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Out of Stock</p>
          <p className="text-3xl font-bold text-red-600 dark:text-red-400 mt-2">0</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Total Value</p>
          <p className="text-3xl font-bold text-green-600 dark:text-green-400 mt-2">₹0</p>
        </div>
      </div>
      
      <div className="card">
        <h2 className="mb-4 text-gray-900 dark:text-gray-100">Inventory Overview</h2>
        <p className="text-gray-600 dark:text-gray-400">Add garment products in Master Data to see inventory here.</p>
      </div>
    </div>
  );
}
