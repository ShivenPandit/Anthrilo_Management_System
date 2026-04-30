/** @type {import('next').NextConfig} */
const normalizedApiUrl = (process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000')
  .replace(/\/+$/, '')
  .replace(/\/api\/v1$/, '')

const nextConfig = {
  reactStrictMode: true,
  output: 'standalone', // Required for Docker multi-stage build
  experimental: {
    optimizePackageImports: ['lucide-react', 'recharts', 'framer-motion'],
  },
  eslint: {
    // Keep linting available via `npm run lint`, but don't block container image builds.
    ignoreDuringBuilds: true,
  },
  env: {
    NEXT_PUBLIC_API_URL: normalizedApiUrl,
  },
}

module.exports = nextConfig
