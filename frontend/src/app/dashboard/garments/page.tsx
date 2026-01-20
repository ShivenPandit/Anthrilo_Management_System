'use client';

import { PageHeader } from '@/components/ui/Common';
import Link from 'next/link';

export default function GarmentsPage() {
  const modules = [
    {
      title: 'Master Data',
      description: 'Manage garment products, SKUs, and pricing',
      icon: '👕',
      href: '/dashboard/garments/master',
      color: 'blue',
    },
    {
      title: 'Inventory',
      description: 'Track finished goods inventory',
      icon: '📦',
      href: '/dashboard/garments/inventory',
      color: 'green',
    },
    {
      title: 'Production',
      description: 'Production planning and tracking',
      icon: '🏭',
      href: '/dashboard/garments/production',
      color: 'purple',
    },
  ];

  const quickActions = [
    {
      title: 'Add New Garment',
      description: 'Create new product in master data',
      icon: '➕',
      action: 'add-garment',
    },
    {
      title: 'Update Stock',
      description: 'Update inventory levels',
      icon: '📊',
      action: 'update-stock',
    },
    {
      title: 'Production Plan',
      description: 'Create new production plan',
      icon: '📋',
      action: 'production-plan',
    },
  ];

  return (
    <div>
      <PageHeader
        title="Garment Management"
        description="Manage garment products, inventory, and production"
      />

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="card hover:shadow-xl transition-shadow bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20">
          <p className="text-sm text-gray-600 dark:text-gray-400">Total Products</p>
          <p className="text-3xl font-bold text-blue-600 dark:text-blue-400 mt-2">0</p>
          <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">Active SKUs</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20">
          <p className="text-sm text-gray-600 dark:text-gray-400">Total Stock</p>
          <p className="text-3xl font-bold text-green-600 dark:text-green-400 mt-2">0</p>
          <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">Units Available</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/20 dark:to-purple-800/20">
          <p className="text-sm text-gray-600 dark:text-gray-400">In Production</p>
          <p className="text-3xl font-bold text-purple-600 dark:text-purple-400 mt-2">0</p>
          <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">Active Plans</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow bg-gradient-to-br from-orange-50 to-orange-100 dark:from-orange-900/20 dark:to-orange-800/20">
          <p className="text-sm text-gray-600 dark:text-gray-400">Stock Value</p>
          <p className="text-3xl font-bold text-orange-600 dark:text-orange-400 mt-2">₹0</p>
          <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">Total Inventory</p>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="mb-8">
        <h2 className="text-xl font-semibold mb-4 text-gray-900 dark:text-gray-100">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {quickActions.map((action) => (
            <button
              key={action.action}
              className="card hover:shadow-xl hover:scale-105 transition-all text-left border-l-4 border-l-primary-500"
            >
              <div className="text-3xl mb-2">{action.icon}</div>
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">{action.title}</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">{action.description}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Management Modules */}
      <div>
        <h2 className="text-xl font-semibold mb-4 text-gray-900 dark:text-gray-100">Management Modules</h2>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {modules.map((module) => (
            <Link
              key={module.href}
              href={module.href}
              className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-green-500 dark:border-l-green-400"
            >
              <div className="text-4xl mb-3">{module.icon}</div>
              <h3 className="mb-2 text-gray-900 dark:text-gray-100 font-semibold">{module.title}</h3>
              <p className="text-gray-600 dark:text-gray-400 text-sm">{module.description}</p>
              <div className="mt-4 text-primary-600 dark:text-primary-400 text-sm font-medium">
                Open Module →
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
