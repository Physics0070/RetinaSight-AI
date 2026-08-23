/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // Tailwind is used as a utility layer only. All colour, elevation and
      // radius values resolve to the RetinaSight design tokens in
      // src/design-system/tokens/tokens.css — never raw hex in components.
      colors: {
        surface: "var(--rs-surface)",
        "surface-raised": "var(--rs-surface-raised)",
        "surface-sunken": "var(--rs-surface-sunken)",
        ink: "var(--rs-ink)",
        "ink-muted": "var(--rs-ink-muted)",
        "ink-subtle": "var(--rs-ink-subtle)",
        line: "var(--rs-line)",
        accent: "var(--rs-accent)",
        "accent-ink": "var(--rs-accent-ink)",
        retina: "var(--rs-retina)",
        "risk-low": "var(--rs-risk-low)",
        "risk-moderate": "var(--rs-risk-moderate)",
        "risk-high": "var(--rs-risk-high)",
        "risk-urgent": "var(--rs-risk-urgent)",
      },
      borderRadius: {
        xs: "var(--rs-radius-xs)",
        sm: "var(--rs-radius-sm)",
        md: "var(--rs-radius-md)",
        lg: "var(--rs-radius-lg)",
        xl: "var(--rs-radius-xl)",
      },
      fontFamily: {
        sans: "var(--rs-font-sans)",
        mono: "var(--rs-font-mono)",
      },
      boxShadow: {
        raised: "var(--rs-shadow-raised)",
        sunken: "var(--rs-shadow-sunken)",
        panel: "var(--rs-shadow-panel)",
        focus: "var(--rs-shadow-focus)",
      },
    },
  },
  plugins: [],
};
