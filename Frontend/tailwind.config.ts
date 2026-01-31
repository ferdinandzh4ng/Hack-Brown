import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        'visa-blue': '#003399',
        'visa-gold': '#F7B600',
        'visa-blue-dark': '#002266',
        'slate-trust': {
          50: '#f8fafc',
          100: '#f1f5f9',
          150: '#e8eef4',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          800: '#1e293b',
          900: '#0f172a',
        },
      },
      fontFamily: {
        sans: ['var(--font-geist-sans)', 'system-ui', 'sans-serif'],
        display: ['var(--font-geist-sans)', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'visa-card': '0 4px 24px -4px rgba(0, 51, 153, 0.12), 0 2px 8px -2px rgba(0, 0, 0, 0.06)',
        'visa-premium': '0 8px 32px -8px rgba(0, 51, 153, 0.18), 0 4px 12px -4px rgba(0, 0, 0, 0.08)',
      },
    },
  },
  plugins: [],
};

export default config;
