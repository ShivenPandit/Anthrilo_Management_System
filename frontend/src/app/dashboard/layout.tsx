'use client';

import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { ucSales } from '@/features/sales/api';
import { Sidebar } from '@/components/layout/Sidebar';
import { Navbar } from '@/components/layout/Navbar';
import { AuthGuard } from '@/components/auth/AuthGuard';

function scheduleIdleWarmup(task: () => void, fallbackDelay = 220): () => void {
  if (typeof window === 'undefined') {
    return () => undefined;
  }

  const win = window as any;
  if (typeof win.requestIdleCallback === 'function') {
    const idleId = win.requestIdleCallback(task, { timeout: 1400 });
    return () => {
      if (typeof win.cancelIdleCallback === 'function') {
        win.cancelIdleCallback(idleId);
      }
    };
  }

  const timeoutId = window.setTimeout(task, fallbackDelay);
  return () => window.clearTimeout(timeoutId);
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const pathname = usePathname();
  const queryClient = useQueryClient();

  useEffect(() => {
    setMobileSidebarOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('access_token')) {
      return;
    }

    let cancelled = false;

    const warmSharedQueries = async () => {
      if (cancelled) return;

      await Promise.allSettled([
        queryClient.prefetchQuery({
          queryKey: ['unicommerce-today'],
          queryFn: async () => (await ucSales.getToday()).data,
          staleTime: 10 * 60 * 1000,
        }),
        queryClient.prefetchQuery({
          queryKey: ['unicommerce-yesterday'],
          queryFn: async () => (await ucSales.getYesterday()).data,
          staleTime: 2 * 60 * 60 * 1000,
        }),
        queryClient.prefetchQuery({
          queryKey: ['unicommerce-last-7-days'],
          queryFn: async () => (await ucSales.getLast7Days()).data,
          staleTime: 2 * 60 * 60 * 1000,
        }),
      ]);
    };

    const cancelWarmup = scheduleIdleWarmup(() => {
      void warmSharedQueries();
    });

    return () => {
      cancelled = true;
      cancelWarmup();
    };
  }, [queryClient]);

  return (
    <AuthGuard>
      <div
        data-dashboard-scroll-container
        className="h-dvh flex overflow-hidden bg-surface-50 dark:bg-slate-950"
      >
        {/* Sidebar */}
        <Sidebar
          collapsed={collapsed}
          onToggle={() => setCollapsed(!collapsed)}
          mobileOpen={mobileSidebarOpen}
          onMobileClose={() => setMobileSidebarOpen(false)}
        />

        {/* Main Content */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Top Navbar */}
          <Navbar onOpenSidebar={() => setMobileSidebarOpen(true)} />

          {/* Page Content */}
          <main className="flex-1 overflow-y-auto page-gradient px-3 py-3 sm:px-4 sm:py-4 lg:px-6 lg:py-6 2xl:px-8 2xl:py-8 3xl:px-10 3xl:py-10">
            <div className="page-shell">{children}</div>
          </main>
        </div>
      </div>
    </AuthGuard>
  );
}
