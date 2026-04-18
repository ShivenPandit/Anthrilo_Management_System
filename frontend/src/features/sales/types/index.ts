// Sales-related types
export type { Sale, Discount, PaginatedResponse } from '@/types';

export interface SalesActivityRow {
  item_sku_code: string;
  item_type_name: string;
  type?: string;
  tags?: string;
  selling_price?: number;
  size: string;
  item_type_size?: string;
  style_name?: string;
  mrp?: number;
  cost?: number;
  channel: string;
  total_sale_qty: number;
  cancel_qty: number;
  return_qty: number;
  net_sale: number;
  sale_amount?: number;
  cancel_amount?: number;
  return_amount?: number;
  net_sale_amount?: number;
  stock_good: number;
  stock_virtual: number;
}

export type ReportType = 'size-wise' | 'item-wise' | 'channel-detailed' | 'channel-summary';
