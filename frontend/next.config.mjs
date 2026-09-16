/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Lint runs separately (`npm run lint`) — don't block the production build on
  // cosmetic ESLint errors like unescaped apostrophes so start-all.bat works.
  eslint: { ignoreDuringBuilds: true },
  allowedDevOrigins: [
    "research-student-management-system.fusionpractices.com",
  ],
  // Proxy API calls to the FastAPI backend during local dev so the browser
  // talks to same-origin /api/v1 (arch §14.1). Backend runs on :8000.
  async rewrites() {
    const backend = process.env.BACKEND_ORIGIN || 'http://localhost:8000'
    return [
      { source: '/api/v1/:path*', destination: `${backend}/api/v1/:path*` },
      { source: '/health/:path*', destination: `${backend}/health/:path*` },
    ]
  },
  // Serve the HTML documents with no-store so a rebuilt bundle is always picked up on the next
  // load (the recurring "I still see the old version" problem). The content-hashed static chunks
  // under /_next/static keep their long immutable cache — they never change under a fixed hash.
  async headers() {
    return [
      {
        source: '/((?!_next/static|_next/image).*)',
        headers: [{ key: 'Cache-Control', value: 'no-store, must-revalidate' }],
      },
    ]
  },
}

export default nextConfig
