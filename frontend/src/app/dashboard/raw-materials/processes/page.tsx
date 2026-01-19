'use client';

import { PageHeader } from '@/components/ui/Common';

export default function ProcessesPage() {
  return (
    <div>
      <PageHeader
        title="Processing Operations"
        description="Manage dyeing, finishing, and printing processes"
      />
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div className="card">
          <h3 className="mb-4 text-gray-900 dark:text-gray-100">Active Processes</h3>
          <div className="space-y-3">
            <div className="border-b border-gray-200 dark:border-gray-700 pb-3">
              <div className="flex justify-between items-center">
                <div>
                  <p className="font-medium text-gray-900 dark:text-gray-100">Dyeing - Batch #234</p>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Navy Blue - 500 kg</p>
                </div>
                <span className="px-3 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded-full text-xs font-medium">
                  In Progress
                </span>
              </div>
            </div>
            <div className="border-b border-gray-200 dark:border-gray-700 pb-3">
              <div className="flex justify-between items-center">
                <div>
                  <p className="font-medium text-gray-900 dark:text-gray-100">Finishing - Batch #235</p>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Cotton - 300 kg</p>
                </div>
                <span className="px-3 py-1 bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200 rounded-full text-xs font-medium">
                  Pending
                </span>
              </div>
            </div>
          </div>
        </div>
        
        <div className="card">
          <h3 className="mb-4 text-gray-900 dark:text-gray-100">Process Categories</h3>
          <div className="space-y-2">
            <button className="w-full text-left px-4 py-3 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
              <span className="font-medium text-gray-900 dark:text-gray-100">Dyeing</span>
              <p className="text-sm text-gray-600 dark:text-gray-400">Color application processes</p>
            </button>
            <button className="w-full text-left px-4 py-3 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
              <span className="font-medium text-gray-900 dark:text-gray-100">Finishing</span>
              <p className="text-sm text-gray-600 dark:text-gray-400">Final fabric treatment</p>
            </button>
            <button className="w-full text-left px-4 py-3 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
              <span className="font-medium text-gray-900 dark:text-gray-100">Printing</span>
              <p className="text-sm text-gray-600 dark:text-gray-400">Pattern and design application</p>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
