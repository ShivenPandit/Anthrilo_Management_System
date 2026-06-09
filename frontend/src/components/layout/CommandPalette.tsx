'use client';

import {
  useState, useEffect, useCallback, useRef, useMemo, memo,
} from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, X, ArrowRight, Clock, BarChart3, ShoppingCart,
  TrendingUp, Package, FileText, DollarSign, PieChart,
  Percent, Target, Gauge, Zap, Store, Undo2, Shirt,
  Boxes, LayoutDashboard, Receipt,
  type LucideIcon,
} from 'lucide-react';
import { NAVIGATION_ITEMS } from './Sidebar';

// Types
interface SearchItem {
  id: string;
  title: string;
  description: string;
  href: string;
  icon: LucideIcon;
  category: string;
  keywords?: string[];
}

// Search Catalogue
const BASE_SEARCH_ITEMS: SearchItem[] = [
  // Dashboard
  {
    id: 'dashboard',
    title: 'Dashboard Overview',
    description: 'Main dashboard overview',
    href: '/dashboard',
    icon: LayoutDashboard,
    category: 'Dashboard',
  },

  // Reports
  {
    id: 'all-reports',
    title: 'All Reports',
    description: 'Reports & Analytics hub',
    href: '/dashboard/reports/reports-index',
    icon: FileText,
    category: 'Reports',
    keywords: ['reports', 'analytics', 'hub'],
  },
  {
    id: 'daily-sales',
    title: 'Sales Report',
    description: 'Channel-wise daily revenue breakdown',
    href: '/dashboard/sales/reports/daily',
    icon: BarChart3,
    category: 'Reports',
    keywords: ['sales', 'daily', 'revenue', 'channel'],
  },
  {
    id: 'demo-report',
    title: 'Sales + Inventory + return combined report',
    description: 'Combined sales, returns and inventory report with channel and bundle SKU details',
    href: '/dashboard/sales/reports/combined-report',
    icon: FileText,
    category: 'Reports',
    keywords: ['demo', 'report', 'item type size', 'size wise', 'inventory'],
  },
  {
    id: 'return-report',
    title: 'Return Report',
    description: 'Returns & refunds summary',
    href: '/dashboard/sales/reports/returns',
    icon: Undo2,
    category: 'Reports',
    keywords: ['returns', 'refunds', 'rto', 'cir'],
  },
  {
    id: 'cancellation-report',
    title: 'Cancellation Report',
    description: 'Order cancellations summary by channel and SKU',
    href: '/dashboard/reports/sales/cancellations',
    icon: Undo2,
    category: 'Reports',
    keywords: ['cancellation', 'cancelled', 'canceled', 'orders'],
  },
  {
    id: 'sku-sales',
    title: 'SKU Sales',
    description: 'Size-wise bundle sales & search',
    href: '/dashboard/reports/sales/bundle-sku',
    icon: Package,
    category: 'Reports',
    keywords: ['sku', 'bundle', 'sales', 'size'],
  },
  {
    id: 'discounts-report',
    title: 'Discount Report',
    description: 'General discount & coupon analysis',
    href: '/dashboard/reports/sales/discount-general',
    icon: Percent,
    category: 'Reports',
    keywords: ['discount', 'coupon', 'promo'],
  },
  {
    id: 'channels',
    title: 'Channel Settlement',
    description: 'Commission & net settlement estimates',
    href: '/dashboard/reports/panels/settlement',
    icon: Store,
    category: 'Reports',
    keywords: ['channel', 'settlement', 'commission'],
  },
  {
    id: 'panel-perf',
    title: 'Panel Performance',
    description: 'Panel revenue share & sorting',
    href: '/dashboard/reports/panels',
    icon: PieChart,
    category: 'Reports',
    keywords: ['panel', 'performance', 'revenue'],
  },
  {
    id: 'inventory-health',
    title: 'Inventory Health',
    description: 'Slow & fast moving turnover rates',
    href: '/dashboard/garments/sku-velocity',
    icon: Gauge,
    category: 'Reports',
    keywords: ['inventory', 'health', 'velocity', 'turnover'],
  },

  // Sales
  {
    id: 'transactions',
    title: 'Sales Transactions',
    description: 'All sales transaction records',
    href: '/dashboard/sales/transactions',
    icon: Receipt,
    category: 'Sales',
    keywords: ['transactions', 'orders', 'records'],
  },
  {
    id: 'panels-sales',
    title: 'Sales Panels',
    description: 'Panel performance view',
    href: '/dashboard/sales/panels',
    icon: PieChart,
    category: 'Sales',
    keywords: ['panels', 'marketplace', 'channels'],
  },
  {
    id: 'cod-prepaid',
    title: 'COD vs Prepaid',
    description: 'Payment method split analysis',
    href: '/dashboard/sales/cod-prepaid',
    icon: ShoppingCart,
    category: 'Sales',
    keywords: ['cod', 'prepaid', 'payment', 'split'],
  },
  {
    id: 'top-sellers',
    title: 'Top Selling Products',
    description: 'Best performing SKUs by units sold',
    href: '/dashboard/sales/top-sellers',
    icon: TrendingUp,
    category: 'Sales',
    keywords: ['top', 'best', 'selling', 'sku', 'popular'],
  },

  // Garments
  {
    id: 'garment-master',
    title: 'Garment Master Data',
    description: 'Garment catalog & definitions',
    href: '/dashboard/garments/master',
    icon: Shirt,
    category: 'Garments',
    keywords: ['garment', 'catalogue', 'master', 'product'],
  },
  {
    id: 'production-orders',
    title: 'Production Orders',
    description: 'Active & planned production orders',
    href: '/dashboard/garments/production',
    icon: ShoppingCart,
    category: 'Garments',
    keywords: ['production', 'orders', 'planning'],
  },
  {
    id: 'best-skus',
    title: 'Best SKUs',
    description: 'Top monthly SKU performance',
    href: '/dashboard/garments/best-skus',
    icon: Zap,
    category: 'Garments',
    keywords: ['best', 'sku', 'monthly', 'top', 'performance'],
  },
  {
    id: 'sku-velocity',
    title: 'SKU Velocity',
    description: 'Fast & slow movers',
    href: '/dashboard/garments/sku-velocity',
    icon: Gauge,
    category: 'Garments',
    keywords: ['velocity', 'fast', 'slow', 'mover', 'sku'],
  },

  // Financial
  {
    id: 'financial',
    title: 'Financial Overview',
    description: 'P&L and overall financial metrics',
    href: '/dashboard/financial',
    icon: DollarSign,
    category: 'Financial',
    keywords: ['finance', 'pnl', 'profit', 'loss', 'revenue'],
  },
  {
    id: 'financial-discounts',
    title: 'Financial Discounts',
    description: 'Discount impact on revenue',
    href: '/dashboard/financial/discounts',
    icon: Percent,
    category: 'Financial',
    keywords: ['discount', 'financial', 'impact'],
  },
  {
    id: 'roi',
    title: 'ROI Analysis',
    description: 'Return on investment across channels',
    href: '/dashboard/financial/roi',
    icon: Target,
    category: 'Financial',
    keywords: ['roi', 'return', 'investment', 'channels'],
  },
];

function toKeywordTokens(value: string): string[] {
  return value
    .toLowerCase()
    .replace(/[&/\\]/g, ' ')
    .split(/\s+/)
    .filter(Boolean);
}

const NAVIGATION_SEARCH_ITEMS: SearchItem[] = NAVIGATION_ITEMS.flatMap((item) => {
  const parentKeywords = toKeywordTokens(item.name);

  if (item.href) {
    return [
      {
        id: `nav-${item.href.replace(/[^a-zA-Z0-9]+/g, '-').replace(/(^-|-$)/g, '').toLowerCase()}`,
        title: item.name,
        description: `${item.name} section`,
        href: item.href,
        icon: item.icon,
        category: item.name,
        keywords: parentKeywords,
      },
    ];
  }

  return (item.children || []).map((child) => ({
    id: `nav-${child.href.replace(/[^a-zA-Z0-9]+/g, '-').replace(/(^-|-$)/g, '').toLowerCase()}`,
    title: child.name,
    description: `${item.name} • ${child.name}`,
    href: child.href,
    icon: child.icon || item.icon,
    category: item.name,
    keywords: [...parentKeywords, ...toKeywordTokens(child.name)],
  }));
});

const SEARCH_ITEMS: SearchItem[] = (() => {
  const byHref = new Map<string, SearchItem>();

  [...BASE_SEARCH_ITEMS, ...NAVIGATION_SEARCH_ITEMS].forEach((item) => {
    const existing = byHref.get(item.href);

    if (!existing) {
      byHref.set(item.href, item);
      return;
    }

    byHref.set(item.href, {
      ...existing,
      keywords: Array.from(new Set([...(existing.keywords || []), ...(item.keywords || [])])),
    });
  });

  return Array.from(byHref.values());
})();

// Recent search persistence
const RECENT_KEY = 'cmd_recent';
const MAX_RECENT = 5;

function getRecentIds(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
  } catch {
    return [];
  }
}

function saveRecentId(id: string) {
  const prev = getRecentIds().filter((r) => r !== id);
  localStorage.setItem(RECENT_KEY, JSON.stringify([id, ...prev].slice(0, MAX_RECENT)));
}

// Props
interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

// Component
export const CommandPalette = memo(function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [cursor, setCursor] = useState(0);
  const [recentIds, setRecentIds] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Reset & focus on open
  useEffect(() => {
    if (open) {
      setQuery('');
      setCursor(0);
      setRecentIds(getRecentIds());
      const t = setTimeout(() => inputRef.current?.focus(), 60);
      return () => clearTimeout(t);
    }
  }, [open]);

  // Filtered results
  const results = useMemo<SearchItem[]>(() => {
    if (!query.trim()) return [];
    const q = query.toLowerCase();
    return SEARCH_ITEMS.filter(
      (item) =>
        item.title.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q) ||
        item.category.toLowerCase().includes(q) ||
        item.keywords?.some((k) => k.toLowerCase().includes(q)),
    );
  }, [query]);

  const recentItems = useMemo<SearchItem[]>(
    () =>
      recentIds
        .map((id) => SEARCH_ITEMS.find((i) => i.id === id))
        .filter(Boolean) as SearchItem[],
    [recentIds],
  );

  const prefetchRoute = useCallback(
    (href: string) => {
      try {
        router.prefetch(href);
      } catch {
        // Ignore prefetch failures; route push still works.
      }
    },
    [router],
  );

  useEffect(() => {
    if (!open) return;

    const targets = (recentItems.length ? recentItems : SEARCH_ITEMS).slice(0, 12);
    const timeoutIds = targets.map((item, index) =>
      window.setTimeout(() => prefetchRoute(item.href), index * 90),
    );

    return () => {
      timeoutIds.forEach((id) => window.clearTimeout(id));
    };
  }, [open, prefetchRoute, recentItems]);

  const displayItems = query.trim() ? results : recentItems;
  const isShowingRecent = !query.trim();

  // Group by category (or 'Recent' for recents)
  const grouped = useMemo<Record<string, SearchItem[]>>(() => {
    if (isShowingRecent) return { Recent: displayItems };
    return displayItems.reduce<Record<string, SearchItem[]>>((acc, item) => {
      if (!acc[item.category]) acc[item.category] = [];
      acc[item.category].push(item);
      return acc;
    }, {});
  }, [displayItems, isShowingRecent]);

  // Navigate to item
  const navigate = useCallback(
    (item: SearchItem) => {
      saveRecentId(item.id);
      setRecentIds(getRecentIds());
      prefetchRoute(item.href);
      router.push(item.href);
      onClose();
    },
    [onClose, prefetchRoute, router],
  );

  // Keyboard navigation
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!open) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setCursor((c) => Math.min(c + 1, displayItems.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setCursor((c) => Math.max(c - 1, 0));
      } else if (e.key === 'Enter') {
        if (displayItems[cursor]) navigate(displayItems[cursor]);
      } else if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, displayItems, cursor, navigate, onClose]);

  // Scroll cursor into view
  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>(`[data-idx="${cursor}"]`)
      ?.scrollIntoView({ block: 'nearest' });
  }, [cursor]);

  // Reset cursor on query change
  useEffect(() => setCursor(0), [query]);

  // Render flat index tracker (reset each render)
  let flatIdx = 0;

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            key="cp-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden
          />

          {/* Panel */}
          <motion.div
            key="cp-panel"
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            initial={{ opacity: 0, y: -20, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -12, scale: 0.97 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="fixed top-[11vh] left-1/2 -translate-x-1/2 z-50 w-full max-w-2xl px-4"
          >
            <div
              className="rounded-2xl border border-white/20 dark:border-slate-700/60
                         bg-white/95 dark:bg-slate-900/95 backdrop-blur-2xl
                         shadow-2xl shadow-black/25 overflow-hidden"
            >
              {/* Search input */}
              <div className="flex items-center gap-3 px-4 py-3.5 border-b border-slate-100 dark:border-slate-800">
                <Search className="w-5 h-5 flex-shrink-0 text-slate-400" />
                <input
                  ref={inputRef}
                  type="text"
                  placeholder="Search pages, reports, sections..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="flex-1 bg-transparent text-[15px] text-slate-900 dark:text-white
                             placeholder:text-slate-400 outline-none"
                  aria-label="Search"
                />
                {query && (
                  <button
                    onClick={() => setQuery('')}
                    aria-label="Clear search"
                    className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
                <kbd className="hidden sm:flex items-center px-1.5 py-0.5 rounded text-[11px] font-medium
                               bg-slate-100 dark:bg-slate-800 text-slate-400
                               ring-1 ring-slate-200 dark:ring-slate-700">
                  ESC
                </kbd>
              </div>

              {/* Results */}
              <div ref={listRef} className="max-h-[420px] overflow-y-auto overscroll-contain py-2">
                {displayItems.length === 0 ? (
                  /* Empty state */
                  <div className="py-14 text-center select-none">
                    {query ? (
                      <>
                        <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center mx-auto mb-3">
                          <Search className="w-5 h-5 text-slate-400" />
                        </div>
                        <p className="text-sm font-medium text-slate-600 dark:text-slate-400">
                          No results for &ldquo;{query}&rdquo;
                        </p>
                        <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                          Try a different search term
                        </p>
                      </>
                    ) : (
                      <>
                        <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center mx-auto mb-3">
                          <Clock className="w-5 h-5 text-slate-400" />
                        </div>
                        <p className="text-sm text-slate-400 dark:text-slate-500">
                          No recent searches yet
                        </p>
                      </>
                    )}
                  </div>
                ) : (
                  Object.entries(grouped).map(([category, items]) => (
                    <div key={category}>
                      <p className="px-4 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500 select-none">
                        {category}
                      </p>
                      {items.map((item) => {
                        const idx = flatIdx++;
                        const isActive = cursor === idx;
                        const Icon = item.icon;
                        return (
                          <button
                            key={item.id}
                            data-idx={idx}
                            onClick={() => navigate(item)}
                            onMouseEnter={() => {
                              setCursor(idx);
                              prefetchRoute(item.href);
                            }}
                            onFocus={() => prefetchRoute(item.href)}
                            className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${isActive
                              ? 'bg-primary-50 dark:bg-primary-950/50'
                              : 'hover:bg-slate-50 dark:hover:bg-slate-800/40'
                              }`}
                          >
                            {/* Icon */}
                            <div
                              className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 transition-colors ${isActive
                                ? 'bg-primary-100 dark:bg-primary-900/60'
                                : 'bg-slate-100 dark:bg-slate-800'
                                }`}
                            >
                              <Icon
                                className={`w-[15px] h-[15px] ${isActive
                                  ? 'text-primary-600 dark:text-primary-400'
                                  : 'text-slate-500 dark:text-slate-400'
                                  }`}
                              />
                            </div>

                            {/* Text */}
                            <div className="flex-1 min-w-0">
                              <p
                                className={`text-[13.5px] font-medium truncate ${isActive
                                  ? 'text-primary-700 dark:text-primary-300'
                                  : 'text-slate-800 dark:text-slate-200'
                                  }`}
                              >
                                {item.title}
                              </p>
                              <p className="text-xs text-slate-400 dark:text-slate-500 truncate">
                                {item.description}
                              </p>
                            </div>

                            {/* Arrow on active */}
                            {isActive && (
                              <ArrowRight className="w-3.5 h-3.5 text-primary-400 flex-shrink-0" />
                            )}
                          </button>
                        );
                      })}
                    </div>
                  ))
                )}
              </div>

              {/* Footer hints */}
              <div className="flex items-center justify-between px-4 py-2.5 border-t border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/20">
                <div className="flex items-center gap-3 text-[11px] text-slate-400 select-none">
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 rounded bg-white dark:bg-slate-700 ring-1 ring-slate-200 dark:ring-slate-600 text-slate-500">↑↓</kbd>
                    navigate
                  </span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 rounded bg-white dark:bg-slate-700 ring-1 ring-slate-200 dark:ring-slate-600 text-slate-500">↵</kbd>
                    open
                  </span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 rounded bg-white dark:bg-slate-700 ring-1 ring-slate-200 dark:ring-slate-600 text-slate-500">esc</kbd>
                    close
                  </span>
                </div>
                <span className="text-[11px] text-slate-400">
                  {displayItems.length} result{displayItems.length !== 1 ? 's' : ''}
                </span>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
});

export default CommandPalette;
