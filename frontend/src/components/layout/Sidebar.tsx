'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard,
  BarChart3,
  Package,
  ShoppingCart,
  TrendingUp,
  ChevronLeft,
  ChevronDown,
  ChevronRight,
  FileText,
  Shirt,
  Boxes,
  Zap,
  Gauge,
  Receipt,
  Store,
  PieChart,
  DollarSign,
  Percent,
  Target,
  Layers,
  Megaphone,
  Undo2,
  Truck,
  ClipboardList,
  Building2,
  PackageCheck,
  Scissors,
  CheckCircle,
  QrCode,
  Factory,
  BookOpen,
  X,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

interface NavChild {
  name: string;
  href: string;
  icon?: LucideIcon;
}

interface NavItem {
  name: string;
  icon: LucideIcon;
  href?: string;
  children?: NavChild[];
}

export const NAVIGATION_ITEMS: NavItem[] = [
  {
    name: 'Overview',
    href: '/dashboard',
    icon: LayoutDashboard,
  },
  {
    name: 'Reports',
    icon: BarChart3,
    children: [
      { name: 'All Reports', href: '/dashboard/reports/reports-index', icon: FileText },
      { name: 'Sales Report', href: '/dashboard/sales/reports/daily', icon: BarChart3 },
      { name: 'Sales + Inventory + return combined report', href: '/dashboard/sales/reports/demo', icon: FileText },
      { name: 'Return Report', href: '/dashboard/sales/reports/returns', icon: BarChart3 },
      { name: 'Cancellation Report', href: '/dashboard/reports/sales/cancellations', icon: Undo2 },
      { name: 'SKU Sales', href: '/dashboard/reports/sales/bundle-sku', icon: BarChart3 },
      { name: 'Discounts', href: '/dashboard/reports/sales/discount-general', icon: Percent },
      { name: 'Channels', href: '/dashboard/reports/panels/settlement', icon: Store },
    ],
  },
  {
    name: 'Garments',
    icon: Shirt,
    children: [
      { name: 'Master Data', href: '/dashboard/garments/master', icon: Package },
      { name: 'Planning Report', href: '/dashboard/garments/planning-report', icon: FileText },
      { name: 'Orders', href: '/dashboard/garments/production', icon: ShoppingCart },
      { name: 'Best SKUs', href: '/dashboard/garments/best-skus', icon: Zap },
      { name: 'SKU Velocity', href: '/dashboard/garments/sku-velocity', icon: Gauge },
      { name: 'Bundle SKUs', href: '/dashboard/garments/bundle-skus', icon: Layers },
      { name: 'Bundle Sales', href: '/dashboard/garments/bundle-sales', icon: TrendingUp },
      { name: 'Fabric', href: '/dashboard/garments/fabric', icon: Boxes },
    ],
  },
  {
    name: 'Sales',
    icon: DollarSign,
    children: [
      { name: 'Transactions', href: '/dashboard/sales/transactions', icon: Receipt },
      { name: 'Panels', href: '/dashboard/sales/panels', icon: PieChart },
      { name: 'Sales Activity', href: '/dashboard/sales/activity', icon: BarChart3 },
      { name: 'Shopify Master Data', href: '/dashboard/sales/shopify-master-data', icon: BookOpen },
      { name: 'COD vs Prepaid', href: '/dashboard/sales/cod-prepaid', icon: ShoppingCart },
      { name: 'Top Sellers', href: '/dashboard/sales/top-sellers', icon: TrendingUp },
    ],
  },
  {
    name: 'Financial',
    icon: TrendingUp,
    children: [
      { name: 'Overview', href: '/dashboard/financial', icon: BarChart3 },
      { name: 'Discounts', href: '/dashboard/financial/discounts', icon: Percent },
      { name: 'Ads', href: '/dashboard/financial/ads', icon: Megaphone },
      { name: 'ROI Analysis', href: '/dashboard/financial/roi', icon: Target },
    ],
  },
  {
    name: 'Procurement',
    icon: Truck,
    children: [
      { name: 'Product Master', href: '/dashboard/procurement/product-master', icon: BookOpen },
      { name: 'Fabric & Yarn Master', href: '/dashboard/procurement/fabric-yarn-master', icon: Layers },
      { name: 'Suppliers', href: '/dashboard/procurement/suppliers', icon: Building2 },
      { name: 'Purchase Orders', href: '/dashboard/procurement/purchase-orders', icon: ClipboardList },
      { name: 'Gate Entry', href: '/dashboard/procurement/gate-entry', icon: PackageCheck },
      { name: 'MRN', href: '/dashboard/procurement/mrn', icon: FileText },
    ],
  },
  {
    name: 'Manufacturing',
    icon: Factory,
    children: [
      { name: 'Yarn Store', href: '/dashboard/manufacturing/yarn-store', icon: Package },
      { name: 'Knit Orders', href: '/dashboard/manufacturing/knit-orders', icon: Layers },
      { name: 'Processing', href: '/dashboard/manufacturing/processing', icon: Boxes },
      { name: 'Cutting', href: '/dashboard/manufacturing/cutting', icon: Scissors },
      { name: 'Stitching', href: '/dashboard/manufacturing/stitching', icon: Shirt },
      { name: 'Finishing', href: '/dashboard/manufacturing/finishing', icon: CheckCircle },
      { name: 'Barcoding', href: '/dashboard/manufacturing/barcoding', icon: QrCode },
    ],
  },
];

const MODULE_BY_ITEM_NAME: Record<string, string> = {
  Overview: 'dashboard',
  Reports: 'reports',
  Garments: 'garments',
  Sales: 'sales',
  Financial: 'financial',
  Procurement: 'procurement',
  Manufacturing: 'manufacturing',
};

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

export function Sidebar({
  collapsed,
  onToggle,
  mobileOpen = false,
  onMobileClose,
}: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { user } = useAuth();

  useEffect(() => {
    if (!mobileOpen) return;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = '';
    };
  }, [mobileOpen]);

  const allowedModules = useMemo(() => {
    if (!user) return new Set<string>();
    if (user.role === 'developer') return new Set(Object.values(MODULE_BY_ITEM_NAME));

    const explicitModules = new Set((user.module_access || []).map((m) => m.toLowerCase()));
    if (explicitModules.size > 0) return explicitModules;

    const permissionModules = new Set<string>();
    (user.permissions || []).forEach((code) => {
      const [module, action] = code.split(':');
      if (module && action === 'view') permissionModules.add(module.toLowerCase());
    });
    return permissionModules;
  }, [user]);

  const visibleNavigation = useMemo(() => {
    if (!user) return [] as NavItem[];
    if (user.role === 'developer') return NAVIGATION_ITEMS;

    return NAVIGATION_ITEMS.filter((item) => {
      const moduleKey = MODULE_BY_ITEM_NAME[item.name];
      if (!moduleKey) return true;
      return allowedModules.has(moduleKey);
    });
  }, [allowedModules, user]);

  const visibleRoutes = useMemo(() => {
    const routes: string[] = [];

    visibleNavigation.forEach((item) => {
      if (item.href) {
        routes.push(item.href);
        return;
      }
      (item.children || []).forEach((child) => routes.push(child.href));
    });

    return Array.from(new Set(routes));
  }, [visibleNavigation]);

  const prefetchRoute = useCallback((href?: string) => {
    if (!href) return;
    try {
      router.prefetch(href);
    } catch {
      // Ignore prefetch failures; navigation still works via push/link.
    }
  }, [router]);

  useEffect(() => {
    if (!visibleRoutes.length) return;

    let cancelled = false;
    const timeoutIds: number[] = [];
    const win = window as any;

    const startWarmup = () => {
      visibleRoutes.slice(0, 14).forEach((href, index) => {
        const id = window.setTimeout(() => {
          if (!cancelled) prefetchRoute(href);
        }, index * 130);
        timeoutIds.push(id);
      });
    };

    let idleId: number | undefined;
    if (typeof win.requestIdleCallback === 'function') {
      idleId = win.requestIdleCallback(startWarmup, { timeout: 1500 });
    } else {
      const id = window.setTimeout(startWarmup, 220);
      timeoutIds.push(id);
    }

    return () => {
      cancelled = true;
      timeoutIds.forEach((id) => window.clearTimeout(id));
      if (idleId !== undefined && typeof win.cancelIdleCallback === 'function') {
        win.cancelIdleCallback(idleId);
      }
    };
  }, [prefetchRoute, visibleRoutes]);

  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => {
    // Auto-expand the group containing the current page
    const initial: Record<string, boolean> = {};
    NAVIGATION_ITEMS.forEach((item) => {
      if (item.children?.some((c) => pathname === c.href || pathname.startsWith(c.href + '/'))) {
        initial[item.name] = true;
      }
    });
    return initial;
  });

  const isActive = (href: string) => pathname === href;
  const isGroupActive = (children?: NavChild[]) =>
    children?.some((c) => pathname === c.href || pathname.startsWith(c.href + '/'));

  const toggleGroup = (name: string) => {
    setOpenGroups((prev) => ({ ...prev, [name]: !prev[name] }));
  };

  const closeForMobile = () => {
    onMobileClose?.();
  };

  return (
    <>
      <AnimatePresence>
        {mobileOpen && (
          <motion.button
            type="button"
            aria-label="Close navigation"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={closeForMobile}
            className="fixed inset-0 z-30 bg-black/45 backdrop-blur-[1px] md:hidden"
          />
        )}
      </AnimatePresence>

      <aside
        className={`fixed md:sticky top-0 left-0 md:left-auto z-40 flex flex-col min-h-0 shrink-0 h-dvh md:h-dvh overflow-hidden transition-all duration-300 ease-in-out
          w-[84vw] max-w-[340px]
          ${collapsed ? 'md:w-[72px] 2xl:w-[88px]' : 'md:w-[260px] 2xl:w-[300px] 3xl:w-[340px]'}
          ${mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
          bg-white dark:bg-slate-950 border-r border-slate-200/70 dark:border-slate-800/70`}
      >
        {/* Logo */}
        <div className="h-14 2xl:h-16 flex items-center px-3.5 2xl:px-4 border-b border-slate-100 dark:border-slate-800/50">
          <Link
            href="/dashboard"
            onClick={closeForMobile}
            onMouseEnter={() => prefetchRoute('/dashboard')}
            onFocus={() => prefetchRoute('/dashboard')}
            className="flex items-center gap-3 overflow-hidden flex-1 min-w-0"
          >
            <div className="w-8 h-8 2xl:w-9 2xl:h-9 rounded-lg bg-primary-600 flex items-center justify-center flex-shrink-0">
              <span className="text-white font-bold text-sm 2xl:text-base">A</span>
            </div>
            <motion.span
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              className={`text-base 2xl:text-lg 3xl:text-xl font-bold text-slate-900 dark:text-white whitespace-nowrap ${collapsed ? 'md:hidden' : ''}`}
            >
              Anthrilo
            </motion.span>
          </Link>

          <button
            type="button"
            onClick={closeForMobile}
            className="md:hidden p-1.5 rounded-lg text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
            aria-label="Close navigation"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 min-h-0 overflow-y-auto overscroll-contain py-3 px-2.5 2xl:px-3 pb-4 space-y-0.5">
          {visibleNavigation.map((item) => {
            if (item.href) {
              // Direct link (no children)
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  prefetch
                  onClick={closeForMobile}
                  onMouseEnter={() => prefetchRoute(item.href)}
                  onFocus={() => prefetchRoute(item.href)}
                  className={`sidebar-item 2xl:text-[15px] ${isActive(item.href) ? 'sidebar-active' : ''}`}
                  title={collapsed ? item.name : undefined}
                >
                  <item.icon className="w-[18px] h-[18px] 2xl:w-5 2xl:h-5 flex-shrink-0" strokeWidth={1.8} />
                  <span className={`${collapsed ? 'md:hidden' : ''}`}>{item.name}</span>
                </Link>
              );
            }

            // Group with children
            const groupActive = isGroupActive(item.children);
            const isOpen = openGroups[item.name] || false;

            return (
              <div key={item.name} className="space-y-0.5">
                <button
                  onClick={() => toggleGroup(item.name)}
                  className={`sidebar-item w-full 2xl:text-[15px] ${groupActive ? 'text-primary-700 dark:text-primary-300 font-semibold' : ''
                    }`}
                  title={collapsed ? item.name : undefined}
                >
                  <item.icon className="w-[18px] h-[18px] 2xl:w-5 2xl:h-5 flex-shrink-0" strokeWidth={1.8} />
                  <span className={`flex-1 text-left ${collapsed ? 'md:hidden' : ''}`}>{item.name}</span>
                  <ChevronDown
                    className={`w-3.5 h-3.5 text-slate-400 transition-transform duration-200 ${collapsed ? 'md:hidden' : ''} ${isOpen ? 'rotate-180' : ''
                      }`}
                  />
                </button>

                {/* Sub-items */}
                <AnimatePresence initial={false}>
                  {isOpen && item.children && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2, ease: 'easeInOut' }}
                      className={`overflow-hidden ${collapsed ? 'md:hidden' : ''}`}
                    >
                      <div className="ml-3 pl-3 border-l border-slate-200 dark:border-slate-800 space-y-0.5">
                        {item.children.map((child) => (
                          <Link
                            key={child.href}
                            href={child.href}
                            prefetch
                            onClick={closeForMobile}
                            onMouseEnter={() => prefetchRoute(child.href)}
                            onFocus={() => prefetchRoute(child.href)}
                            className={`flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-[13px] 2xl:text-sm transition-colors duration-150 ${isActive(child.href)
                              ? 'text-primary-600 dark:text-primary-400 bg-primary-50/80 dark:bg-primary-950/40 font-medium'
                              : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800/50'
                              }`}
                          >
                            {child.icon && <child.icon className="w-3.5 h-3.5 2xl:w-4 2xl:h-4 flex-shrink-0" strokeWidth={1.8} />}
                            <span>{child.name}</span>
                          </Link>
                        ))}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </nav>

        {/* Collapse Toggle */}
        <div className="p-3 border-t border-slate-100 dark:border-slate-800/50 hidden md:block">
          <button
            onClick={onToggle}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl text-xs 2xl:text-sm
                     text-slate-400 hover:text-slate-600 dark:hover:text-slate-300
                     hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors"
          >
            {collapsed ? (
              <ChevronRight className="w-4 h-4" />
            ) : (
              <>
                <ChevronLeft className="w-4 h-4" />
                <span>Collapse</span>
              </>
            )}
          </button>
        </div>
      </aside>
    </>
  );
}
