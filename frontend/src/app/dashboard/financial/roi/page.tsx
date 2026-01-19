'use client';

import { PageHeader } from '@/components/ui/Common';

export default function ROIAnalysisPage() {
  return (
    <div>
      <PageHeader
        title="ROI Analysis"
        description="Return on Investment analysis for marketing campaigns"
      />
      
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Total Investment</p>
          <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-2">₹0</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Revenue Generated</p>
          <p className="text-3xl font-bold text-green-600 dark:text-green-400 mt-2">₹0</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">ROI Percentage</p>
          <p className="text-3xl font-bold text-blue-600 dark:text-blue-400 mt-2">0%</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Net Profit</p>
          <p className="text-3xl font-bold text-purple-600 dark:text-purple-400 mt-2">₹0</p>
        </div>
      </div>
      
      <div className="card mb-6">
        <h2 className="mb-4 text-gray-900 dark:text-gray-100">Campaign ROI Breakdown</h2>
        <p className="text-gray-600 dark:text-gray-400 mb-4">Track return on investment for each marketing campaign</p>
        <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Campaign</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Spend</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Revenue</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">ROI</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Status</th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
                  No campaigns available for ROI analysis
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      
      <div className="card">
        <h3 className="mb-4 text-gray-900 dark:text-gray-100">ROI Formula</h3>
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
          <p className="text-sm text-blue-800 dark:text-blue-300 font-mono">
            ROI = ((Revenue - Investment) / Investment) × 100
          </p>
        </div>
      </div>
    </div>
  );
}
