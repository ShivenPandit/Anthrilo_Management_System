import Link from 'next/link';

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <nav className="bg-white shadow-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center">
              <h1 className="text-2xl font-bold text-primary-600">Anthrilo</h1>
            </div>
            <div className="flex items-center space-x-4">
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
        <div className="text-center mb-12">
          <h1 className="text-5xl font-bold text-gray-900 mb-4">
            Anthrilo Management System
          </h1>
          <p className="text-xl text-gray-600 max-w-3xl mx-auto">
            Enterprise-grade ERP solution for textile manufacturing and garment production management
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mt-12">
          {/* Module I */}
          <div className="card hover:shadow-xl transition-shadow">
            <div className="text-primary-600 mb-4">
              <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            <h3 className="mb-2">Raw Material & Processing</h3>
            <p className="text-gray-600">
              Manage yarn, fabric, and processing workflows including knitting, dyeing, finishing, and printing
            </p>
            <Link href="/dashboard/raw-materials" className="text-primary-600 hover:text-primary-700 mt-4 inline-block">
              Learn more →
            </Link>
          </div>

          {/* Module II */}
          <div className="card hover:shadow-xl transition-shadow">
            <div className="text-primary-600 mb-4">
              <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
              </svg>
            </div>
            <h3 className="mb-2">Garment & Sales</h3>
            <p className="text-gray-600">
              Track inventory, production planning, sales transactions, and panel-wise performance
            </p>
            <Link href="/dashboard/garments" className="text-primary-600 hover:text-primary-700 mt-4 inline-block">
              Learn more →
            </Link>
          </div>

          {/* Module III */}
          <div className="card hover:shadow-xl transition-shadow">
            <div className="text-primary-600 mb-4">
              <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <h3 className="mb-2">Financial & Marketing</h3>
            <p className="text-gray-600">
              Manage discounts, track paid advertising ROI, and generate comprehensive financial reports
            </p>
            <Link href="/dashboard/financial" className="text-primary-600 hover:text-primary-700 mt-4 inline-block">
              Learn more →
            </Link>
          </div>
        </div>

        <div className="mt-16 bg-white rounded-lg shadow-md p-8">
          <h2 className="mb-6 text-center">Key Features</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <div className="flex items-center justify-center h-12 w-12 rounded-md bg-primary-500 text-white">
                  ✓
                </div>
              </div>
              <div className="ml-4">
                <h4 className="font-semibold">Real-time Inventory Tracking</h4>
                <p className="text-gray-600">Monitor stock levels across all warehouses in real-time</p>
              </div>
            </div>
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <div className="flex items-center justify-center h-12 w-12 rounded-md bg-primary-500 text-white">
                  ✓
                </div>
              </div>
              <div className="ml-4">
                <h4 className="font-semibold">Production Planning</h4>
                <p className="text-gray-600">Plan and track production with material requirement calculations</p>
              </div>
            </div>
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <div className="flex items-center justify-center h-12 w-12 rounded-md bg-primary-500 text-white">
                  ✓
                </div>
              </div>
              <div className="ml-4">
                <h4 className="font-semibold">Advanced Analytics</h4>
                <p className="text-gray-600">Generate comprehensive reports and ROI analysis for marketing</p>
              </div>
            </div>
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <div className="flex items-center justify-center h-12 w-12 rounded-md bg-primary-500 text-white">
                  ✓
                </div>
              </div>
              <div className="ml-4">
                <h4 className="font-semibold">Multi-channel Sales</h4>
                <p className="text-gray-600">Manage sales across multiple panels and channels efficiently</p>
              </div>
            </div>
          </div>
        </div>
      </main>

      <footer className="bg-gray-800 text-white mt-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <p className="text-center text-gray-400">
            © 2026 Anthrilo Management System. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
