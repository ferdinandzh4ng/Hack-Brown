/** @type {import('next').NextConfig} */
// Production: JSON imports are bundled at build time. Mapbox uses canvas/WebGL (no image.domains).
// If host CSP is strict, allow script-src/connect-src/style-src/img-src for api.mapbox.com and *.mapbox.com.
const nextConfig = {
  reactStrictMode: true,
};

export default nextConfig;
