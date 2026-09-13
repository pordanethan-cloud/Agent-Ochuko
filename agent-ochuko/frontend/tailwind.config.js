/** @type {import('tailwindcss').Config} */
import plugin from 'tailwindcss/plugin'

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    screens: {
      xs: '400px',
      sm: '640px',
      md: '768px',
      lg: '1024px',
      xl: '1280px',
      '2xl': '1536px',
    },
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
          ok: "#a9c1a5",         // Muted sage — success / live (semantic only)
          err: "#dba49a",        // Muted terracotta — failure / attention (semantic only)
        }
      },
      fontFamily: {
        sans: ["Outfit", "Inter", "sans-serif"],
        serif: ["'Source Serif 4'", "Charter", "Georgia", "Cambria", "serif"],
        mono: ["'JetBrains Mono'", "Fira Code", "monospace"],
      }
    },
  },
  plugins: [
    // ── `touch:` variant — applies on coarse-pointer (touchscreen) devices ──
    // Registered AFTER core variants, so `touch:h-11` wins over `sm:h-7.5`.
    // This keeps the desktop look pixel-identical (pointer: fine) while phones
    // in LANDSCAPE (width ≥ 640px) still get 44px touch targets.
    plugin(({ addVariant }) => {
      addVariant('touch', '@media (pointer: coarse)')
    }),
  ],
}
