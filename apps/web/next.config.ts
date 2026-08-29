import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  typedRoutes: true,
  experimental: {
    taint: true,
    staleTimes: {
      dynamic: 30,
      static: 180,
    },
  },
  productionBrowserSourceMaps: false,
  images: {
    formats: ["image/avif", "image/webp"],
  },
}
export default nextConfig
