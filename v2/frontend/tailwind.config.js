/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          base: "var(--color-paper)",
          raised: "var(--color-paper-2)",
          elevated: "var(--color-paper-3)",
          hover: "var(--color-paper-4)",
        },
        text: {
          primary: "var(--color-ink)",
          secondary: "var(--color-ink-2)",
          muted: "var(--color-muted)",
          faint: "var(--color-faint)",
        },
        border: {
          DEFAULT: "var(--color-rule)",
          strong: "var(--color-rule-2)",
        },
        accent: {
          DEFAULT: "var(--color-accent)",
          hover: "var(--color-accent-hover)",
          soft: "var(--color-accent-soft)",
          ink: "var(--color-accent-ink)",
        },
        status: {
          ok: "var(--color-ok)",
          danger: "var(--color-danger)",
          warn: "var(--color-warn)",
        },
        primary: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          800: '#075985',
          900: '#0c4a6e',
        }
      },
      fontFamily: {
        display: ['var(--font-display)'],
        body: ['var(--font-body)'],
        mono: ['var(--font-mono)'],
      },
      boxShadow: {
        'elev-1': 'var(--elev-1)',
        'elev-2': 'var(--elev-2)',
        'elev-3': 'var(--elev-3)',
        'elev-4': 'var(--elev-4)',
      },
      borderRadius: {
        'input': 'var(--radius-input)',
        'card': 'var(--radius-card)',
        'modal': 'var(--radius-modal)',
        'pill': 'var(--radius-pill)',
      },
      zIndex: {
        'modal': 'var(--z-modal)',
        'palette': 'var(--z-palette)',
        'toast': 'var(--z-toast)',
      }
    },
  },
  plugins: [],
}
