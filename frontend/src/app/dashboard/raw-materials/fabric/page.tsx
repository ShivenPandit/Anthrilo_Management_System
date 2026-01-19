'use client';

import { PageHeader } from '@/components/ui/Common';

export default function FabricPage() {
  return (
    <div>
      <PageHeader
        title="Fabric Management"
        description="Manage fabric inventory and processes"
      />
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-blue-500">
          <h3 className="mb-2 text-gray-900 dark:text-gray-100">Fabric Inventory</h3>
          <p className="text-gray-600 dark:text-gray-400 text-sm mb-4">Track current fabric stock</p>
          <button className="btn btn-primary w-full">View Inventory</button>
        </div>
        
        <div className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-green-500">
          <h3 className="mb-2 text-gray-900 dark:text-gray-100">Knitting Status</h3>
          <p className="text-gray-600 dark:text-gray-400 text-sm mb-4">Monitor knitting operations</p>
          <button className="btn btn-primary w-full">View Status</button>
        </div>
        
        <div className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-purple-500">
          <h3 className="mb-2 text-gray-900 dark:text-gray-100">Quality Check</h3>
          <p className="text-gray-600 dark:text-gray-400 text-sm mb-4">Fabric quality inspection</p>
          <button className="btn btn-primary w-full">View Reports</button>
        </div>
      </div>
    </div>
  );
}
