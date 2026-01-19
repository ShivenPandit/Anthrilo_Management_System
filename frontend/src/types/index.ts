// Yarn Types
export interface Yarn {
  id: number;
  yarn_type: string;
  yarn_count: string;
  composition: string;
  percentage_breakdown?: Record<string, number>;
  supplier?: string;
  unit_price?: number;
  stock_quantity: number;
  unit: string;
  created_at: string;
  updated_at: string;
}

// Fabric Types
export interface Fabric {
  id: number;
  fabric_type: string;
  subtype: string;
  gsm: number;
  composition: string;
  width?: number;
  color?: string;
  stock_quantity: number;
  unit: string;
  cost_per_unit?: number;
  created_at: string;
  updated_at: string;
}

// Garment Types
export interface Garment {
  id: number;
  style_sku: string;
  name: string;
  category: string;
  sub_category?: string;
  sizes: string[];
  gross_weight_per_size?: Record<string, number>;
  mrp: number;
  description?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// Inventory Types
export interface Inventory {
  id: number;
  garment_id: number;
  size: string;
  good_stock: number;
  virtual_stock: number;
  warehouse_location?: string;
  last_updated: string;
  created_at: string;
}

// Panel Types
export interface Panel {
  id: number;
  panel_name: string;
  panel_type: string;
  contact_person?: string;
  email?: string;
  phone?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// Sale Types
export interface Sale {
  id: number;
  transaction_date: string;
  garment_id: number;
  panel_id: number;
  size: string;
  quantity: number;
  unit_price: number;
  discount_percentage: number;
  total_amount: number;
  is_return: boolean;
  invoice_number?: string;
  created_at: string;
}

// Production Types
export interface ProductionPlan {
  id: number;
  plan_name: string;
  garment_id: number;
  planned_quantity: number;
  target_date: string;
  status: 'PLANNED' | 'IN_PROGRESS' | 'COMPLETED';
  fabric_requirement?: number;
  yarn_requirement?: number;
  notes?: string;
  created_at: string;
  updated_at: string;
}

// Discount Types
export interface Discount {
  id: number;
  discount_name: string;
  discount_type: string;
  discount_value: number;
  applicable_to: string;
  panel_id?: number;
  garment_id?: number;
  category?: string;
  valid_from: string;
  valid_to?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// Paid Ad Types
export interface PaidAd {
  id: number;
  ad_date: string;
  panel_id: number;
  platform: string;
  campaign_name: string;
  daily_spend: number;
  impressions?: number;
  clicks?: number;
  conversions?: number;
  revenue_generated?: number;
  notes?: string;
  created_at: string;
}
