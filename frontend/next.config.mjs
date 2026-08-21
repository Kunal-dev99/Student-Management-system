/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Proxy API calls to the FastAPI backend during local dev so the browser
  // talks to same-origin /api/v1 (arch §14.1). Backend runs on :8000.
  async rewrites() {
    const backend = process.env.BACKEND_ORIGIN || 'http://localhost:8000'
    return [
      { source: '/api/v1/:path*', destination: `${backend}/api/v1/:path*` },
      { source: '/health/:path*', destination: `${backend}/health/:path*` },
    ]
  },
}

export default nextConfig
