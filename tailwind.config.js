/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    "./templates/**/*.html",
    "./static/js/**/*.js"
  ],
  theme: {
    extend: {
      colors: {
        zinc: {
          850: '#202023',
          900: '#18181b',
        }
      }
    },
  },
  plugins: [],
}
