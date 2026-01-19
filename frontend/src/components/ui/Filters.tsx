'use client';

import React from 'react';

interface FilterInputProps {
  label: string;
  type?: 'text' | 'date' | 'select' | 'number';
  value: string | number;
  onChange: (value: string) => void;
  placeholder?: string;
  options?: { label: string; value: string }[];
  min?: string | number;
  max?: string | number;
}

export function FilterInput({
  label,
  type = 'text',
  value,
  onChange,
  placeholder,
  options,
  min,
  max,
}: FilterInputProps) {
  return (
    <div className="flex flex-col space-y-1">
      <label className="text-sm font-medium text-gray-700 dark:text-gray-300">{label}</label>
      {type === 'select' && options ? (
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500 dark:focus:ring-primary-400 transition-all"
        >
          <option value="">All</option>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          min={min}
          max={max}
          className="px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500 dark:focus:ring-primary-400 transition-all"
        />
      )}
    </div>
  );
}

interface ReportFiltersProps {
  onApplyFilters: (filters: any) => void;
  children: React.ReactNode;
}

export function ReportFilters({ onApplyFilters, children }: ReportFiltersProps) {
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const formData = new FormData(e.target as HTMLFormElement);
    const filters: any = {};
    formData.forEach((value, key) => {
      if (value) filters[key] = value;
    });
    onApplyFilters(filters);
  };

  return (
    <form onSubmit={handleSubmit} className="card mb-6">
      <h3 className="mb-4 text-gray-900 dark:text-gray-100">Filters</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-4">
        {children}
      </div>
      <div className="flex space-x-3">
        <button type="submit" className="btn btn-primary">
          Apply Filters
        </button>
        <button
          type="reset"
          className="btn btn-secondary"
          onClick={() => onApplyFilters({})}
        >
          Clear Filters
        </button>
      </div>
    </form>
  );
}
