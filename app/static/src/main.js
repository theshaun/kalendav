// KalenDAV global entry. Wave 2.
//
// Responsibilities (preserved from the legacy CDN-loaded code + extended):
//   1. Load HTMX onto window for the existing Jinja2 templates.
//   2. Render Lucide icons after initial paint and after every HTMX swap.
//   3. Wire the dark-mode toggle (localStorage 'darkMode' key, falls back to
//      prefers-color-scheme). Dispatches 'dark-mode:changed' so listeners
//      such as charts or code highlighting can react.
//   4. Provide closeModal() and refreshCalendar() globals so the existing
//      calendar.html template contract keeps working until Wave 4 rewrites
//      it to call initCalendar() instead.

import 'htmx.org';
import { createIcons, icons } from 'lucide';

// Tailwind + design tokens. Imported here so Vite emits a single CSS bundle
// (cssCodeSplit: false in vite.config.js) keyed off the main entry.
import './main.css';

// ---------------------------------------------------------------------------
// Icons — initial render and re-render after every HTMX swap.
// ---------------------------------------------------------------------------

function renderIcons() {
  // Lucide ≥ 0.460 requires the icons map to be passed explicitly; the no-arg
  // form throws and renders nothing.
  createIcons({ icons });
}

document.addEventListener('DOMContentLoaded', renderIcons);
document.body.addEventListener('htmx:afterSwap', renderIcons);

// ---------------------------------------------------------------------------
// Dark mode toggle. The FOUC buster in <head> sets the initial class before
// paint; this handles subsequent toggles and persistence.
// ---------------------------------------------------------------------------

function isDarkFromStorage() {
  const stored = localStorage.getItem('darkMode');
  if (stored === 'true') return true;
  if (stored === 'false') return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function applyDarkMode(isDark) {
  document.documentElement.classList.toggle('dark', isDark);
  localStorage.setItem('darkMode', String(isDark));
  document.dispatchEvent(
    new CustomEvent('dark-mode:changed', { detail: { dark: isDark } })
  );
}

function wireDarkModeToggle() {
  const toggle = document.getElementById('darkModeToggle');
  if (!toggle) return;
  toggle.addEventListener('click', () => {
    const isDark = !document.documentElement.classList.contains('dark');
    applyDarkMode(isDark);
  });
}

document.addEventListener('DOMContentLoaded', wireDarkModeToggle);

// ---------------------------------------------------------------------------
// Globals consumed by the current calendar.html template until Wave 4
// replaces it. Wave 4's calendar.html will call initCalendar() from
// calendar.js and set window.calendar itself; these stubs become no-ops.
// ---------------------------------------------------------------------------

/**
 * Empty the modal container. Preserved from the existing template contract.
 */
function closeModal() {
  const container = document.getElementById('modal-container');
  if (container) container.innerHTML = '';
}

/**
 * Ask the mounted calendar to refetch events. No-op until calendar.js
 * attaches window.calendar. After Wave 4, calendar.js owns window.calendar
 * and this becomes a thin pass-through.
 */
function refreshCalendar() {
  if (typeof window !== 'undefined' && window.calendar) {
    window.calendar.refetchEvents();
  }
}

window.closeModal = closeModal;
window.refreshCalendar = refreshCalendar;

export { closeModal, refreshCalendar };
