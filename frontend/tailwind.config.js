/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        eoc: {
          bg: '#0b1220',
          panel: '#111a2e',
          border: '#1e2a45',
          accent: '#38bdf8',
          critical: '#ef4444',
          high: '#f97316',
          moderate: '#eab308',
          low: '#22c55e',
        },
      },
    },
  },
  plugins: [],
}