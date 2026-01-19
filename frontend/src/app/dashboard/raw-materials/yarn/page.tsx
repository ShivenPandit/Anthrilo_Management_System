'use client';

import { PageHeader } from '@/components/ui/Common';

export default function YarnPage() {
  return (
    <div>
      <PageHeader
        title="Yarn Management"
        description="Manage yarn inventory and procurement"
      />
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-blue-500">
          <h3 className="mb-2 text-gray-900 dark:text-gray-100">Yarn Inventory</h3>
          <p className="text-gray-600 dark:text-gray-400 text-sm mb-4">Track current yarn stock levels</p>
          <button className="btn btn-primary w-full">View Inventory</button>
        </div>
        
        <div className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-green-500">
          <h3 className="mb-2 text-gray-900 dark:text-gray-100">Purchase Orders</h3>
          <p className="text-gray-600 dark:text-gray-400 text-sm mb-4">Manage yarn purchase orders</p>
          <button className="btn btn-primary w-full">View Orders</button>
        </div>
        
        <div className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-purple-500">
          <h3 className="mb-2 text-gray-900 dark:text-gray-100">Suppliers</h3>
          <p className="text-gray-600 dark:text-gray-400 text-sm mb-4">Manage yarn suppliers</p>
          <button className="btn btn-primary w-full">View Suppliers</button>
        </div>
      </div>
    </div>
  );
}
