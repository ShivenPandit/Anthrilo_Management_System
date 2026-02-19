'use client';

import Link from 'next/link';
import { ThemeToggle } from '@/components/ui/ThemeToggle';

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-primary-50/30 to-violet-50/40 dark:from-slate-950 dark:via-slate-900 dark:to-slate-950">
      {/* Navigation */}
      <nav className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-xl border-b border-white/40 dark:border-slate-800/60 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-600 to-violet-600 flex items-center justify-center">
                <span className="text-white font-bold text-sm">A</span>
              </div>
              <span className="text-xl font-bold text-slate-900 dark:text-white">Anthrilo</span>
            </div>
            <div className="flex items-center gap-3">
              <ThemeToggle />
              <Link href="/dashboard" className="px-5 py-2 rounded-xl bg-gradient-to-r from-primary-600 to-violet-600 text-white text-sm font-semibold shadow-lg shadow-primary-500/25 hover:shadow-primary-500/40 transition-all">
                Open Dashboard
              </Link>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Hero */}
        <div className="text-center pt-20 pb-16">
          <div className="inline-flex items-center gap-2 mb-6 px-4 py-1.5 rounded-full bg-primary-100/60 dark:bg-primary-900/30 border border-primary-200 dark:border-primary-800">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-sm font-medium text-primary-700 dark:text-primary-300">Live Unicommerce Data</span>
          </div>
          <h1 className="text-5xl md:text-6xl lg:text-7xl font-extrabold leading-tight mb-6">
            <span className="text-slate-900 dark:text-white">Anthrilo</span>
            <br />
            <span className="bg-gradient-to-r from-primary-600 via-violet-600 to-purple-600 bg-clip-text text-transparent">Management System</span>
          </h1>
          <p className="text-lg md:text-xl text-slate-600 dark:text-slate-400 max-w-2xl mx-auto leading-relaxed">
            Real-time inventory, sales, and financial analytics powered by Unicommerce — all in one modern dashboard.
          </p>
          <div className="mt-10 flex justify-center gap-4">
            <Link href="/dashboard" className="px-8 py-3.5 rounded-2xl bg-gradient-to-r from-primary-600 to-violet-600 text-white font-semibold shadow-xl shadow-primary-500/25 hover:shadow-primary-500/40 hover:-translate-y-0.5 transition-all text-lg">
              Get Started
            </Link>
            <a href="#features" className="px-8 py-3.5 rounded-2xl bg-white/80 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 font-semibold hover:bg-white dark:hover:bg-slate-800 transition-all text-lg">
              Learn More
            </a>
          </div>
        </div>

        {/* Modules */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 py-12">
          {[
            { title: 'Reports & Analytics', desc: 'Stock analysis, SKU sales breakdown, channel revenue, and discounts — all from real data.', href: '/dashboard/reports/reports-index', gradient: 'from-blue-500 to-cyan-500', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
            { title: 'Garments & Sales', desc: 'Catalog management, inventory tracking, production orders, and transaction history.', href: '/dashboard/garments', gradient: 'from-emerald-500 to-green-500', icon: 'M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z' },
            { title: 'Financial', desc: 'Revenue analytics, discount management, ROI analysis, and profitability tracking.', href: '/dashboard/financial', gradient: 'from-violet-500 to-purple-500', icon: 'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
          ].map((m) => (
            <Link key={m.href} href={m.href} className="group relative overflow-hidden rounded-2xl bg-white/70 dark:bg-slate-800/70 backdrop-blur-sm border border-white/60 dark:border-slate-700/60 p-6 hover:shadow-xl hover:-translate-y-1 transition-all duration-300">
              <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${m.gradient} flex items-center justify-center mb-4 shadow-lg group-hover:scale-110 transition-transform`}>
                <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={m.icon} /></svg>
              </div>
              <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">{m.title}</h3>
              <p className="text-slate-600 dark:text-slate-400 text-sm leading-relaxed">{m.desc}</p>
              <div className="mt-4 text-primary-600 dark:text-primary-400 text-sm font-semibold flex items-center gap-1 group-hover:gap-2 transition-all">
                Explore <span>→</span>
              </div>
            </Link>
          ))}
        </div>

        {/* Features */}
        <div id="features" className="py-16">
          <h2 className="text-3xl font-bold text-center text-slate-900 dark:text-white mb-12">Why Anthrilo?</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {[
              { title: 'Real-time Unicommerce Sync', desc: 'Live catalog, orders, and revenue data from 11+ sales channels synced automatically.', bgClass: 'bg-primary-100 dark:bg-primary-900/30', textClass: 'text-primary-600 dark:text-primary-400' },
              { title: '61,000+ Products Tracked', desc: 'Full catalog search, inventory monitoring, and stock analysis in real-time.', bgClass: 'bg-emerald-100 dark:bg-emerald-900/30', textClass: 'text-emerald-600 dark:text-emerald-400' },
              { title: 'Actionable Analytics', desc: 'Channel-wise revenue, SKU sales breakdown, discount analysis, and profitability reports.', bgClass: 'bg-violet-100 dark:bg-violet-900/30', textClass: 'text-violet-600 dark:text-violet-400' },
              { title: 'Modern & Fast', desc: 'Built with Next.js 14, React Query caching, and a responsive glass-morphism UI.', bgClass: 'bg-amber-100 dark:bg-amber-900/30', textClass: 'text-amber-600 dark:text-amber-400' },
            ].map((f) => (
              <div key={f.title} className="flex items-start gap-4 p-6 rounded-2xl bg-white/60 dark:bg-slate-800/60 backdrop-blur-sm border border-white/40 dark:border-slate-700/40">
                <div className={`w-10 h-10 rounded-xl ${f.bgClass} flex items-center justify-center flex-shrink-0`}>
                  <svg className={`w-5 h-5 ${f.textClass}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                </div>
                <div>
                  <h4 className="font-bold text-slate-900 dark:text-white mb-1">{f.title}</h4>
                  <p className="text-slate-600 dark:text-slate-400 text-sm">{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 py-12">
          {[
            { num: '61K+', label: 'Products', textClass: 'text-primary-600 dark:text-primary-400' },
            { num: '11+', label: 'Sales Channels', textClass: 'text-emerald-600 dark:text-emerald-400' },
            { num: '19+', label: 'Reports', textClass: 'text-violet-600 dark:text-violet-400' },
            { num: '24/7', label: 'Real-time', textClass: 'text-amber-600 dark:text-amber-400' },
          ].map((s) => (
            <div key={s.label} className="text-center p-6 rounded-2xl bg-white/60 dark:bg-slate-800/60 backdrop-blur-sm border border-white/40 dark:border-slate-700/40">
              <div className={`text-3xl font-extrabold ${s.textClass} mb-1`}>{s.num}</div>
              <div className="text-slate-600 dark:text-slate-400 text-sm font-medium">{s.label}</div>
            </div>
          ))}
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-slate-900 dark:bg-black border-t border-slate-800 mt-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-8">
            <div>
              <span className="text-xl font-bold bg-gradient-to-r from-primary-400 to-violet-400 bg-clip-text text-transparent">Anthrilo</span>
              <p className="text-slate-500 mt-2 text-sm">Enterprise management powered by Unicommerce real-time data.</p>
            </div>
            <div>
              <h4 className="font-semibold text-slate-300 mb-3 text-sm">Quick Links</h4>
              <ul className="space-y-2">
                <li><Link href="/dashboard" className="text-slate-500 hover:text-primary-400 transition-colors text-sm">Dashboard</Link></li>
                <li><Link href="/dashboard/reports/reports-index" className="text-slate-500 hover:text-primary-400 transition-colors text-sm">Reports</Link></li>
                <li><Link href="/dashboard/garments/master" className="text-slate-500 hover:text-primary-400 transition-colors text-sm">Products</Link></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold text-slate-300 mb-3 text-sm">Modules</h4>
              <ul className="space-y-2">
                <li><Link href="/dashboard/garments" className="text-slate-500 hover:text-primary-400 transition-colors text-sm">Garments</Link></li>
                <li><Link href="/dashboard/sales" className="text-slate-500 hover:text-primary-400 transition-colors text-sm">Sales</Link></li>
                <li><Link href="/dashboard/financial" className="text-slate-500 hover:text-primary-400 transition-colors text-sm">Financial</Link></li>
              </ul>
            </div>
          </div>
          <div className="border-t border-slate-800 pt-8">
            <p className="text-center text-slate-600 text-sm">&copy; 2026 Anthrilo Management System. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
