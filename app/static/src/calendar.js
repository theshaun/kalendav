// KalenDAV calendar entry. Wave 2 / Wave 5.
//
// Configuration lives in the calendar.html template so server-side vars
// (writable_calendar_ids, etc.) are in scope. This module provides the
// bundler-aware loader for FullCalendar + rrule, imports the FullCalendar
// Linear theme (calendar.css), and exposes initCalendar() used by Wave 5's
// calendar.html.

import { Calendar } from '@fullcalendar/core';
import dayGridPlugin from '@fullcalendar/daygrid';
import timeGridPlugin from '@fullcalendar/timegrid';
import interactionPlugin from '@fullcalendar/interaction';
import rrulePlugin from '@fullcalendar/rrule';
import { RRuleSet, rrulestr } from 'rrule';

import './calendar.css';

const PLUGINS = [dayGridPlugin, timeGridPlugin, interactionPlugin, rrulePlugin];

// Expose rrule types so the template can build recurrence rules without a
// second import path. Calendar config authored in the template references
// these via window.calendar RRULE helpers if needed.
window.RRuleSet = RRuleSet;
window.rrulestr = rrulestr;

/**
 * Build a FullCalendar instance and attach it to window.calendar so the
 * global refreshCalendar() stub in main.js can call refetchEvents().
 *
 * @param {string} elementId - DOM element id to mount into.
 * @param {Record<string, unknown>} config - FullCalendar options merged on top of plugins.
 * @returns {import('@fullcalendar/core').Calendar}
 */
export function initCalendar(elementId, config = {}) {
  const el = document.getElementById(elementId);
  if (!el) {
    throw new Error(`initCalendar: element "#${elementId}" not found`);
  }

  const calendar = new Calendar(el, {
    plugins: PLUGINS,
    ...config,
  });

  // refreshCalendar() (main.js) reads window.calendar.refetchEvents().
  window.calendar = calendar;
  calendar.render();
  return calendar;
}

// Side-effect assignment defeats Rollup tree-shaking. calendar.html loads
// this chunk via an inline ES-module `import` from a hashed URL, which the
// static analyzer cannot see — without this anchor, the chunk is reduced to
// just the rrule globals (94 bytes) and initCalendar() is dropped.
window.initCalendar = initCalendar;
