/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        cv: {
          black: 'rgb(var(--cv-black) / <alpha-value>)',
          deep: 'rgb(var(--cv-deep) / <alpha-value>)',
          navy: 'rgb(var(--cv-navy) / <alpha-value>)',
          accent: 'rgb(var(--cv-accent) / <alpha-value>)',
          electric: 'rgb(var(--cv-electric) / <alpha-value>)',
          'accent-dim': 'rgb(var(--cv-accent-dim) / <alpha-value>)',
          surface: 'rgb(var(--cv-surface) / <alpha-value>)',
          border: 'rgb(var(--cv-border) / <alpha-value>)',
          muted: 'rgb(var(--cv-muted) / <alpha-value>)',
          text: 'rgb(var(--cv-text) / <alpha-value>)',
          'cyan-glow': 'rgb(var(--cv-metric-cameras) / <alpha-value>)',
        },
        'metric-cameras': 'rgb(var(--cv-metric-cameras) / <alpha-value>)',
        'metric-alerts': 'rgb(var(--cv-metric-alerts) / <alpha-value>)',
        'metric-events': 'rgb(var(--cv-metric-events) / <alpha-value>)',
        'metric-rules': 'rgb(var(--cv-metric-rules) / <alpha-value>)',
        'severity-low': 'rgb(var(--cv-severity-low) / <alpha-value>)',
        'severity-medium': 'rgb(var(--cv-severity-medium) / <alpha-value>)',
        'severity-high': 'rgb(var(--cv-severity-high) / <alpha-value>)',
        'severity-critical': 'rgb(var(--cv-severity-critical) / <alpha-value>)',
      },
      fontFamily: {
        display: ['"Plus Jakarta Sans"', 'Inter', 'system-ui', 'sans-serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        card: 'var(--cv-shadow-card)',
        soft: 'var(--cv-shadow-soft)',
        glow: 'var(--cv-shadow-glow)',
        'metric-cameras/20': '0 4px 20px rgb(var(--cv-metric-cameras) / 0.2)',
        'metric-alerts/20': '0 4px 20px rgb(var(--cv-metric-alerts) / 0.2)',
        'metric-events/20': '0 4px 20px rgb(var(--cv-metric-events) / 0.2)',
        'metric-rules/20': '0 4px 20px rgb(var(--cv-metric-rules) / 0.2)',
      },
      animation: {
        'fade-in': 'fadeIn 0.4s ease-out',
        'slide-in': 'slideIn 0.3s ease-out',
        'spin-slow': 'spin 8s linear infinite',
        'pulse-soft': 'pulseSoft 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        slideIn: {
          from: { opacity: '0', transform: 'translateX(-12px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        pulseSoft: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.65' },
        },
      },
    },
  },
  plugins: [],
};
