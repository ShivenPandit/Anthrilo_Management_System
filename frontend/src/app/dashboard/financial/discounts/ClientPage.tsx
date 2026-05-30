'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ucSales } from '@/features/financial';
import { PageHeader, ProgressLoader, ErrorPanel } from '@/components/ui/Common';
import Link from 'next/link';
import { motion } from 'framer-motion';
import {
  Percent, TrendingDown, Tag, Package, Store,
  ArrowRight, BarChart3, FileText,
} from 'lucide-react';

const fmt = (v: number) =>
  v >= 100000 ? `₹${(v / 100000).toFixed(1)}L` : v >= 1000 ? `₹${(v / 1000).toFixed(1)}K` : `₹${v.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

const PERIODS = [
  { key: 'today', label: 'Today' },
  { key: 'yesterday', label: 'Yesterday' },
  { key: 'last_7_days', label: '7 Days' },
  { key: 'last_30_days', label: '30 Days' },
];

export default function DiscountsPage() {
  const [period, setPeriod] = useState('last_7_days');

  const { data, isLoading, error } = useQuery({
    queryKey: ['discount-overview', period],
    queryFn: async () => (await ucSales.getSalesBySku({ period })).data,
    staleTime: 120_000,
  });

  const summary = useMemo(() => data?.summary ?? {}, [data?.summary]);
  const skus = useMemo(() => data?.skus ?? [], [data?.skus]);

  const stats = useMemo(() => {
    const avgDisc = summary.avg_discount_pct ?? 0;
    const totalDisc = summary.total_discount ?? 0;
    const totalRev = summary.total_revenue ?? 0;
    const totalMrp = summary.total_mrp ?? 0;
    const totalSkus = summary.total_skus ?? 0;
    const discountedSkus = skus.filter((s: any) => (s.discount_pct ?? 0) > 0).length;
    const zeroDisc = skus.filter((s: any) => (s.discount_pct ?? 0) === 0).length;
    const heavyDisc = skus.filter((s: any) => (s.discount_pct ?? 0) > 30).length;
    return { avgDisc, totalDisc, totalRev, totalMrp, totalSkus, discountedSkus, zeroDisc, heavyDisc };
  }, [summary, skus]);

  // Top 5 highest discount SKUs
  const topDiscounted = useMemo(() =>
    [...skus]
      .filter((s: any) => s.discount_pct > 0)
      .sort((a: any, b: any) => b.discount_pct - a.discount_pct)
      .slice(0, 5),
    [skus]
  );

  // Channel aggregation
  const channelStats = useMemo(() => {
    const map: Record<string, { channel: string; revenue: number; mrp: number }> = {};
    for (const sku of skus) {
      const channels = (sku as any).channels || {};
      for (const [ch, chData] of Object.entries(channels) as [string, any][]) {
        if (!map[ch]) map[ch] = { channel: ch, revenue: 0, mrp: 0 };
        map[ch].revenue += chData.revenue || 0;
      }
      const totalRev = (sku as any).total_revenue || 0;
      const totalMrp = (sku as any).total_mrp || totalRev;
      if (totalRev > 0) {
        for (const [ch, chData] of Object.entries(channels) as [string, any][]) {
          const prop = (chData.revenue || 0) / totalRev;
          map[ch].mrp += totalMrp * prop;
        }
      }
    }
    return Object.values(map)
      .map(c => ({ ...c, discount: Math.max(c.mrp - c.revenue, 0), disc_pct: c.mrp > 0 ? ((c.mrp - c.revenue) / c.mrp) * 100 : 0 }))
      .sort((a, b) => b.discount - a.discount)
      .slice(0, 6);
  }, [skus]);

  return (
    <div className="space-y-6">
      <PageHeader title="Discount Analytics" description="Comprehensive discount analysis across products and channels" />

      {/* Period Selector */}
      <div className="flex items-center gap-2">
        {PERIODS.map(p => (
          <button key={p.key} onClick={() => setPeriod(p.key)}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-all duration-200 ${period === p.key
                ? 'bg-primary-600 text-white shadow-md shadow-primary-500/20'
                : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700 hover:border-primary-300 dark:hover:border-primary-700'
              }`}>
            {p.label}
          </button>
        ))}
      </div>

      {error && <ErrorPanel message="Failed to load discount data. Please try again." />}

      <ProgressLoader loading={isLoading} stages={[
        { at: 0, label: 'Connecting to Unicommerce…' },
        { at: 25, label: 'Fetching discount data…' },
        { at: 55, label: 'Computing analytics…' },
        { at: 85, label: 'Finalizing…' },
      ]} />
      {!isLoading && (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { title: 'Avg Discount', value: `${stats.avgDisc.toFixed(1)}%`, icon: Percent, color: 'blue', sub: `${stats.totalSkus} SKUs analyzed` },
              { title: 'Total Discount', value: fmt(stats.totalDisc), icon: TrendingDown, color: 'red', sub: `of ${fmt(stats.totalMrp)} MRP` },
              { title: 'Net Revenue', value: fmt(stats.totalRev), icon: Tag, color: 'green', sub: 'After discounts' },
              { title: 'Discounted SKUs', value: `${stats.discountedSkus}`, icon: Package, color: 'purple', sub: `${stats.zeroDisc} at full price` },
            ].map((card, i) => (
              <motion.div key={card.title}
                initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: i * 0.06 }}
                className="rounded-2xl border border-slate-200/60 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-[var(--shadow-soft)] p-5"
              >
                <div className="flex items-start justify-between mb-3">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">{card.title}</p>
                  <div className={`p-2 rounded-xl bg-${card.color === 'blue' ? 'blue' : card.color === 'red' ? 'rose' : card.color === 'green' ? 'emerald' : 'violet'}-500/10`}>
                    <card.icon className={`w-4 h-4 text-${card.color === 'blue' ? 'blue' : card.color === 'red' ? 'rose' : card.color === 'green' ? 'emerald' : 'violet'}-500`} strokeWidth={2} />
                  </div>
                </div>
                <p className="text-2xl font-bold text-slate-900 dark:text-white">{card.value}</p>
                <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">{card.sub}</p>
              </motion.div>
            ))}
          </div>

          {/* Discount Distribution + Heavy Discount Warning */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Discount Buckets */}
            <div className="card">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-4">Discount Distribution</h3>
              <div className="space-y-3">
                {[
                  { label: '0% (Full Price)', count: skus.filter((s: any) => (s.discount_pct ?? 0) === 0).length, color: 'bg-emerald-500', textColor: 'text-emerald-600 dark:text-emerald-400' },
                  { label: '1–10%', count: skus.filter((s: any) => s.discount_pct > 0 && s.discount_pct <= 10).length, color: 'bg-blue-500', textColor: 'text-blue-600 dark:text-blue-400' },
                  { label: '10–20%', count: skus.filter((s: any) => s.discount_pct > 10 && s.discount_pct <= 20).length, color: 'bg-amber-500', textColor: 'text-amber-600 dark:text-amber-400' },
                  { label: '20–30%', count: skus.filter((s: any) => s.discount_pct > 20 && s.discount_pct <= 30).length, color: 'bg-orange-500', textColor: 'text-orange-600 dark:text-orange-400' },
                  { label: '30%+', count: skus.filter((s: any) => s.discount_pct > 30).length, color: 'bg-rose-500', textColor: 'text-rose-600 dark:text-rose-400' },
                ].map(bucket => {
                  const pct = stats.totalSkus > 0 ? (bucket.count / stats.totalSkus) * 100 : 0;
                  return (
                    <div key={bucket.label} className="flex items-center gap-3">
                      <span className="text-xs font-medium text-slate-500 dark:text-slate-400 w-24">{bucket.label}</span>
                      <div className="flex-1 h-3 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                        <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }}
                          transition={{ duration: 0.5, ease: 'easeOut' }}
                          className={`h-full rounded-full ${bucket.color}`} />
                      </div>
                      <span className={`text-sm font-bold w-10 text-right ${bucket.textColor}`}>{bucket.count}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Top Discounted SKUs */}
            <div className="card">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-4">Highest Discount SKUs</h3>
              {topDiscounted.length === 0 ? (
                <p className="text-sm text-slate-400">No discounted SKUs in this period.</p>
              ) : (
                <div className="space-y-2">
                  {topDiscounted.map((sku: any, i: number) => (
                    <div key={i} className="flex items-center gap-3 p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold text-white ${sku.discount_pct > 30 ? 'bg-rose-500' : sku.discount_pct > 20 ? 'bg-orange-500' : 'bg-amber-500'
                        }`}>
                        {sku.discount_pct.toFixed(0)}%
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{sku.sku || 'Unknown'}</p>
                        <p className="text-xs text-slate-400 truncate">{sku.name || ''}</p>
                      </div>
                      <span className="text-sm font-semibold text-rose-600 dark:text-rose-400">{fmt(sku.total_discount || 0)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Channel Discount Overview */}
          {channelStats.length > 0 && (
            <div className="card">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-4">Channel Discount Overview</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                {channelStats.map((ch, i) => (
                  <motion.div key={ch.channel}
                    initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.2, delay: i * 0.04 }}
                    className="p-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/30 text-center"
                  >
                    <Store className="w-4 h-4 mx-auto text-slate-400 mb-2" />
                    <p className="text-xs font-medium text-slate-600 dark:text-slate-300 truncate">{ch.channel}</p>
                    <p className={`text-lg font-bold mt-1 ${ch.disc_pct > 30 ? 'text-rose-600 dark:text-rose-400' : ch.disc_pct > 15 ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400'
                      }`}>{ch.disc_pct.toFixed(1)}%</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">{fmt(ch.discount)}</p>
                  </motion.div>
                ))}
              </div>
            </div>
          )}

          {/* Quick Links to Detailed Reports */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Link href="/dashboard/reports/sales/discount-general">
              <motion.div whileHover={{ y: -2 }}
                className="card-interactive p-5 flex items-center gap-4 group"
              >
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center flex-shrink-0">
                  <BarChart3 className="w-6 h-6 text-white" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-white group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">
                    SKU-wise Discount Report
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">Product-level discount breakdown with bucketing</p>
                </div>
                <ArrowRight className="w-5 h-5 text-slate-300 dark:text-slate-600 group-hover:text-primary-500 transition-colors" />
              </motion.div>
            </Link>

            <Link href="/dashboard/reports/sales/discount-by-panel">
              <motion.div whileHover={{ y: -2 }}
                className="card-interactive p-5 flex items-center gap-4 group"
              >
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center flex-shrink-0">
                  <FileText className="w-6 h-6 text-white" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-white group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">
                    Channel-wise Discount Report
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">Compare discount performance across channels</p>
                </div>
                <ArrowRight className="w-5 h-5 text-slate-300 dark:text-slate-600 group-hover:text-primary-500 transition-colors" />
              </motion.div>
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
