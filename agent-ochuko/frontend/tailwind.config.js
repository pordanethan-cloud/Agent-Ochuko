/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // High-altitude warm dark theme colors
        brand: {
          bg: "#0b0c0e",         // Grounded deep carbon background
          surface: "#141619",    // Warm slate surface
          card: "#1b1d22",       // Warm charcoal card base
          border: "#282b31",     // Clean muted border
          accent: "#c084fc",     // Muted lavender accent (calm, warm)
          text: "#f3f4f6",       // Crisp off-white primary text
          muted: "#9ca3af",      // Muted slate secondary text
        }
      },
      fontFamily: {
        sans: ["Outfit", "Inter", "sans-serif"],
      }
    },
  },
  plugins: [],
}
