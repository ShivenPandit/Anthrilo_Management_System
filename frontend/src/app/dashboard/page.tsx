'use client';

import { useQuery } from '@tanstack/react-query';
import { garmentApi, inventoryApi, salesApi } from '@/lib/api';

export default function DashboardPage() {
  // Fetch summary data
  const { data: garments } = useQuery({
    queryKey: ['garments'],
    queryFn: async () => {
      const response = await garmentApi.getAll({ is_active: true });
      return response.data;
    },
  });

  const { data: lowStock } = useQuery({
    queryKey: ['lowStock'],
    queryFn: async () => {
      const response = await inventoryApi.getLowStock(10);
      return response.data;
    },
  });

  const stats = [
    {
      name: 'Active Garments',
      value: garments?.length || 0,
      icon: '👕',
      color: 'bg-blue-500',
    },
    {
      name: 'Low Stock Items',
      value: lowStock?.length || 0,
      icon: '⚠️',
      color: 'bg-yellow-500',
    },
    {
      name: 'Today\'s Sales',
      value: '0',
      icon: '💰',
      color: 'bg-green-500',
    },
    {
      name: 'Active Panels',
      value: '0',
      icon: '🏪',
      color: 'bg-purple-500',
    },
  ];

  return (
    <div>
      <h1 className="mb-8">Dashboard Overview</h1>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {stats.map((stat) => (
          <div key={stat.name} className="card">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">{stat.name}</p>
                <p className="text-3xl font-bold text-gray-900 mt-2">{stat.value}</p>
              </div>
              <div className={`${stat.color} text-white p-3 rounded-lg text-2xl`}>
                {stat.icon}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="card hover:shadow-lg transition-shadow cursor-pointer">
          <h3 className="mb-2">Record Sale</h3>
          <p className="text-gray-600 text-sm">Quickly record a new sales transaction</p>
          <button className="btn btn-primary mt-4 w-full">New Sale</button>
        </div>

        <div className="card hover:shadow-lg transition-shadow cursor-pointer">
          <h3 className="mb-2">Update Inventory</h3>
          <p className="text-gray-600 text-sm">Adjust stock levels and locations</p>
          <button className="btn btn-primary mt-4 w-full">Update Stock</button>
        </div>

        <div className="card hover:shadow-lg transition-shadow cursor-pointer">
          <h3 className="mb-2">Production Plan</h3>
          <p className="text-gray-600 text-sm">Create a new production plan</p>
          <button className="btn btn-primary mt-4 w-full">New Plan</button>
        </div>
      </div>

      {/* Recent Activity */}
      <div className="card">
        <h2 className="mb-4">Recent Activity</h2>
        <div className="space-y-4">
          <div className="border-b pb-4">
            <div className="flex justify-between items-start">
              <div>
                <p className="font-medium">Low stock alert: Cotton T-Shirt</p>
                <p className="text-sm text-gray-500">Size M - Only 5 units remaining</p>
              </div>
              <span className="text-xs text-gray-400">2 hours ago</span>
            </div>
          </div>
          <div className="border-b pb-4">
            <div className="flex justify-between items-start">
              <div>
                <p className="font-medium">New sale recorded</p>
                <p className="text-sm text-gray-500">Panel: Amazon - ₹2,450</p>
              </div>
              <span className="text-xs text-gray-400">5 hours ago</span>
            </div>
          </div>
          <div className="pb-4">
            <div className="flex justify-between items-start">
              <div>
                <p className="font-medium">Production plan completed</p>
                <p className="text-sm text-gray-500">Summer Collection Batch #123</p>
              </div>
              <span className="text-xs text-gray-400">1 day ago</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
