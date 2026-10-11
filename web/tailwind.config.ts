import type { Config } from "tailwindcss";
import { palette } from "./scripts/tokens.mjs";

// Colours come from design/tokens.json. Adding one here without adding it
// there is how two sources of truth start.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: palette,
      // Keep keyboard focus immediate; Tailwind 4 also transitions outline-color.
      transitionProperty: {
        colors: "color, background-color, border-color, text-decoration-color, fill, stroke",
      },
      fontFamily: {
        // A glyph Source Sans 3 lacks falls back to Helvetica.
        sans: ["'Source Sans 3'", "Helvetica", "Arial", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
