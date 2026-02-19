'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import { ThemeToggle } from '@/components/ui/ThemeToggle';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  const navigation = [
    { name: 'Overview', href: '/dashboard', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
    {
      name: 'Reports',
      icon: 'M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z',
      children: [
        { name: 'All Reports', href: '/dashboard/reports/reports-index' },
        { name: 'Stock Analysis', href: '/dashboard/reports/raw-materials/stock-analysis' },
        { name: 'Top Sellers', href: '/dashboard/reports/raw-materials/yarn-forecasting' },
        { name: 'SKU Sales', href: '/dashboard/reports/sales/bundle-sku' },
        { name: 'Discounts', href: '/dashboard/reports/sales/discount-general' },
        { name: 'Channels', href: '/dashboard/reports/panels/settlement' },
      ],
    },
    {
      name: 'Garments',
      icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4',
      children: [
        { name: 'Master Data', href: '/dashboard/garments/master' },
        { name: 'Inventory', href: '/dashboard/garments/inventory' },
        { name: 'Orders', href: '/dashboard/garments/production' },
        { name: 'Best SKUs', href: '/dashboard/garments/best-skus' },
        { name: 'SKU Velocity', href: '/dashboard/garments/sku-velocity' },
      ],
    },
    {
      name: 'Sales',
      icon: 'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
      children: [
        { name: 'Transactions', href: '/dashboard/sales/transactions' },
        { name: 'Panels', href: '/dashboard/sales/panels' },
        { name: 'Reports', href: '/dashboard/sales/reports' },
        { name: 'COD vs Prepaid', href: '/dashboard/sales/cod-prepaid' },
      ],
    },
    {
      name: 'Financial',
      icon: 'M13 7h8m0 0v8m0-8l-8 8-4-4-6 6',
      children: [
        { name: 'Overview', href: '/dashboard/financial' },
        { name: 'Discounts', href: '/dashboard/financial/discounts' },
        { name: 'ROI Analysis', href: '/dashboard/financial/roi' },
      ],
    },
  ];

  const isActive = (href: string) => pathname === href;
  const isGroupActive = (children?: { href: string }[]) =>
    children?.some(c => pathname === c.href || pathname.startsWith(c.href + '/'));

  return (
    <div className="h-screen flex overflow-hidden bg-slate-50 dark:bg-slate-900">
      {/* Sidebar - Fixed */}
      <aside className={`${collapsed ? 'w-[68px]' : 'w-60'} flex-shrink-0 flex flex-col h-screen sticky top-0 transition-all duration-300 bg-white dark:bg-slate-800 border-r border-slate-200/80 dark:border-slate-700/80`}>
        {/* Logo */}
        <div className="h-16 flex items-center px-4 border-b border-slate-100 dark:border-slate-700/50">
          <Link href="/dashboard" className="flex items-center gap-2.5 overflow-hidden">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-primary-500 to-indigo-600 flex items-center justify-center flex-shrink-0">
              <span className="text-white font-black text-sm">A</span>
            </div>
            {!collapsed && (
              <span className="text-lg font-bold bg-gradient-to-r from-primary-600 to-indigo-600 dark:from-primary-400 dark:to-indigo-400 bg-clip-text text-transparent whitespace-nowrap">
                Anthrilo
              </span>
            )}
          </Link>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
          {navigation.map((item) => {
            if ('href' in item) {
              return (
                <Link key={item.name} href={(item as any).href}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all duration-200 ${isActive((item as any).href) ? 'sidebar-active' : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700/50 hover:text-slate-900 dark:hover:text-white'
                    }`}>
                  <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
                    <path strokeLinecap="round" strokeLinejoin="round" d={item.icon} />
                  </svg>
                  {!collapsed && <span>{item.name}</span>}
                </Link>
              );
            }
            return (
              <div key={item.name} className="space-y-0.5">
                <div className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium ${isGroupActive((item as any).children) ? 'text-primary-600 dark:text-primary-400' : 'text-slate-500 dark:text-slate-400'
                  }`}>
                  <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
                    <path strokeLinecap="round" strokeLinejoin="round" d={item.icon} />
                  </svg>
                  {!collapsed && <span>{item.name}</span>}
                </div>
                {!collapsed && (item as any).children && (
                  <div className="ml-8 space-y-0.5">
                    {(item as any).children.map((child: any) => (
                      <Link key={child.href} href={child.href}
                        className={`block px-3 py-2 rounded-lg text-[13px] transition-all duration-200 ${isActive(child.href) ? 'text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/20 font-semibold' : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700/30'
                          }`}>
                        {child.name}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        {/* Sidebar Footer */}
        <div className="p-3 border-t border-slate-100 dark:border-slate-700/50">
          <button onClick={() => setCollapsed(!collapsed)}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-all">
            <svg className={`w-4 h-4 transition-transform ${collapsed ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            </svg>
            {!collapsed && <span>Collapse</span>}
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Bar */}
        <header className="h-16 flex-shrink-0 flex items-center justify-between px-6 bg-white/80 dark:bg-slate-800/80 backdrop-blur-md border-b border-slate-200/80 dark:border-slate-700/80 sticky top-0 z-30">
          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-1.5 text-sm text-slate-400">
              {pathname.split('/').filter(Boolean).map((seg, i, arr) => {
                const href = '/' + arr.slice(0, i + 1).join('/');
                const isLast = i === arr.length - 1;
                return (
                  <span key={i} className="flex items-center gap-1.5">
                    {i > 0 && <span>/</span>}
                    {isLast ? (
                      <span className="text-slate-700 dark:text-slate-200 font-medium capitalize">
                        {seg.replace(/-/g, ' ')}
                      </span>
                    ) : (
                      <Link href={href} className="capitalize hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                        {seg.replace(/-/g, ' ')}
                      </Link>
                    )}
                  </span>
                );
              })}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-primary-400 to-indigo-500 flex items-center justify-center">
              <span className="text-white text-xs font-bold">A</span>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto p-6 lg:p-8 page-gradient">
          {children}
        </main>
      </div>
    </div>
  );
}
