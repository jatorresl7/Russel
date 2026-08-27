/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.ts', './web/**/*.html'],
  theme: {
    extend: {
      colors: {
        primary:         'var(--color-primary)',
        'primary-hover': 'var(--color-primary-hover)',
      },
    },
  },
  plugins: [],
};
