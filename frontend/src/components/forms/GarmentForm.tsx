'use client';

import { useState } from 'react';
import { garmentApi } from '@/lib/api';
import { useMutation, useQueryClient } from '@tanstack/react-query';

interface GarmentFormProps {
  initialData?: any;
  onSuccess?: () => void;
  onCancel?: () => void;
}

export function GarmentForm({ initialData, onSuccess, onCancel }: GarmentFormProps) {
  const queryClient = useQueryClient();
  const [formData, setFormData] = useState(
    initialData || {
      sku: '',
      name: '',
      category: '',
      subcategory: '',
      size: '',
      color: '',
      fabric_type: '',
      gsm: '',
      mrp: '',
      cost_price: '',
      selling_price: '',
      is_active: true,
    }
  );

  const mutation = useMutation({
    mutationFn: async (data: any) => {
      if (initialData?.id) {
        return await garmentApi.update(initialData.id, data);
      }
      return await garmentApi.create(data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['garments'] });
      onSuccess?.();
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate(formData);
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => {
    const { name, value, type } = e.target;
    setFormData((prev: any) => ({
      ...prev,
      [name]:
        type === 'number'
          ? parseFloat(value) || 0
          : type === 'checkbox'
          ? (e.target as HTMLInputElement).checked
          : value,
    }));
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            SKU <span className="text-red-500 dark:text-red-400">*</span>
          </label>
          <input
            type="text"
            name="sku"
            value={formData.sku}
            onChange={handleChange}
            required
            className="input"
            placeholder="e.g., TSHIRT-BLK-M-001"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Name <span className="text-red-500 dark:text-red-400">*</span>
          </label>
          <input
            type="text"
            name="name"
            value={formData.name}
            onChange={handleChange}
            required
            className="input"
            placeholder="e.g., Cotton T-Shirt"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Category <span className="text-red-500 dark:text-red-400">*</span>
          </label>
          <select
            name="category"
            value={formData.category}
            onChange={handleChange}
            required
            className="input"
          >
            <option value="">Select Category</option>
            <option value="T-Shirt">T-Shirt</option>
            <option value="Shirt">Shirt</option>
            <option value="Trouser">Trouser</option>
            <option value="Jeans">Jeans</option>
            <option value="Jacket">Jacket</option>
            <option value="Hoodie">Hoodie</option>
            <option value="Bundle">Bundle</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Subcategory</label>
          <input
            type="text"
            name="subcategory"
            value={formData.subcategory}
            onChange={handleChange}
            className="input"
            placeholder="e.g., Casual, Formal"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Size <span className="text-red-500 dark:text-red-400">*</span>
          </label>
          <select
            name="size"
            value={formData.size}
            onChange={handleChange}
            required
            className="input"
          >
            <option value="">Select Size</option>
            <option value="XS">XS</option>
            <option value="S">S</option>
            <option value="M">M</option>
            <option value="L">L</option>
            <option value="XL">XL</option>
            <option value="XXL">XXL</option>
            <option value="XXXL">XXXL</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Color</label>
          <input
            type="text"
            name="color"
            value={formData.color}
            onChange={handleChange}
            className="input"
            placeholder="e.g., Black, White, Navy"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Fabric Type</label>
          <input
            type="text"
            name="fabric_type"
            value={formData.fabric_type}
            onChange={handleChange}
            className="input"
            placeholder="e.g., Cotton, Polyester"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">GSM</label>
          <input
            type="number"
            name="gsm"
            value={formData.gsm}
            onChange={handleChange}
            className="input"
            placeholder="e.g., 180"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            MRP <span className="text-red-500 dark:text-red-400">*</span>
          </label>
          <input
            type="number"
            name="mrp"
            value={formData.mrp}
            onChange={handleChange}
            required
            step="0.01"
            className="input"
            placeholder="0.00"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Cost Price</label>
          <input
            type="number"
            name="cost_price"
            value={formData.cost_price}
            onChange={handleChange}
            step="0.01"
            className="input"
            placeholder="0.00"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Selling Price <span className="text-red-500 dark:text-red-400">*</span>
          </label>
          <input
            type="number"
            name="selling_price"
            value={formData.selling_price}
            onChange={handleChange}
            required
            step="0.01"
            className="input"
            placeholder="0.00"
          />
        </div>

        <div className="flex items-center">
          <input
            type="checkbox"
            name="is_active"
            checked={formData.is_active}
            onChange={handleChange}
            className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600 rounded"
          />
          <label className="ml-2 block text-sm text-gray-900 dark:text-gray-100">Active Product</label>
        </div>
      </div>

      <div className="flex justify-end space-x-3 pt-4 border-t dark:border-gray-700">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="btn btn-secondary"
            disabled={mutation.isPending}
          >
            Cancel
          </button>
        )}
        <button
          type="submit"
          className="btn btn-primary"
          disabled={mutation.isPending}
        >
          {mutation.isPending
            ? 'Saving...'
            : initialData
            ? 'Update Garment'
            : 'Create Garment'}
        </button>
      </div>

      {mutation.isError && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded">
          <p className="text-sm">
            Error: {(mutation.error as any)?.response?.data?.detail || 'Failed to save garment'}
          </p>
        </div>
      )}
    </form>
  );
}
