import type { NextConfig } from "next";

/**
 * The browser only talks to Next.js. `/api/*` and `/health` are rewritten to the FastAPI
 * backend, so the httpOnly `azentio_session` cookie is first-party and no CORS is involved.
 *
 * In production the App Platform ingress routes `/api` and `/health` to the backend before
 * they reach Next.js, so these rewrites never fire there. BACKEND_URL is read when the
 * server starts in development and at build time for `next build`.
 */
const backendUrl = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  poweredByHeader: false,
  // Keep the dev-only indicator clear of the sidebar footer.
  devIndicators: { position: "bottom-right" },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backendUrl}/api/:path*` },
      { source: "/health", destination: `${backendUrl}/health` },
    ];
  },
};

export default nextConfig;
