'use client';

import { PageHeader } from '@/components/ui/Common';

export default function GarmentProductionPage() {
  return (
    <div>
      <PageHeader
        title="Production Planning"
        description="Manage garment production plans and tracking"
      />
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <div className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-blue-500">
          <h3 className="mb-2 text-gray-900 dark:text-gray-100">Create Production Plan</h3>
          <p className="text-gray-600 dark:text-gray-400 text-sm mb-4">Plan new production batches</p>
          <button className="btn btn-primary w-full">New Plan</button>
        </div>
        
        <div className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-green-500">
          <h3 className="mb-2 text-gray-900 dark:text-gray-100">Active Plans</h3>
          <p className="text-gray-600 dark:text-gray-400 text-sm mb-4">Monitor ongoing production</p>
          <button className="btn btn-primary w-full">View Plans</button>
        </div>
        
        <div className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-purple-500">
          <h3 className="mb-2 text-gray-900 dark:text-gray-100">Quality Control</h3>
          <p className="text-gray-600 dark:text-gray-400 text-sm mb-4">Track quality metrics</p>
          <button className="btn btn-primary w-full">View Reports</button>
        </div>
      </div>
      
      <div className="card">
        <h2 className="mb-4 text-gray-900 dark:text-gray-100">Recent Production Plans</h2>
        <p className="text-gray-600 dark:text-gray-400">No production plans created yet.</p>
      </div>
    </div>
  );
}
