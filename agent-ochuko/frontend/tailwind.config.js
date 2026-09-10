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
        // Warm charcoal theme — soft, layered, low-contrast (Verdent-style).
        // Never pure black/white: lifted base, softened text, hairline borders.
        brand: {
          bg: "#1a1a18",         // Warm charcoal base
          surface: "#212120",    // Panels / sidebar
          card: "#262624",       // Cards & elevated surfaces
          border: "#313130",     // Hairline low-contrast border
          accent: "#e8e6e3",     // Soft ivory primary
          text: "#e9e8e6",       // Softened off-white body text
          muted: "#a6a29c",      // Warm gray secondary
        }
      },
      fontFamily: {
        sans: ["Outfit", "Inter", "sans-serif"],
        serif: ["'Source Serif 4'", "Charter", "Georgia", "Cambria", "serif"],
        mono: ["'JetBrains Mono'", "Fira Code", "monospace"],
      }
    },
  },
  plugins: [],
}
