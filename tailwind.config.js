// KalenDAV Tailwind v3.4 config. Mirrors DESIGN.md section 11 one to one.
// Color, shadow, font, and layout utilities reference CSS variables; those
// variables flip between :root (light) and .dark (dark) in the base CSS layer
// (Wave 2). Static tokens (spacing, radii, durations, easings, z-index, type
// scale) carry literal values because Tailwind's internals need real numbers.

import formsPlugin from '@tailwindcss/forms';
import typographyPlugin from '@tailwindcss/typography';

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    './app/**/*.{html,js}',
    './app/static/src/**/*.{css,js}',
  ],
  theme: {
    extend: {
      screens: {
        sm: '640px',
        md: '768px',
        lg: '1024px',
        xl: '1280px',
        '2xl': '1536px',
      },
      colors: {
        // Background surfaces
        canvas: 'var(--color-bg-canvas)',
        surface: 'var(--color-bg-surface)',
        elevated: 'var(--color-bg-elevated)',
        hover: 'var(--color-bg-hover)',
        sidebar: 'var(--color-bg-sidebar)',
        topbar: 'var(--color-bg-topbar)',
        overlay: 'var(--color-bg-overlay)',

        // Text
        text: {
          primary: 'var(--color-text-primary)',
          secondary: 'var(--color-text-secondary)',
          tertiary: 'var(--color-text-tertiary)',
          quaternary: 'var(--color-text-quaternary)',
          inverse: 'var(--color-text-inverse)',
        },

        // Borders
        border: {
          default: 'var(--color-border-default)',
          subtle: 'var(--color-border-subtle)',
          strong: 'var(--color-border-strong)',
          focus: 'var(--color-border-focus)',
          input: 'var(--color-border-input)',
        },

        // Locked brand accent ramp (Tailwind blue)
        accent: {
          50: 'var(--color-accent-50)',
          100: 'var(--color-accent-100)',
          200: 'var(--color-accent-200)',
          300: 'var(--color-accent-300)',
          400: 'var(--color-accent-400)',
          500: 'var(--color-accent-500)',
          600: 'var(--color-accent-600)',
          700: 'var(--color-accent-700)',
          800: 'var(--color-accent-800)',
          900: 'var(--color-accent-900)',
          950: 'var(--color-accent-950)',
        },

        // Semantic
        success: {
          DEFAULT: 'var(--color-success)',
          bg: 'var(--color-success-bg)',
        },
        warning: {
          DEFAULT: 'var(--color-warning)',
          bg: 'var(--color-warning-bg)',
        },
        danger: {
          DEFAULT: 'var(--color-danger)',
          bg: 'var(--color-danger-bg)',
        },
        info: 'var(--color-info)',

        // Calendar event palette
        calendar: {
          accent: 'var(--color-cal-accent)',
          emerald: 'var(--color-cal-emerald)',
          amber: 'var(--color-cal-amber)',
          rose: 'var(--color-cal-rose)',
          violet: 'var(--color-cal-violet)',
          cyan: 'var(--color-cal-cyan)',
        },

        // Permission badge tokens
        perm: {
          admin: 'var(--color-perm-admin)',
          'admin-permission': 'var(--color-perm-admin-permission)',
          write: 'var(--color-perm-write)',
          read: 'var(--color-perm-read)',
        },
      },
      backgroundImage: {
        // Auth backdrop. Wave 2's base CSS defines --color-bg-auth on :root and .dark.
        'auth-gradient': 'var(--color-bg-auth)',
        // Event block gradient (DESIGN.md section 6); --fc-event-bg-color is set inline per calendar
        'event-block': 'linear-gradient(135deg, color-mix(in srgb, var(--fc-event-bg-color) 92%, #ffffff 8%), var(--fc-event-bg-color))',
      },
      fontFamily: {
        sans: 'var(--font-sans)',
        mono: 'var(--font-mono)',
      },
      fontSize: {
        display: ['48px', { lineHeight: '1.1', fontWeight: '600', letterSpacing: '-0.025em' }],
        h1: ['36px', { lineHeight: '1.2', fontWeight: '600', letterSpacing: '-0.02em' }],
        h2: ['28px', { lineHeight: '1.3', fontWeight: '600', letterSpacing: '-0.015em' }],
        h3: ['20px', { lineHeight: '1.4', fontWeight: '600', letterSpacing: '-0.01em' }],
        'body-lg': ['18px', { lineHeight: '1.5', fontWeight: '400', letterSpacing: '0' }],
        body: ['15px', { lineHeight: '1.6', fontWeight: '400', letterSpacing: '0' }],
        'body-sm': ['14px', { lineHeight: '1.5', fontWeight: '400', letterSpacing: '0' }],
        caption: ['13px', { lineHeight: '1.4', fontWeight: '500', letterSpacing: '0' }],
        label: ['12px', { lineHeight: '1.4', fontWeight: '500', letterSpacing: '0' }],
        overline: ['11px', { lineHeight: '1.4', fontWeight: '600', letterSpacing: '0.08em' }],
        mono: ['13px', { lineHeight: '1.5', fontWeight: '400', letterSpacing: '0' }],
      },
      spacing: {
        0: '0',
        1: '4px',
        2: '8px',
        3: '12px',
        4: '16px',
        5: '20px',
        6: '24px',
        8: '32px',
        10: '40px',
        12: '48px',
        16: '64px',
        20: '80px',
      },
      padding: {
        'content-gutter': 'var(--content-gutter)',
        'content-gutter-mobile': 'var(--content-gutter-mobile)',
      },
      borderRadius: {
        sm: '4px',
        md: '6px',
        lg: '8px',
        xl: '12px',
        '2xl': '16px',
        full: '9999px',
      },
      boxShadow: {
        popover: 'var(--shadow-popover)',
        modal: 'var(--shadow-modal)',
        toast: 'var(--shadow-toast)',
        focus: 'var(--shadow-focus)',
      },
      transitionDuration: {
        instant: '75ms',
        fast: '150ms',
        base: '250ms',
        slow: '400ms',
      },
      transitionTimingFunction: {
        out: 'cubic-bezier(0.16, 1, 0.3, 1)',
        'in-out': 'cubic-bezier(0.65, 0, 0.35, 1)',
        spring: 'cubic-bezier(0.32, 0.72, 0, 1)',
        standard: 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
      zIndex: {
        base: '0',
        dropdown: '1000',
        sticky: '1100',
        sidebar: '1200',
        'modal-backdrop': '1300',
        modal: '1310',
        toast: '1400',
      },
      width: {
        sidebar: 'var(--sidebar-width)',
        'sidebar-collapsed': 'var(--sidebar-width-collapsed)',
        'sidebar-drawer': 'var(--sidebar-width-drawer)',
      },
      height: {
        topbar: 'var(--topbar-height)',
      },
      maxWidth: {
        content: 'var(--content-max-width)',
      },
      keyframes: {
        'modal-pop': {
          from: { transform: 'scale(0.96)', opacity: '0' },
          to: { transform: 'scale(1)', opacity: '1' },
        },
        'backdrop-fade': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'drawer-slide-in': {
          from: { transform: 'translateX(-100%)' },
          to: { transform: 'translateX(0)' },
        },
        'drawer-slide-out': {
          from: { transform: 'translateX(0)' },
          to: { transform: 'translateX(-100%)' },
        },
        'toast-slide-in': {
          from: { transform: 'translateY(16px)', opacity: '0' },
          to: { transform: 'translateY(0)', opacity: '1' },
        },
      },
      animation: {
        'modal-pop': 'modal-pop 250ms cubic-bezier(0.32, 0.72, 0, 1) both',
        'backdrop-fade': 'backdrop-fade 250ms cubic-bezier(0.32, 0.72, 0, 1) both',
        'drawer-slide-in': 'drawer-slide-in 250ms cubic-bezier(0.32, 0.72, 0, 1) both',
        'drawer-slide-out': 'drawer-slide-out 250ms cubic-bezier(0.32, 0.72, 0, 1) both',
        'toast-slide-in': 'toast-slide-in 250ms cubic-bezier(0.16, 1, 0.3, 1) both',
      },
    },
  },
  plugins: [
    formsPlugin,
    typographyPlugin,
  ],
};
