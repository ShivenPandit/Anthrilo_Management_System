'use client';

import Link from 'next/link';
import { ThemeToggle } from '@/components/ui/ThemeToggle';

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      <nav className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-md shadow-lg border-b border-gray-200 dark:border-gray-700 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center">
              <h1 className="text-2xl font-bold bg-gradient-to-r from-primary-600 to-purple-600 dark:from-primary-400 dark:to-purple-400 bg-clip-text text-transparent">
                Anthrilo
              </h1>
            </div>
            <div className="flex items-center space-x-4">
              <ThemeToggle />
              <Link href="/login" className="btn btn-secondary">
                Login
              </Link>
              <Link href="/dashboard" className="btn btn-primary">
                Dashboard
              </Link>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {/* Hero Section */}
        <div className="text-center mb-16 pt-8">
          <div className="inline-block mb-4">
            <span className="px-4 py-2 bg-primary-100 dark:bg-primary-900/30 text-primary-800 dark:text-primary-300 rounded-full text-sm font-semibold animate-pulse">
              Enterprise ERP Solution
            </span>
          </div>
          <h1 className="text-5xl md:text-6xl font-bold text-gray-900 dark:text-gray-100 mb-6 leading-tight">
            Anthrilo Management System
          </h1>
          <p className="text-xl md:text-2xl text-gray-600 dark:text-gray-300 max-w-3xl mx-auto leading-relaxed">
            Enterprise-grade ERP solution for textile manufacturing and garment production management
          </p>
          <div className="mt-8 flex justify-center gap-4">
            <Link href="/dashboard" className="btn btn-primary text-lg px-8 py-3">
              Get Started
            </Link>
            <Link href="#features" className="btn btn-secondary text-lg px-8 py-3">
              Learn More
            </Link>
          </div>
        </div>

        {/* Modules Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mt-16">
          {/* Module I */}
          <div className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-blue-500 dark:border-l-blue-400 group">
            <div className="text-primary-600 dark:text-primary-400 mb-4 transform group-hover:scale-110 transition-transform duration-300">
              <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            <h3 className="mb-3 text-gray-900 dark:text-gray-100 font-bold">Raw Material & Processing</h3>
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              Manage yarn, fabric, and processing workflows including knitting, dyeing, finishing, and printing
            </p>
            <Link href="/dashboard/raw-materials" className="text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 font-semibold inline-flex items-center group">
              Learn more 
              <svg className="w-4 h-4 ml-1 transform group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </Link>
          </div>

          {/* Module II */}
          <div className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-green-500 dark:border-l-green-400 group">
            <div className="text-green-600 dark:text-green-400 mb-4 transform group-hover:scale-110 transition-transform duration-300">
              <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
              </svg>
            </div>
            <h3 className="mb-3 text-gray-900 dark:text-gray-100 font-bold">Garment & Sales</h3>
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              Track inventory, production planning, sales transactions, and panel-wise performance
            </p>
            <Link href="/dashboard/garments" className="text-green-600 dark:text-green-400 hover:text-green-700 dark:hover:text-green-300 font-semibold inline-flex items-center group">
              Learn more 
              <svg className="w-4 h-4 ml-1 transform group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </Link>
          </div>

          {/* Module III */}
          <div className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-purple-500 dark:border-l-purple-400 group">
            <div className="text-purple-600 dark:text-purple-400 mb-4 transform group-hover:scale-110 transition-transform duration-300">
              <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <h3 className="mb-3 text-gray-900 dark:text-gray-100 font-bold">Financial & Marketing</h3>
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              Manage discounts, track paid advertising ROI, and generate comprehensive financial reports
            </p>
            <Link href="/dashboard/financial" className="text-purple-600 dark:text-purple-400 hover:text-purple-700 dark:hover:text-purple-300 font-semibold inline-flex items-center group">
              Learn more 
              <svg className="w-4 h-4 ml-1 transform group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </Link>
          </div>
        </div>

        {/* Key Features */}
        <div id="features" className="mt-20 card">
          <h2 className="mb-8 text-center text-gray-900 dark:text-gray-100">Key Features</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="flex items-start group">
              <div className="flex-shrink-0">
                <div className="flex items-center justify-center h-14 w-14 rounded-xl bg-gradient-to-br from-primary-500 to-primary-600 dark:from-primary-400 dark:to-primary-500 text-white shadow-lg transform group-hover:scale-110 transition-transform duration-300">
                  <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              </div>
              <div className="ml-5">
                <h4 className="font-bold text-gray-900 dark:text-gray-100 mb-2">Real-time Inventory Tracking</h4>
                <p className="text-gray-600 dark:text-gray-400">Monitor stock levels across all warehouses in real-time with automated alerts</p>
              </div>
            </div>
            
            <div className="flex items-start group">
              <div className="flex-shrink-0">
                <div className="flex items-center justify-center h-14 w-14 rounded-xl bg-gradient-to-br from-green-500 to-green-600 dark:from-green-400 dark:to-green-500 text-white shadow-lg transform group-hover:scale-110 transition-transform duration-300">
                  <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              </div>
              <div className="ml-5">
                <h4 className="font-bold text-gray-900 dark:text-gray-100 mb-2">Production Planning</h4>
                <p className="text-gray-600 dark:text-gray-400">Plan and track production with material requirement calculations and forecasting</p>
              </div>
            </div>
            
            <div className="flex items-start group">
              <div className="flex-shrink-0">
                <div className="flex items-center justify-center h-14 w-14 rounded-xl bg-gradient-to-br from-purple-500 to-purple-600 dark:from-purple-400 dark:to-purple-500 text-white shadow-lg transform group-hover:scale-110 transition-transform duration-300">
                  <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              </div>
              <div className="ml-5">
                <h4 className="font-bold text-gray-900 dark:text-gray-100 mb-2">Advanced Analytics</h4>
                <p className="text-gray-600 dark:text-gray-400">Generate comprehensive reports and ROI analysis for marketing campaigns</p>
              </div>
            </div>
            
            <div className="flex items-start group">
              <div className="flex-shrink-0">
                <div className="flex items-center justify-center h-14 w-14 rounded-xl bg-gradient-to-br from-orange-500 to-orange-600 dark:from-orange-400 dark:to-orange-500 text-white shadow-lg transform group-hover:scale-110 transition-transform duration-300">
                  <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              </div>
              <div className="ml-5">
                <h4 className="font-bold text-gray-900 dark:text-gray-100 mb-2">Multi-channel Sales</h4>
                <p className="text-gray-600 dark:text-gray-400">Manage sales across multiple panels and channels efficiently with unified dashboard</p>
              </div>
            </div>
          </div>
        </div>

        {/* Stats Section */}
        <div className="mt-20 grid grid-cols-1 md:grid-cols-4 gap-6">
          <div className="text-center p-6 card hover:shadow-xl transition-shadow">
            <div className="text-4xl font-bold text-primary-600 dark:text-primary-400 mb-2">19+</div>
            <div className="text-gray-600 dark:text-gray-400 font-medium">Business Reports</div>
          </div>
          <div className="text-center p-6 card hover:shadow-xl transition-shadow">
            <div className="text-4xl font-bold text-green-600 dark:text-green-400 mb-2">100%</div>
            <div className="text-gray-600 dark:text-gray-400 font-medium">Real-time Updates</div>
          </div>
          <div className="text-center p-6 card hover:shadow-xl transition-shadow">
            <div className="text-4xl font-bold text-purple-600 dark:text-purple-400 mb-2">3</div>
            <div className="text-gray-600 dark:text-gray-400 font-medium">Core Modules</div>
          </div>
          <div className="text-center p-6 card hover:shadow-xl transition-shadow">
            <div className="text-4xl font-bold text-orange-600 dark:text-orange-400 mb-2">24/7</div>
            <div className="text-gray-600 dark:text-gray-400 font-medium">System Availability</div>
          </div>
        </div>
      </main>

      <footer className="bg-gray-900 dark:bg-black text-white mt-24 border-t border-gray-800 dark:border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-8">
            <div>
              <h3 className="text-xl font-bold mb-4 bg-gradient-to-r from-primary-400 to-purple-400 bg-clip-text text-transparent">Anthrilo</h3>
              <p className="text-gray-400">Enterprise ERP for textile manufacturing excellence</p>
            </div>
            <div>
              <h4 className="font-semibold mb-4 text-gray-200">Quick Links</h4>
              <ul className="space-y-2">
                <li><Link href="/dashboard" className="text-gray-400 hover:text-primary-400 transition-colors">Dashboard</Link></li>
                <li><Link href="/dashboard/reports/reports-index" className="text-gray-400 hover:text-primary-400 transition-colors">Reports</Link></li>
                <li><Link href="/dashboard/garments/master" className="text-gray-400 hover:text-primary-400 transition-colors">Products</Link></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-4 text-gray-200">Modules</h4>
              <ul className="space-y-2">
                <li><Link href="/dashboard/raw-materials" className="text-gray-400 hover:text-primary-400 transition-colors">Raw Materials</Link></li>
                <li><Link href="/dashboard/garments" className="text-gray-400 hover:text-primary-400 transition-colors">Garments</Link></li>
                <li><Link href="/dashboard/financial" className="text-gray-400 hover:text-primary-400 transition-colors">Financial</Link></li>
              </ul>
            </div>
          </div>
          <div className="border-t border-gray-800 pt-8">
            <p className="text-center text-gray-500">
              © 2026 Anthrilo Management System. All rights reserved.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
