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
          bg: "#08090a",         // Deep carbon obsidian
          surface: "#0f1113",    // Refined slate surface
          card: "#16181b",       // Dark charcoal base
          border: "#202328",     // Premium low-contrast border
          accent: "#ffffff",     // Muted gold/bronze (signals competence)
          text: "#f3f4f6",       // Clean soft white
          muted: "#8e95a2",      // Warm muted silver
        }
      },
      fontFamily: {
        sans: ["Outfit", "Inter", "sans-serif"],
      }
    },
  },
  plugins: [],
}
