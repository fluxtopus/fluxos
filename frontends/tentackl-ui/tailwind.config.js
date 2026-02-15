/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-share-tech)', 'sans-serif'],
        mono: ['var(--font-share-tech-mono)', 'monospace'],
        display: ['var(--font-share-tech)', 'sans-serif'],
      },
    },
  },
  plugins: [],
}