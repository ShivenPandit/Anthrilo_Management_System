'use client';

import { useState, useMemo, useCallback, memo } from 'react';
import Link from 'next/link';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, ArrowRight, Star, Clock, TrendingUp,
  BarChart3, ShoppingCart, Undo2, DollarSign, Package, FileText,
  PieChart, Receipt, Percent, Store, Zap, Target, Truck, Megaphone, AlertTriangle,
  type LucideIcon,
} from 'lucide-react';

/*  */
/*  Types                                                     */
/*  */

type Category = 'Sales' | 'Returns' | 'Financial' | 'Inventory';
type Frequency = 'Daily' | 'Weekly' | 'Monthly' | 'Real-time' | 'AI Forecast';

interface ReportDef {
  id: string;
  title: string;
  description: string;
  href: string;
  icon: LucideIcon;
  category: Category;
  frequency: Frequency;
  badge?: string;
  popular?: boolean;
}

/*  */
/*  Report Registry  (clean titles — no "Daily" prefix)       */
/*  */

const REPORTS: ReportDef[] = [
  // Sales
  {
    id: 'daily-sales',
    title: 'Sales Report',
    description: 'Channel-wise revenue breakdown & CSV export',
    href: '/dashboard/sales/reports/daily',
    icon: BarChart3,
    category: 'Sales',
    frequency: 'Daily',
    popular: true,
  },
  {
    id: 'sales-analytics',
    title: 'Sales Analytics',
    description: 'Sales performance & channel insights',
    href: '/dashboard/reports/sales',
    icon: TrendingUp,
    category: 'Sales',
    frequency: 'Daily',
  },
  {
    id: 'bundle-sku',
    title: 'SKU Sales',
    description: 'Size-wise bundle sales & search',
    href: '/dashboard/reports/sales/bundle-sku',
    icon: Package,
    category: 'Sales',
    frequency: 'Daily',
    badge: 'Popular',
    popular: true,
  },
  {
    id: 'bundle-catalog',
    title: 'Bundle SKU Catalog',
    description: 'Bundle/combo SKU catalog with component details',
    href: '/dashboard/reports/sales/bundle-sku/bundles',
    icon: Package,
    category: 'Inventory',
    frequency: 'Daily',
    badge: 'New',
  },
  {
    id: 'bundle-sales-analysis',
    title: 'Bundle Sales Analysis',
    description: 'Revenue, trends & performance by bundle — reverse-mapped from component sales',
    href: '/dashboard/reports/sales/bundle-sku/analysis',
    icon: TrendingUp,
    category: 'Sales',
    frequency: 'Daily',
    badge: 'New',
    popular: true,
  },
  {
    id: 'panel-performance',
    title: 'Panel Performance',
    description: 'Panel revenue share & sorting',
    href: '/dashboard/reports/panels',
    icon: PieChart,
    category: 'Sales',
    frequency: 'Daily',
  },
  {
    id: 'panel-settlement',
    title: 'Channel Settlement',
    description: 'Commission & net settlement estimates',
    href: '/dashboard/reports/panels/settlement',
    icon: Store,
    category: 'Sales',
    frequency: 'Daily',
    badge: 'New',
  },
  {
    id: 'cod-prepaid',
    title: 'COD vs Prepaid',
    description: 'Payment method split analysis',
    href: '/dashboard/sales/cod-prepaid',
    icon: ShoppingCart,
    category: 'Sales',
    frequency: 'Monthly',
  },
  {
    id: 'top-sellers',
    title: 'Top Selling Products',
    description: 'Best performing SKUs by units sold',
    href: '/dashboard/sales/top-sellers',
    icon: TrendingUp,
    category: 'Sales',
    frequency: 'Daily',
    badge: 'Popular',
    popular: true,
  },
  {
    id: 'sales-activity',
    title: 'Sales Activity',
    description: 'SKU movement, stock activity & channel-wise breakdowns with Excel export',
    href: '/dashboard/sales/activity',
    icon: FileText,
    category: 'Sales',
    frequency: 'Daily',
    badge: 'New',
    popular: true,
  },
  {
    id: 'demo-report',
    title: 'Demo Report',
    description: 'Business-ready Item Type Size report with sale/return/cancel/net and current inventory',
    href: '/dashboard/sales/reports/demo',
    icon: FileText,
    category: 'Sales',
    frequency: 'Daily',
    badge: 'New',
    popular: true,
  },

  // Returns
  {
    id: 'daily-returns',
    title: 'Return Report',
    description: 'RTO & CIR breakdown by channel & SKU',
    href: '/dashboard/sales/reports/returns',
    icon: Undo2,
    category: 'Returns',
    frequency: 'Daily',
    popular: true,
  },
  {
    id: 'cancellation-report',
    title: 'Cancellation Report',
    description: 'Cancelled orders and items by channel, SKU and value',
    href: '/dashboard/reports/sales/cancellations',
    icon: AlertTriangle,
    category: 'Returns',
    frequency: 'Daily',
    badge: 'New',
    popular: true,
  },

  // Financial
  {
    id: 'discount-general',
    title: 'Discount Report',
    description: 'Product-wise discount buckets',
    href: '/dashboard/reports/sales/discount-general',
    icon: Percent,
    category: 'Financial',
    frequency: 'Daily',
    popular: true,
  },
  {
    id: 'discount-channel',
    title: 'Discount by Channel',
    description: 'Channel-level discount comparison',
    href: '/dashboard/reports/sales/discount-by-panel',
    icon: Receipt,
    category: 'Financial',
    frequency: 'Daily',
  },
  {
    id: 'financial-overview',
    title: 'Financial Overview',
    description: 'Margins, profitability & expenses',
    href: '/dashboard/financial',
    icon: DollarSign,
    category: 'Financial',
    frequency: 'Daily',
  },
  {
    id: 'roi-analysis',
    title: 'ROI Analysis',
    description: 'ROI across channels & campaigns',
    href: '/dashboard/financial/roi',
    icon: Target,
    category: 'Financial',
    frequency: 'Daily',
  },
  {
    id: 'ads-performance',
    title: 'Ads Performance',
    description: 'Ad spend, ROAS & channel-wise advertising metrics',
    href: '/dashboard/financial/ads',
    icon: Megaphone,
    category: 'Financial',
    frequency: 'Daily',
    badge: 'New',
    popular: true,
  },

  // Inventory
  {

    id: 'yarn-forecasting',
    title: 'Yarn Forecasting',
    description: 'AI demand forecasting for yarn',
    href: '/dashboard/reports/raw-materials/yarn-forecasting',
    icon: Zap,
    category: 'Inventory',
    frequency: 'AI Forecast',
    badge: 'AI',
  },
  {
    id: 'fabric-reports',
    title: 'Fabric Stock',
    description: 'Stock by type, period & cost',
    href: '/dashboard/reports/fabric',
    icon: FileText,
    category: 'Inventory',
    frequency: 'Daily',
  },
  {
    id: 'inventory-analysis',
    title: 'Inventory Health',
    description: 'Slow & fast moving turnover rates',
    href: '/dashboard/garments/sku-velocity',
    icon: Truck,
    category: 'Inventory',
    frequency: 'Daily',
  },
];

/*  */
/*  Category Config                                           */
/*  */

const CATEGORY_META: Record<Category, {
  color: string; bg: string; ring: string; dot: string; border: string;
  gradient: string; icon: LucideIcon; label: string;
}> = {
  Sales: {
    color: 'text-blue-600 dark:text-blue-400',
    bg: 'bg-blue-50 dark:bg-blue-950/30',
    ring: 'ring-blue-200 dark:ring-blue-800',
    dot: 'bg-blue-500',
    border: 'border-l-blue-500',
    gradient: 'from-blue-500 to-indigo-600',
    icon: BarChart3,
    label: 'Sales',
  },
  Returns: {
    color: 'text-rose-600 dark:text-rose-400',
    bg: 'bg-rose-50 dark:bg-rose-950/30',
    ring: 'ring-rose-200 dark:ring-rose-800',
    dot: 'bg-rose-500',
    border: 'border-l-rose-500',
    gradient: 'from-rose-500 to-pink-600',
    icon: Undo2,
    label: 'Returns',
  },
  Financial: {
    color: 'text-violet-600 dark:text-violet-400',
    bg: 'bg-violet-50 dark:bg-violet-950/30',
    ring: 'ring-violet-200 dark:ring-violet-800',
    dot: 'bg-violet-500',
    border: 'border-l-violet-500',
    gradient: 'from-violet-500 to-purple-600',
    icon: DollarSign,
    label: 'Financial',
  },
  Inventory: {
    color: 'text-emerald-600 dark:text-emerald-400',
    bg: 'bg-emerald-50 dark:bg-emerald-950/30',
    ring: 'ring-emerald-200 dark:ring-emerald-800',
    dot: 'bg-emerald-500',
    border: 'border-l-emerald-500',
    gradient: 'from-emerald-500 to-teal-600',
    icon: Package,
    label: 'Inventory',
  },
};

const ALL_CATEGORIES: Category[] = ['Sales', 'Returns', 'Financial', 'Inventory'];

/*  */
/*  LocalStorage helpers                                      */
/*  */

const LS_FAV = 'anthrilo_fav_reports';
const LS_REC = 'anthrilo_recent_reports';

function readLS<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback;
  try { return JSON.parse(localStorage.getItem(key) || '') as T; }
  catch { return fallback; }
}
function writeLS<T>(key: string, val: T) {
  if (typeof window === 'undefined') return;
  localStorage.setItem(key, JSON.stringify(val));
}

/*  */
/*  Sub-components                                            */
/*  */

/* Frequency Badge */
const FREQ_STYLES: Record<Frequency, string> = {
  'Daily': 'bg-sky-50 text-sky-600 dark:bg-sky-950/40 dark:text-sky-400',
  'Weekly': 'bg-amber-50 text-amber-600 dark:bg-amber-950/40 dark:text-amber-400',
  'Monthly': 'bg-purple-50 text-purple-600 dark:bg-purple-950/40 dark:text-purple-400',
  'Real-time': 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-400',
  'AI Forecast': 'bg-gradient-to-r from-violet-500 to-indigo-500 text-white',
};

const FrequencyBadge = memo(({ frequency }: { frequency: Frequency }) => (
  <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider leading-none ${FREQ_STYLES[frequency]}`}>
    {frequency}
  </span>
));
FrequencyBadge.displayName = 'FrequencyBadge';

/* Extra Badge (New / Popular / AI) */
const ExtraBadge = memo(({ text }: { text: string }) => {
  const cls =
    text === 'AI'
      ? 'bg-gradient-to-r from-violet-500 to-indigo-500 text-white'
      : text === 'New'
        ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400 ring-1 ring-emerald-200 dark:ring-emerald-800'
        : 'bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400 ring-1 ring-amber-200 dark:ring-amber-800';
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider leading-none ${cls}`}>
      {text}
    </span>
  );
});
ExtraBadge.displayName = 'ExtraBadge';

/* Category Section Header */
const CategoryHeader = memo(({ category }: { category: Category }) => {
  const m = CATEGORY_META[category];
  const Icon = m.icon;
  const count = REPORTS.filter(r => r.category === category).length;
  return (
    <div className="flex items-center gap-3 mb-4 sm:mb-5">
      <div className={`h-9 w-9 rounded-lg bg-gradient-to-br ${m.gradient} flex items-center justify-center flex-shrink-0`}>
        <Icon className="w-[18px] h-[18px] text-white" strokeWidth={2} />
      </div>
      <div className="min-w-0">
        <h2 className="text-base sm:text-lg 2xl:text-xl font-semibold text-slate-900 dark:text-slate-100 leading-tight">{category}</h2>
        <p className="text-xs text-slate-400 dark:text-slate-500">{count} report{count !== 1 ? 's' : ''}</p>
      </div>
      <div className="flex-1 h-px bg-slate-200/70 dark:bg-slate-700/50 ml-2" />
    </div>
  );
});
CategoryHeader.displayName = 'CategoryHeader';

/* Report Card */
const ReportCard = memo(({
  report, isFav, onToggleFav, onOpen,
}: {
  report: ReportDef; isFav: boolean;
  onToggleFav: (id: string) => void;
  onOpen: (id: string) => void;
}) => {
  const m = CATEGORY_META[report.category];
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ duration: 0.2, ease: [.4, 0, .2, 1] }}
      className={`group relative rounded-2xl border-l-[3px] ${m.border}
                  bg-white dark:bg-slate-800/60
                  border border-slate-200/60 dark:border-slate-700/50
                  shadow-sm hover:shadow-md dark:hover:shadow-slate-900/40
                  transition-all duration-200 hover:-translate-y-0.5 flex flex-col`}
    >
      <div className="p-4 sm:p-6 2xl:p-7 flex flex-col flex-1">
        {/* Row 1: icon + title + badges + fav */}
        <div className="flex items-start gap-3 sm:gap-4 mb-3">
          <div className={`h-11 w-11 rounded-xl ${m.bg} flex items-center justify-center flex-shrink-0`}>
            <report.icon className={`w-5 h-5 ${m.color}`} strokeWidth={1.8} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1.5">
              <h3 className="text-sm sm:text-base 2xl:text-lg font-semibold text-slate-900 dark:text-slate-100 leading-snug group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                {report.title}
              </h3>
              <FrequencyBadge frequency={report.frequency} />
              {report.badge && <ExtraBadge text={report.badge} />}
            </div>
            <p className="text-[13px] text-slate-400 dark:text-slate-500 leading-relaxed">
              {report.description}
            </p>
          </div>
          <button
            onClick={(e) => { e.preventDefault(); onToggleFav(report.id); }}
            className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700/60 transition-colors flex-shrink-0 -mt-0.5"
            aria-label={isFav ? 'Remove from favorites' : 'Add to favorites'}
          >
            <Star
              className={`w-4 h-4 transition-colors ${isFav
                ? 'fill-amber-400 text-amber-400'
                : 'text-slate-300 dark:text-slate-600 group-hover:text-slate-400 dark:group-hover:text-slate-500'
                }`}
              strokeWidth={1.8}
            />
          </button>
        </div>

        {/* Row 2: open button */}
        <div className="flex items-center justify-end mt-auto pt-2">
          <Link
            href={report.href}
            onClick={() => onOpen(report.id)}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-[13px] font-medium
                       bg-slate-100 dark:bg-slate-700/50 text-slate-600 dark:text-slate-300
                       hover:bg-slate-200 dark:hover:bg-slate-700
                       transition-all duration-150 group/btn"
          >
            Open Report
            <ArrowRight className="w-3.5 h-3.5 group-hover/btn:translate-x-0.5 transition-transform" strokeWidth={2} />
          </Link>
        </div>
      </div>
    </motion.div>
  );
});
ReportCard.displayName = 'ReportCard';

/* Mini Card (sidebar) */
const MiniCard = memo(({
  report, icon: Icon, onOpen,
}: {
  report: ReportDef; icon?: LucideIcon; onOpen: (id: string) => void;
}) => {
  const m = CATEGORY_META[report.category];
  return (
    <Link
      href={report.href}
      onClick={() => onOpen(report.id)}
      className="group flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-700/40 transition-colors"
    >
      <div className={`h-8 w-8 rounded-lg ${m.bg} flex items-center justify-center flex-shrink-0`}>
        {Icon
          ? <Icon className={`w-4 h-4 ${m.color}`} strokeWidth={1.8} />
          : <report.icon className={`w-4 h-4 ${m.color}`} strokeWidth={1.8} />}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-medium text-slate-700 dark:text-slate-200 truncate group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
          {report.title}
        </p>
        <p className="text-[11px] text-slate-400 dark:text-slate-500 truncate">{report.category}</p>
      </div>
      <ArrowRight className="w-3.5 h-3.5 text-slate-300 dark:text-slate-600 group-hover:text-blue-500 group-hover:translate-x-0.5 transition-all flex-shrink-0" strokeWidth={2} />
    </Link>
  );
});
MiniCard.displayName = 'MiniCard';

/* Empty State */
const EmptyState = memo(({ query }: { query: string }) => (
  <motion.div
    initial={{ opacity: 0, y: 12 }}
    animate={{ opacity: 1, y: 0 }}
    className="flex flex-col items-center justify-center py-24"
  >
    <div className="h-14 w-14 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center mb-4">
      <Search className="w-6 h-6 text-slate-300 dark:text-slate-600" strokeWidth={1.5} />
    </div>
    <p className="text-base font-semibold text-slate-700 dark:text-slate-300 mb-1">No reports found</p>
    <p className="text-sm text-slate-400 dark:text-slate-500">
      {query ? `No results for "${query}".` : 'Adjust your filters to see reports.'}
    </p>
  </motion.div>
));
EmptyState.displayName = 'EmptyState';

/* Reports Section (one category group) */
const ReportsSection = memo(({
  category, reports, favorites, onToggleFav, onOpen,
}: {
  category: Category;
  reports: ReportDef[];
  favorites: string[];
  onToggleFav: (id: string) => void;
  onOpen: (id: string) => void;
}) => {
  if (reports.length === 0) return null;
  return (
    <section>
      <CategoryHeader category={category} />
      <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-4">
        {reports.map(r => (
          <ReportCard
            key={r.id}
            report={r}
            isFav={favorites.includes(r.id)}
            onToggleFav={onToggleFav}
            onOpen={onOpen}
          />
        ))}
      </div>
    </section>
  );
});
ReportsSection.displayName = 'ReportsSection';

/* Sidebar helpers */
function SidebarPanel({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl bg-white dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/50 shadow-sm overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-700/40 flex items-center gap-2">
        {icon}
        <h3 className="text-[13px] font-semibold text-slate-800 dark:text-slate-200">{title}</h3>
      </div>
      <div className="p-1.5">{children}</div>
    </div>
  );
}

function SidebarEmpty({ children }: { children: React.ReactNode }) {
  return <p className="px-3 py-4 text-center text-xs text-slate-400 dark:text-slate-500">{children}</p>;
}

/*  */
/*  Main Reports Hub                                          */
/*  */

export default function ReportsHub() {
  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState<Category | 'All'>('All');
  const [favorites, setFavorites] = useState<string[]>(() => readLS<string[]>(LS_FAV, []));
  const [recents, setRecents] = useState<string[]>(() => readLS<string[]>(LS_REC, []));

  const toggleFav = useCallback((id: string) => {
    setFavorites(prev => {
      const next = prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id];
      writeLS(LS_FAV, next);
      return next;
    });
  }, []);

  const recordOpen = useCallback((id: string) => {
    setRecents(prev => {
      const next = [id, ...prev.filter(x => x !== id)].slice(0, 6);
      writeLS(LS_REC, next);
      return next;
    });
  }, []);

  /* Derived */
  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    return REPORTS.filter(r => {
      if (activeCategory !== 'All' && r.category !== activeCategory) return false;
      if (q && !r.title.toLowerCase().includes(q) && !r.description.toLowerCase().includes(q) && !r.category.toLowerCase().includes(q) && !r.frequency.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [search, activeCategory]);

  const grouped = useMemo(() => {
    const map: Partial<Record<Category, ReportDef[]>> = {};
    for (const r of filtered) {
      (map[r.category] ??= []).push(r);
    }
    return map;
  }, [filtered]);

  const visibleCategories = useMemo(
    () => ALL_CATEGORIES.filter(c => (grouped[c]?.length ?? 0) > 0),
    [grouped],
  );

  const popularReports = useMemo(() => REPORTS.filter(r => r.popular), []);
  const favReports = useMemo(() => favorites.map(id => REPORTS.find(r => r.id === id)).filter(Boolean) as ReportDef[], [favorites]);
  const recentReports = useMemo(() => recents.map(id => REPORTS.find(r => r.id === id)).filter(Boolean) as ReportDef[], [recents]);

  const catCounts = useMemo(() => {
    const m: Record<string, number> = {};
    ALL_CATEGORIES.forEach(c => { m[c] = REPORTS.filter(r => r.category === c).length; });
    return m;
  }, []);

  return (
    <div className="min-h-0 page-section-gap">
      {/* Header */}
      <div>
        <h1 className="text-xl sm:text-2xl lg:text-3xl 2xl:text-4xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">
          Reports & Analytics
        </h1>
        <p className="mt-1.5 text-sm sm:text-base text-slate-400 dark:text-slate-500 max-w-xl">
          {REPORTS.length} reports across {ALL_CATEGORIES.length} categories. Find, favourite, and open any report.
        </p>
      </div>

      {/* Category Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4">
        {ALL_CATEGORIES.map(cat => {
          const m = CATEGORY_META[cat];
          const Icon = m.icon;
          const isActive = activeCategory === cat;
          return (
            <button
              key={cat}
              onClick={() => setActiveCategory(isActive ? 'All' : cat)}
              className={`relative rounded-2xl p-4 flex items-center gap-3.5 transition-all duration-200 border text-left
                ${isActive
                  ? `${m.bg} border-transparent ring-2 ${m.ring}`
                  : 'bg-white dark:bg-slate-800/60 border-slate-200/60 dark:border-slate-700/50 hover:border-slate-300 dark:hover:border-slate-600 shadow-sm hover:shadow'
                }`}
            >
              <div className={`h-10 w-10 rounded-xl bg-gradient-to-br ${m.gradient} flex items-center justify-center flex-shrink-0`}>
                <Icon className="w-5 h-5 text-white" strokeWidth={1.8} />
              </div>
              <div className="min-w-0">
                <p className={`text-sm font-semibold ${isActive ? m.color : 'text-slate-800 dark:text-slate-200'}`}>
                  {cat}
                </p>
                <p className="text-xs text-slate-400 dark:text-slate-500">{catCounts[cat]} reports</p>
              </div>
              {isActive && (
                <motion.div
                  layoutId="cat-dot"
                  className={`ml-auto h-2 w-2 rounded-full ${m.dot}`}
                  transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                />
              )}
            </button>
          );
        })}
      </div>

      {/* Search Bar */}
      <div>
        <div className="relative w-full max-w-xl">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" strokeWidth={2} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search reports…"
            className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200/80 dark:border-slate-700/50
                       bg-white dark:bg-slate-800/60 text-sm text-slate-900 dark:text-slate-100
                       placeholder:text-slate-400 dark:placeholder:text-slate-500
                       focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-300 dark:focus:border-blue-700
                       transition-all"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 text-xs font-medium"
            >
              Clear
            </button>
          )}
        </div>
        {(activeCategory !== 'All' || search) && (
          <div className="flex items-center gap-2 mt-3">
            <p className="text-xs text-slate-400 dark:text-slate-500">
              <span className="font-medium text-slate-600 dark:text-slate-300">{filtered.length}</span> report{filtered.length !== 1 ? 's' : ''}
              {activeCategory !== 'All' && <> in <span className={`font-medium ${CATEGORY_META[activeCategory].color}`}>{activeCategory}</span></>}
              {search && <> matching &ldquo;{search}&rdquo;</>}
            </p>
            <button
              onClick={() => { setActiveCategory('All'); setSearch(''); }}
              className="text-[11px] text-blue-600 dark:text-blue-400 hover:underline font-medium"
            >
              Reset filters
            </button>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex flex-col xl:flex-row gap-6 xl:gap-10">
        {/* Main: grouped category sections */}
        <div className="flex-1 min-w-0 space-y-7 sm:space-y-10">
          <AnimatePresence mode="popLayout">
            {visibleCategories.length > 0 ? (
              visibleCategories.map(cat => (
                <ReportsSection
                  key={cat}
                  category={cat}
                  reports={grouped[cat] ?? []}
                  favorites={favorites}
                  onToggleFav={toggleFav}
                  onOpen={recordOpen}
                />
              ))
            ) : (
              <EmptyState query={search} />
            )}
          </AnimatePresence>
        </div>

        {/* Sidebar */}
        <aside className="xl:w-72 2xl:w-80 flex-shrink-0 space-y-5">
          <SidebarPanel
            icon={<Star className="w-4 h-4 text-amber-400 fill-amber-400" strokeWidth={1.8} />}
            title="Favorites"
          >
            {favReports.length > 0
              ? favReports.map(r => <MiniCard key={r.id} report={r} icon={Star} onOpen={recordOpen} />)
              : <SidebarEmpty>Star any report to pin it here</SidebarEmpty>
            }
          </SidebarPanel>

          <SidebarPanel
            icon={<Clock className="w-4 h-4 text-slate-400 dark:text-slate-500" strokeWidth={1.8} />}
            title="Recently Opened"
          >
            {recentReports.length > 0
              ? recentReports.map(r => <MiniCard key={r.id} report={r} icon={Clock} onOpen={recordOpen} />)
              : <SidebarEmpty>Reports you open will show here</SidebarEmpty>
            }
          </SidebarPanel>

          <SidebarPanel
            icon={<TrendingUp className="w-4 h-4 text-blue-500" strokeWidth={1.8} />}
            title="Most Used"
          >
            {popularReports.map(r => <MiniCard key={r.id} report={r} onOpen={recordOpen} />)}
          </SidebarPanel>
        </aside>
      </div>
    </div>
  );
}
