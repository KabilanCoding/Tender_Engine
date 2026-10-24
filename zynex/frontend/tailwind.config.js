/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class', // light and dark; the toggle is in the header
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-ui)'],
        heading: ['var(--font-heading)'],
        mono: ['var(--font-mono)'],
      },
      // quieter depth: a hairline edge, and a real shadow only for things that float
      boxShadow: {
        sm: '0 1px 2px rgb(var(--shadow-rgb) / 0.06)',
        DEFAULT: '0 1px 3px rgb(var(--shadow-rgb) / 0.08), 0 1px 2px rgb(var(--shadow-rgb) / 0.05)',
        md: '0 2px 4px rgb(var(--shadow-rgb) / 0.05), 0 8px 20px -6px rgb(var(--shadow-rgb) / 0.14)',
        lg: '0 2px 4px rgb(var(--shadow-rgb) / 0.05), 0 16px 32px -10px rgb(var(--shadow-rgb) / 0.20)',
        xl: '0 2px 4px rgb(var(--shadow-rgb) / 0.06), 0 24px 48px -14px rgb(var(--shadow-rgb) / 0.26)',
        '2xl': '0 2px 4px rgb(var(--shadow-rgb) / 0.06), 0 32px 64px -16px rgb(var(--shadow-rgb) / 0.32)',
      },
      // animations used by the tender screens
      animation: {
        'shimmer': 'shimmer 2.5s infinite linear',
        'float': 'float 3.5s ease-in-out infinite',
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
        'gradient-x': 'gradientX 4s ease infinite',
        'fade-up': 'fadeUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'spin-slow': 'spin 8s linear infinite',
      },
      keyframes: {
        shimmer: { '0%': { transform: 'translateX(-100%)' }, '100%': { transform: 'translateX(100%)' } },
        float: { '0%, 100%': { transform: 'translateY(0px)' }, '50%': { transform: 'translateY(-6px)' } },
        pulseGlow: {
          '0%, 100%': { opacity: '0.8', boxShadow: '0 0 15px rgba(1, 75, 170, 0.3)' },
          '50%': { opacity: '1', boxShadow: '0 0 30px rgba(1, 75, 170, 0.6), 0 0 0 3px rgba(1, 75, 170, 0.2)' },
        },
        gradientX: {
          '0%, 100%': { 'background-size': '200% 200%', 'background-position': 'left center' },
          '50%': { 'background-size': '200% 200%', 'background-position': 'right center' },
        },
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(16px) scale(0.98)' },
          '100%': { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
      },
      colors: {
        // one cool-slate grey family (tinted toward the brand blue) for every screen
        gray: {
          50: 'rgb(var(--g-50) / <alpha-value>)',
          100: 'rgb(var(--g-100) / <alpha-value>)',
          200: 'rgb(var(--g-200) / <alpha-value>)',
          300: 'rgb(var(--g-300) / <alpha-value>)',
          400: 'rgb(var(--g-400) / <alpha-value>)',
          500: 'rgb(var(--g-500) / <alpha-value>)',
          600: 'rgb(var(--g-600) / <alpha-value>)',
          700: 'rgb(var(--g-700) / <alpha-value>)',
          800: 'rgb(var(--g-800) / <alpha-value>)',
          900: 'rgb(var(--g-900) / <alpha-value>)',
          950: 'rgb(var(--g-950) / <alpha-value>)',
        },
        slate: {
          50: 'rgb(var(--g-50) / <alpha-value>)',
          100: 'rgb(var(--g-100) / <alpha-value>)',
          200: 'rgb(var(--g-200) / <alpha-value>)',
          300: 'rgb(var(--g-300) / <alpha-value>)',
          400: 'rgb(var(--g-400) / <alpha-value>)',
          500: 'rgb(var(--g-500) / <alpha-value>)',
          600: 'rgb(var(--g-600) / <alpha-value>)',
          700: 'rgb(var(--g-700) / <alpha-value>)',
          800: 'rgb(var(--g-800) / <alpha-value>)',
          900: 'rgb(var(--g-900) / <alpha-value>)',
          950: 'rgb(var(--g-950) / <alpha-value>)',
        },
        // the tender screens were written with Tailwind's indigo, and older screens with blue; both follow the royal blue scale
        indigo: {
          50: '#EEF3FB', 100: '#DDE7F8', 200: '#BBCFF0', 300: '#8EAEE4', 400: '#5584D3',
          500: '#2462C6', 600: '#014BAA', 700: '#013D8C', 800: '#02316F', 900: '#032553', 950: '#021736',
        },
        blue: {
          50: '#EEF3FB', 100: '#DDE7F8', 200: '#BBCFF0', 300: '#8EAEE4', 400: '#5584D3',
          500: '#2462C6', 600: '#014BAA', 700: '#013D8C', 800: '#02316F', 900: '#032553', 950: '#021736',
        },
        // ZYNEX brand palette: royal blue #014BAA on light cream #F8F3F0
        brand: {
          50: '#EEF3FB', 100: '#DDE7F8', 500: '#2462C6', 600: '#014BAA', 700: '#013D8C', 900: '#032553',
          blue:        '#014BAA',
          'blue-dark': '#013D8C',
          'blue-dim':  '#02316F',
          'blue-deep': '#032553',
          green:       '#1F7A56',
          'green-dark':'#186446',
          cream:       '#F8F3F0',
        },
        // App shell backgrounds
        shell: {
          header: '#0A2150',
          nav:    '#03255A',
          side:   '#0A2150',
          active: '#014BAA',
          hover:  '#023B85',
        },
      },
    },
  },
  plugins: [],
}
