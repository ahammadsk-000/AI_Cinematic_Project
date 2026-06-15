/** @type {import('next').NextConfig} */
// Deployed on Vercel (root dir: apps/web); proxies /api and /media to the Render backend.
const nextConfig = {
  reactStrictMode: true,
  // Allow loading generated artifacts (images/video thumbnails) served by the API.
  images: {
    remotePatterns: [
      { protocol: "http", hostname: "localhost" },
      { protocol: "https", hostname: "**" },
    ],
  },
  // Proxy /api -> backend in dev so the browser hits a same-origin path (no CORS hassle).
  async rewrites() {
    const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${api}/api/:path*` },
      // generated videos/images served by the backend's /media mount
      { source: "/media/:path*", destination: `${api}/media/:path*` },
    ];
  },
};

export default nextConfig;
