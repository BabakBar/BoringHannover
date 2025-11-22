/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  theme: {
    extend: {
      colors: {
        // Background colors
        bg: {
          primary: '#0a0a0a',
          secondary: '#141414',
          tertiary: '#1a1a1a',
        },
        // Text colors
        text: {
          primary: '#e5e5e5',
          secondary: '#888888',
          muted: '#555555',
        },
        // Accent (Nothing red)
        accent: {
          DEFAULT: '#ff3b3b',
          hover: '#ff5555',
          dim: 'rgba(255, 59, 59, 0.13)',
        },
        // Border
        border: '#2a2a2a',
      },
      fontFamily: {
        display: ['"Space Mono"', '"SF Mono"', 'monospace'],
        body: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
      },
      fontSize: {
        'xs': ['0.75rem', { lineHeight: '1rem' }],      // 12px
        'sm': ['0.875rem', { lineHeight: '1.25rem' }],  // 14px
        'base': ['1rem', { lineHeight: '1.5rem' }],     // 16px
        'lg': ['1.125rem', { lineHeight: '1.75rem' }],  // 18px
        'xl': ['1.5rem', { lineHeight: '2rem' }],       // 24px
        '2xl': ['2rem', { lineHeight: '2.5rem' }],      // 32px
      },
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
      },
      maxWidth: {
        'mobile': '480px',
      },
      letterSpacing: {
        'dot': '0.1em',
      },
    },
  },
  plugins: [],
};
