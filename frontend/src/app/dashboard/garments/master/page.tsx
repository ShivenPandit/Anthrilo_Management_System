'use client';

import { useQuery } from '@tanstack/react-query';
import { garmentApi } from '@/lib/api';
import { useState } from 'react';
import { GarmentForm } from '@/components/forms/GarmentForm';
import { DataTable, Column } from '@/components/ui/DataTable';
import { PageHeader } from '@/components/ui/Common';

export default function GarmentMasterPage() {
  const [search, setSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [selectedGarment, setSelectedGarment] = useState(null);

  const { data: garments, isLoading } = useQuery({
    queryKey: ['garments'],
    queryFn: async () => {
      const response = await garmentApi.getAll();
      return response.data;
    },
  });

  const filteredGarments = garments?.filter((g: any) =>
    g.name?.toLowerCase().includes(search.toLowerCase()) ||
    g.sku?.toLowerCase().includes(search.toLowerCase())
  );

  const columns: Column<any>[] = [
    { key: 'sku', header: 'SKU', width: '15%' },
    { key: 'name', header: 'Name', width: '20%' },
    { key: 'category', header: 'Category', width: '12%' },
    { key: 'size', header: 'Size', width: '8%' },
    {
      key: 'mrp',
      header: 'MRP',
      render: (value) => <span className="text-gray-900 dark:text-gray-100">₹{value?.toFixed(2)}</span>,
    },
    {
      key: 'selling_price',
      header: 'Selling Price',
      render: (value) => <span className="text-gray-900 dark:text-gray-100">₹{value?.toFixed(2)}</span>,
    },
    {
      key: 'is_active',
      header: 'Status',
      render: (value) => (
        <span
          className={`px-3 py-1 rounded-full text-xs font-medium ${
            value
              ? 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200'
              : 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
          }`}
        >
          {value ? 'Active' : 'Inactive'}
        </span>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Garment Master Data"
        description="Manage all garment products"
        action={{
          label: showForm ? 'Cancel' : '+ Add Garment',
          onClick: () => {
            setShowForm(!showForm);
            setSelectedGarment(null);
          },
        }}
      />

      {showForm && (
        <div className="card mb-6">
          <h2 className="mb-4 text-gray-900 dark:text-gray-100">{selectedGarment ? 'Edit' : 'Create'} Garment</h2>
          <GarmentForm
            initialData={selectedGarment}
            onSuccess={() => {
              setShowForm(false);
              setSelectedGarment(null);
            }}
            onCancel={() => {
              setShowForm(false);
              setSelectedGarment(null);
            }}
          />
        </div>
      )}

      <div className="card mb-4">
        <input
          type="text"
          placeholder="Search by name or SKU..."
          className="input"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="card">
        <h2 className="mb-4 text-gray-900 dark:text-gray-100">Garment List</h2>
        <DataTable
          data={filteredGarments || []}
          columns={columns}
          isLoading={isLoading}
          emptyMessage="No garments found. Create your first garment to get started."
          onRowClick={(row) => {
            setSelectedGarment(row);
            setShowForm(true);
          }}
        />
      </div>
    </div>
  );
}
