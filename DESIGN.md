# KalenDAV Design System

> Loaded rulesets: `frontend` skill with `design/README.md`, `design/design-system-architecture.md`, `design/linear.app.md` (Layer B brand ref), `design/minimalist-skill.md` (Layer A taste), and `perfection/README.md`. Linear's token structure is the source; the accent hue is swapped from indigo to Tailwind blue (`#3B82F6`) per locked brand decision, and Berkeley Mono is swapped for JetBrains Mono Variable.

Single source of truth for every visual decision in the KalenDAV redesign. The Tailwind v3.4 config written in the next wave mirrors this file one to one. No raw hex, no magic px, no orphan tokens downstream.

## 1. Atmosphere and Identity

A quiet operations console for calendars. Dense when scanned, spacious when read. Surfaces separate by luminance steps rather than hard borders, so depth is felt before it is seen. The brand accent (`#3B82F6`) appears only on interactive surfaces, never as decoration. Dark mode is the native medium; light mode is a polite mirror of it.

Signature: a glassy fixed sidebar whose background sits one luminance step above the canvas, with a near-invisible semi-transparent border on its inner edge. Everything else in the product reinforces that move.

Anti-slop commitments: no gradients on broad surfaces (only on event blocks and the auth backdrop), no `rounded-2xl` blanket, no drop shadows on dark surfaces (Linear's luminance-stacking rule), no emojis, no external CDN calls, no Bootstrap.

## 2. Foundations

### Color tokens (dark first, then light)

Surfaces use the **zinc** family. Slate's blue tint fights the blue accent. Neutral is too warm. Zinc is the cool gray Linear uses without naming it.

| Token | Dark value | Light value | Usage |
|---|---|---|---|
| `--color-bg-canvas` | `#09090b` | `#fafafa` | App background, deepest layer |
| `--color-bg-surface` | `#18181b` | `#ffffff` | Cards, panels, topbar |
| `--color-bg-elevated` | `#27272a` | `#f4f4f5` | Modals, dropdowns, popovers |
| `--color-bg-hover` | `rgba(255,255,255,0.04)` | `rgba(0,0,0,0.03)` | Row hover, button hover wash |
| `--color-bg-sidebar` | `rgba(24,24,27,0.72)` | `rgba(255,255,255,0.72)` | Glassy sidebar |
| `--color-bg-topbar` | `rgba(9,9,11,0.72)` | `rgba(250,250,250,0.72)` | Glassy topbar |
| `--color-bg-overlay` | `rgba(0,0,0,0.60)` | `rgba(15,15,20,0.50)` | Modal backdrop |
| `--color-bg-auth` | `radial-gradient(ellipse at top, #18181b 0%, #09090b 60%)` | `radial-gradient(ellipse at top, #ffffff 0%, #f4f4f5 60%)` | Login page backdrop |
| `--color-text-primary` | `#fafafa` | `#09090b` | Body, headlines |
| `--color-text-secondary` | `#a1a1aa` | `#52525b` | Captions, descriptions |
| `--color-text-tertiary` | `#71717a` | `#64646d` | Metadata, placeholders |
| `--color-text-quaternary` | `#52525b` | `#6e6e78` | Disabled labels |
| `--color-text-inverse` | `#09090b` | `#fafafa` | Text on accent fill |
| `--color-border-default` | `rgba(255,255,255,0.08)` | `rgba(0,0,0,0.10)` | Cards, inputs, dividers |
| `--color-border-subtle` | `rgba(255,255,255,0.05)` | `rgba(0,0,0,0.06)` | Soft separators |
| `--color-border-strong` | `rgba(255,255,255,0.14)` | `rgba(0,0,0,0.18)` | Focus-adjacent, emphasized |
| `--color-border-focus` | `#3B82F6` | `#3B82F6` | Visible focus ring |
| `--color-border-input` | `rgba(255,255,255,0.10)` | `rgba(0,0,0,0.12)` | Form controls at rest |

### Accent scale (locked brand hue, full Tailwind blue ramp)

| Token | Value | Usage |
|---|---|---|
| `--color-accent-50` | `#eff6ff` | Subtle washes, light mode accent tints |
| `--color-accent-100` | `#dbeafe` | Light mode accent backgrounds |
| `--color-accent-200` | `#bfdbfe` | Hover tint for light surfaces |
| `--color-accent-300` | `#93c5fd` | Dark-mode accent borders |
| `--color-accent-400` | `#60a5fa` | Dark-mode accent text on zinc (6.7:1 on `#18181b`) |
| `--color-accent-500` | `#3B82F6` | Brand hue. Focus ring, dark-mode accent fill. **Dark-mode override: `#2563eb`** — the brand hue reads 3.67:1 with white text (below WCAG AA 4.5:1); in dark mode, where `dark:bg-accent-500` is the primary button fill, the variable resolves to `#2563eb` (5.17:1) so white-on-accent buttons pass. Light mode keeps the brand hue. |
| `--color-accent-600` | `#2563eb` | Light-mode primary button fill (5.17:1 with white text) |
| `--color-accent-700` | `#1d4ed8` | Light-mode primary hover |
| `--color-accent-800` | `#1e40af` | Pressed state |
| `--color-accent-900` | `#1e3a8a` | Deep accent surfaces |
| `--color-accent-950` | `#172554` | Maximum contrast accent |

### Semantic tokens

| Token | Dark value | Light value | Usage |
|---|---|---|---|
| `--color-success` | `#22c55e` | `#15803d` | Confirmations, online status |
| `--color-success-bg` | `rgba(34,197,94,0.12)` | `#f0fdf4` | Inline success backgrounds |
| `--color-warning` | `#f59e0b` | `#b45309` | Cautions, sync errors |
| `--color-warning-bg` | `rgba(245,158,11,0.12)` | `#fffbeb` | Inline warning backgrounds |
| `--color-danger` | `#ef4444` | `#dc2626` | Destructive actions, validation errors |
| `--color-danger-bg` | `rgba(239,68,68,0.12)` | `#fef2f2` | Inline danger backgrounds |
| `--color-info` | `#3B82F6` | `#2563eb` | Informational toasts |

### Calendar palette (per-calendar event colors)

Six token colors plus the accent. Each event picks one; the calendar's settings page stores the index.

| Token | Value |
|---|---|
| `--color-cal-accent` | `#3B82F6` |
| `--color-cal-emerald` | `#10b981` |
| `--color-cal-amber` | `#f59e0b` |
| `--color-cal-rose` | `#f43f5e` |
| `--color-cal-violet` | `#8b5cf6` |
| `--color-cal-cyan` | `#06b6d4` |

### Permission badge tokens

| Token | Dark value | Light value | Usage |
|---|---|---|---|
| `--color-perm-admin` | `#f43f5e` | `#e11d48` | Admin role badge |
| `--color-perm-admin-permission` | `#f59e0b` | `#b45309` | Granted-admin badge |
| `--color-perm-write` | `#22c55e` | `#15803d` | Write permission badge |
| `--color-perm-read` | `#60a5fa` | `#2563eb` | Read permission badge |

### Type scale

| Token | Size / line-height | Weight | Tracking | Tailwind alias |
|---|---|---|---|---|
| `--text-display` | `48px / 1.1` | 600 | `-0.025em` | `text-5xl` |
| `--text-h1` | `36px / 1.2` | 600 | `-0.02em` | `text-4xl` |
| `--text-h2` | `28px / 1.3` | 600 | `-0.015em` | `text-3xl` |
| `--text-h3` | `20px / 1.4` | 600 | `-0.01em` | `text-xl` |
| `--text-body-lg` | `18px / 1.5` | 400 | `0` | `text-lg` |
| `--text-body` | `15px / 1.6` | 400 | `0` | `text-[15px]` (NOT `text-base`) |
| `--text-body-sm` | `14px / 1.5` | 400 | `0` | `text-sm` |
| `--text-caption` | `13px / 1.4` | 500 | `0` | `text-[13px]` |
| `--text-label` | `12px / 1.4` | 500 | `0` | `text-xs` |
| `--text-overline` | `11px / 1.4` | 600 | `0.08em` | `text-[11px]` uppercase |
| `--text-mono` | `13px / 1.5` | 400 | `0` | mono utility |

Body sits at 15px (not 16) to match Linear's compressed reading rhythm. Body text never goes below 13px.

### Spacing (base unit 4px)

| Token | Value |
|---|---|
| `--space-0` | `0` |
| `--space-1` | `4px` |
| `--space-2` | `8px` |
| `--space-3` | `12px` |
| `--space-4` | `16px` |
| `--space-5` | `20px` |
| `--space-6` | `24px` |
| `--space-8` | `32px` |
| `--space-10` | `40px` |
| `--space-12` | `48px` |
| `--space-16` | `64px` |
| `--space-20` | `80px` |

### Radii

| Token | Value | Usage |
|---|---|---|
| `--radius-sm` | `4px` | Inline badges, code chips |
| `--radius-md` | `6px` | Buttons, inputs, toolbar |
| `--radius-lg` | `8px` | Cards, dropdowns |
| `--radius-xl` | `12px` | Panels, modals, calendar container |
| `--radius-2xl` | `16px` | Auth card |
| `--radius-full` | `9999px` | Pills, avatars, status dots |

### Shadows (dark-mode luminance stacking, not drop shadows)

On dark surfaces, dark-on-dark shadows disappear. We use them only on elevated floating layers (modals, popovers) where they read against the dimmed overlay. Cards at rest use border and luminance shift, not shadow.

| Token | Dark value | Light value | Usage |
|---|---|---|---|
| `--shadow-popover` | `0 8px 24px 0 rgba(0,0,0,0.40), 0 0 0 1px rgba(255,255,255,0.06)` | `0 8px 24px 0 rgba(0,0,0,0.10), 0 0 0 1px rgba(0,0,0,0.04)` | Dropdowns, popovers |
| `--shadow-modal` | `0 16px 48px 0 rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.08)` | `0 16px 48px 0 rgba(0,0,0,0.15), 0 0 0 1px rgba(0,0,0,0.05)` | Modals, drawers |
| `--shadow-toast` | `0 4px 16px 0 rgba(0,0,0,0.40), 0 0 0 1px rgba(255,255,255,0.06)` | `0 4px 16px 0 rgba(0,0,0,0.08), 0 0 0 1px rgba(0,0,0,0.04)` | Toasts |
| `--shadow-focus` | `0 0 0 3px rgba(59,130,246,0.45)` | `0 0 0 3px rgba(59,130,246,0.35)` | Keyboard focus ring |

### Motion (exact durations, exact cubic-beziers)

| Token | Value | Usage |
|---|---|---|
| `--duration-instant` | `75ms` | Color shifts, hover tints |
| `--duration-fast` | `150ms` | Buttons, toggles, dropdowns |
| `--duration-base` | `250ms` | Panels, drawers, modals |
| `--duration-slow` | `400ms` | Page transitions, hero entries |
| `--ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` | Default exit/entry |
| `--ease-in-out` | `cubic-bezier(0.65, 0, 0.35, 1)` | State switches |
| `--ease-spring` | `cubic-bezier(0.32, 0.72, 0, 1)` | Linear-feel micro-interactions |
| `--ease-standard` | `cubic-bezier(0.4, 0, 0.2, 1)` | Generic transitions |

Only `transform` and `opacity` are animated. `filter` allowed for blur on overlays. No `width`, `height`, `top`, `left`, `margin`, `padding` ever enters a transition.

### Z-index scale

| Token | Value | Layer |
|---|---|---|
| `--z-base` | `0` | Default flow |
| `--z-dropdown` | `1000` | Menus, popovers |
| `--z-sticky` | `1100` | Topbar |
| `--z-sidebar` | `1200` | Mobile drawer sidebar |
| `--z-modal-backdrop` | `1300` | Modal overlay |
| `--z-modal` | `1310` | Modal surface |
| `--z-toast` | `1400` | Toast stack |

## 3. Typography

Single family: `@fontsource-variable/inter` self-hosted. Inter Variable ships one file with the full weight axis; we pick `400`, `500`, `600`, `700` from it. Body and display both Inter. `@fontsource-variable/jetbrains-mono` self-hosted for code, calendar event UIDs, API keys, and `<kbd>` keystrokes. No Google Fonts CDN, no preconnect, no third-party font request.

```css
:root {
  --font-sans: "Inter Variable", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-mono: "JetBrains Mono Variable", ui-monospace, "SFMono-Regular", Menlo, monospace;
}
body {
  font-family: var(--font-sans);
  font-feature-settings: "cv01", "ss03"; /* Linear's alternates; cleaner 'a' and tighter letterforms */
  font-size: 15px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
code, kbd, pre { font-family: var(--font-mono); }
```

OpenType features `cv01` and `ss03` are non-negotiable. Without them, this is generic Inter. With them, the 'a' becomes single-story and several letterforms tighten, giving Inter its Linear-grade character.

Letter-spacing scales with size. Display headings run `-0.025em` at 48px, easing toward `0` at 15px. Body text never gets tracking. Overlines and micro labels get `+0.08em` uppercase.

Mono usage rule: any identifier the user might copy (calendar UID, principal URL, API token, CSS hex code in a tooltip, HTTP method) renders in JetBrains Mono at `--text-mono`. Never use mono for prose.

## 4. Layout and Spacing

### Shell geometry

| Token | Value | Notes |
|---|---|---|
| `--sidebar-width` | `256px` | Expanded desktop |
| `--sidebar-width-collapsed` | `64px` | Icon rail at `lg` breakpoint |
| `--sidebar-width-drawer` | `288px` | Off-canvas drawer at `<md` |
| `--topbar-height` | `56px` | Sticky topbar |
| `--content-max-width` | `1280px` | Calendar goes full width; admin caps here |
| `--content-gutter` | `32px` | Desktop horizontal padding |
| `--content-gutter-mobile` | `16px` | Mobile horizontal padding |

### Breakpoints

| Name | Width | Behavior |
|---|---|---|
| `sm` | `640px` | Phone landscape, single column |
| `md` | `768px` | Drawer sidebar appears below this |
| `lg` | `1024px` | Sidebar collapses to icon rail at and above this |
| `xl` | `1280px` | Standard desktop |
| `2xl` | `1536px` | Wide desktop, calendar stretches |

### Sidebar layout

Three rows: logo (top, 56px tall), nav (middle, scrollable), user menu (footer, fixed). Glassy background using `--color-bg-sidebar` over a `backdrop-filter: blur(12px) saturate(180%)`. Inner right edge carries a 1px `--color-border-subtle`.

At `lg` and above the sidebar is full width (256px). Between `md` and `lg` it becomes the 64px icon rail with tooltip labels. Below `md` it transforms into a drawer that slides in from the left, dismissed by overlay tap or escape key.

### Topbar layout

Three slots: page title (left, `--text-h3` weight 600), search and action slot (center-right), dark toggle and user menu (right, 40px icon buttons). Sticky, with the same glassy treatment as the sidebar and a 1px bottom border.

### Login layout

Dedicated `_auth_base.html` with no sidebar, no topbar. Centered auth card (`--radius-2xl`, `--space-8` padding, `--content-max-width: 420px`). Background uses `--color-bg-auth` gradient. Brand mark (Lucide `calendar-clock` icon) sits above the card.

## 5. Components

### Buttons

```html
<button class="btn btn-primary">Save changes</button>
<button class="btn btn-secondary">Cancel</button>
<button class="btn btn-ghost">Settings</button>
<button class="btn btn-danger">Revoke</button>
<button class="btn btn-link">Forgot password?</button>
```

| Variant | Dark | Light |
|---|---|---|
| `btn-primary` | bg `--color-accent-500`, text `--color-text-inverse`, hover `--color-accent-600` | bg `--color-accent-600`, text white, hover `--color-accent-700` |
| `btn-secondary` | bg `--color-bg-elevated`, text `--color-text-primary`, border `--color-border-default` | bg `--color-bg-surface`, text `--color-text-primary`, border `--color-border-default` |
| `btn-ghost` | transparent, text `--color-text-secondary`, hover bg `--color-bg-hover` | same |
| `btn-danger` | bg `--color-danger`, text white | same |
| `btn-link` | transparent, text `--color-accent-400` (dark) / `--color-accent-600` (light), underline on hover | same |

Sizes: `btn-sm` (`--space-2 --space-3`, 13px text), `btn-md` (`--space-2 --space-4`, 14px text, default), `btn-lg` (`--space-3 --space-5`, 15px text). Radius `--radius-md` on all sizes.

States: hover (`--duration-instant --ease-out`), active (`transform: scale(0.98)`, `--duration-instant`), focus-visible (`--shadow-focus`), disabled (`opacity: 0.5`, `cursor: not-allowed`), loading (text replaced by 14px spinning `LoaderCircle` Lucide icon, button non-interactive).

### Inputs

```html
<input class="input" type="text" placeholder="Calendar name">
<select class="input">...</select>
<label class="switch"><input type="checkbox"><span class="switch-track"></span></label>
```

Text and select inputs: bg `--color-bg-surface` (dark) / `--color-bg-canvas` (light), border `--color-border-input`, text `--color-text-primary`, placeholder `--color-text-tertiary`, padding `--space-2 --space-3`, radius `--radius-md`, height `36px`. Focus state replaces border with `--color-border-focus` plus `--shadow-focus`. Error state paints border `--color-danger` and shows helper text in `--color-danger`.

Switch: 36px wide, 20px tall track, 16px circle. Track bg `--color-bg-elevated` off, `--color-accent-500` on. Knob translates `translateX(16px)` on toggle, `--duration-fast --ease-spring`.

### Tables

Linear-style rows. Each row is `48px` tall, separated by `1px solid --color-border-subtle`, no outer border. Header row uses `--text-overline`, sticky at the top of scroll containers. Row hover paints `--color-bg-hover`. Active row gets `box-shadow: inset 2px 0 0 var(--color-accent-500)` on the left edge.

### Cards

bg `--color-bg-surface`, border `1px solid --color-border-default`, radius `--radius-lg`, padding `--space-6`. Header uses `--text-h3`, body uses `--text-body-sm`. Hover on interactive cards lifts `transform: translateY(-1px)` over `--duration-fast --ease-out` (no shadow change).

### Badges (permission roles)

```html
<span class="badge badge-admin">Admin</span>
<span class="badge badge-admin-permission">Admin granted</span>
<span class="badge badge-write">Write</span>
<span class="badge badge-read">Read</span>
```

Pill shape (`--radius-full`), padding `2px --space-2`, font `--text-label` weight 500. Background uses the permission token at `0.14` opacity in dark mode and `0.12` opacity in light mode, text uses the full token color. Border `1px solid` the same token at `0.30` opacity.

### Modals

Centered, max-width `480px` (delete confirm) or `640px` (event editor), bg `--color-bg-elevated`, radius `--radius-xl`, padding `--space-6`. Backdrop uses `--color-bg-overlay` with `backdrop-filter: blur(4px)`. Mount animation: backdrop fades `opacity 0 -> 1` and modal scales `transform: scale(0.96) -> 1` over `--duration-base --ease-spring`. Focus is trapped inside the modal via Tab key interception. Escape closes. First focusable element receives focus on mount.

### Dropdown menus

Min-width `180px`, bg `--color-bg-elevated`, radius `--radius-lg`, padding `--space-1`, shadow `--shadow-popover`. Items are `--space-2 --space-3` padding, `--text-body-sm`, radius `--radius-md`, hover bg `--color-bg-hover`. Destructive items use `--color-danger` text. Separators are `1px solid --color-border-subtle` with `--space-1` vertical margin.

### Tabs

Underline tabs. Active tab gets `2px` bottom border in `--color-accent-500`, text `--color-text-primary`. Inactive tabs use `--color-text-secondary` and animate the underline in on hover with `--duration-fast --ease-out`. Tab strip has a single `1px` bottom border in `--color-border-subtle`.

### Tooltips

Dark surface `--color-bg-elevated`, text `--color-text-primary`, padding `--space-1 --space-2`, radius `--radius-sm`, font `--text-caption`. Appear after `500ms` hover delay, fade in over `--duration-instant`. Never carry interactive content.

### Empty states

Centered block: Lucide icon at `32px` in `--color-text-tertiary`, headline `--text-h3`, body `--text-body-sm` in `--color-text-secondary`, optional `btn-secondary`. Padding `--space-12` vertical.

### Skeleton loaders

Bar shape, bg `--color-bg-elevated`, pulse animation `opacity 1 -> 0.5 -> 1` over `1.4s` linear infinite. Text skeletons are `12px` tall, button skeletons `32px` tall, card skeletons `120px` tall.

### Sidebar nav items

Single-line items, `--space-2 --space-3` padding, radius `--radius-md`, font `--text-body-sm` weight 500, text `--color-text-secondary`. Lucide icon at `16px` sits left with `--space-2` gap. Active state: bg `--color-bg-hover`, text `--color-text-primary`, left icon in `--color-accent-400`. Hover: bg `--color-bg-hover` over `--duration-instant`.

### Topbar

Already described in section 4. Components inside: search input (`input` with Lucide `search` icon prefix), action buttons (`btn-ghost` with Lucide icon), dark toggle (`btn-ghost` 40px square with `sun` or `moon` icon), user menu (`btn-ghost` showing avatar circle and chevron, opens dropdown).

## 6. Calendar Theming (FullCalendar)

FullCalendar ships `fc-theme-standard` whose visual layer is driven by CSS custom properties. We override those properties, scoped under `.calendar-app`, and drop the Bootstrap 5 stylesheet entirely. Self-hosted via npm; never loaded from a CDN.

```css
.calendar-app {
  /* Page and surface */
  --fc-page-bg-color: var(--color-bg-surface);
  --fc-neutral-bg-color: var(--color-bg-canvas);          /* off-hours, non-business */
  --fc-neutral-skeleton-bg-color: rgba(255,255,255,0.04); /* time grid skeleton */
  --fc-non-business-color: rgba(0,0,0,0.18);

  /* Borders */
  --fc-border-color: var(--color-border-subtle);

  /* Today + now */
  --fc-today-bg-color: rgba(59,130,246,0.06);
  --fc-now-indicator-color: var(--color-accent-500);

  /* Toolbar buttons (prev/next/today/view switcher) */
  --fc-button-bg-color: transparent;
  --fc-button-border-color: var(--color-border-default);
  --fc-button-text-color: var(--color-text-secondary);
  --fc-button-hover-bg-color: var(--color-bg-hover);
  --fc-button-hover-border-color: var(--color-border-default);
  --fc-button-active-bg-color: var(--color-bg-hover);
  --fc-button-active-border-color: var(--color-accent-500);

  /* Events (default; overridden inline per calendar color) */
  --fc-event-bg-color: var(--color-cal-accent);
  --fc-event-border-color: transparent;
  --fc-event-text-color: #ffffff;
  --fc-event-selected-overlay-color: rgba(0,0,0,0.15);

  /* Misc */
  --fc-highlight-color: rgba(59,130,246,0.10); /* drag-select highlight */
  --fc-resizer-color: rgba(255,255,255,0.60);
  --fc-bg-event-color: var(--color-cal-violet); /* all-day background events */
}
```

Event block styling overrides `fc-daygrid-event`, `fc-timegrid-event`, and `fc-event` directly:

```css
.calendar-app .fc-event {
  border-radius: var(--radius-sm);             /* 4px per locked decision */
  border: none;
  font-size: var(--text-label);                /* 12px */
  font-weight: 500;
  padding: 1px 6px;
  background-image: linear-gradient(135deg,
    color-mix(in srgb, var(--fc-event-bg-color) 92%, #ffffff 8%),
    var(--fc-event-bg-color));
  box-shadow: 0 1px 2px 0 rgba(0,0,0,0.20);
  transition: transform var(--duration-instant) var(--ease-out),
              box-shadow var(--duration-instant) var(--ease-out);
}
.calendar-app .fc-event:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px 0 rgba(0,0,0,0.30);
}
.calendar-app .fc-event-selected,
.calendar-app .fc-event:focus { box-shadow: var(--shadow-focus); }
.calendar-app .fc-day-today { background-color: var(--fc-today-bg-color); }
.calendar-app .fc-col-header-cell-cushion,
.calendar-app .fc-daygrid-day-number,
.calendar-app .fc-timegrid-slot-label-cushion {
  color: var(--color-text-secondary);
  font-weight: 500;
  text-decoration: none;
}
.calendar-app .fc-toolbar-title { font-size: var(--text-h3); font-weight: 600; }
.calendar-app .fc-button {
  text-transform: none;
  border-radius: var(--radius-md);
  padding: var(--space-1) var(--space-3);
  font-weight: 500;
}
.calendar-app .fc-button-active { box-shadow: inset 0 0 0 1px var(--color-accent-500); }
```

Per-calendar coloring: each calendar stores a key into the `--color-cal-*` list. When the calendar renders, the template sets `--fc-event-bg-color` inline on its event source:

```html
<div class="calendar-app" style="--fc-event-bg-color: {{ calendar.css_var_value }};">
```

The event editor modal extends the standard modal spec with three sections (summary, time, calendar picker) using `input`, `select`, and `btn-primary` save. Time pickers inherit input styling. Calendar picker uses a color swatch plus name as a custom select list.

## 7. Motion and Interaction

### Per-state contracts

Every interactive component declares: hover, active, focus-visible, disabled. Transitions use `--duration-instant` for color/background, `--duration-fast` for transforms.

### Micro-interactions

- Button press: `transform: scale(0.98)` for `--duration-instant`.
- Sidebar nav click: active item indicator slides in over `--duration-fast --ease-spring`.
- Mobile drawer open: `transform: translateX(-100%) -> 0` over `--duration-base --ease-spring`. Backdrop fades `opacity` over `--duration-base`.
- Modal open: backdrop fade + modal `scale(0.96) -> 1`, both `--duration-base --ease-spring`.
- Toast slide-in: `transform: translateY(16px) -> 0` plus `opacity 0 -> 1`, `--duration-base --ease-out`. Auto-dismiss after 5000ms, fade out `--duration-fast`.
- Dark mode toggle: a 400ms cross-fade on the toggle icon. No theme transition on the document body itself (would force repaint of every surface; instead, the new palette paints immediately).

### Reduced motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

All transforms become near-instant. Color and opacity changes still apply (so state is legible). Skeleton pulse stops.

## 8. Dark Mode Rules

Class-based dark mode via `darkVariant: 'class'` in the Tailwind config. The `.dark` class is applied to `<html>`. Native form controls honor the theme through `color-scheme: light dark` on `:root`.

```css
:root { color-scheme: light dark; }
```

### FOUC buster (preserved from the current codebase)

The existing inline script in `base.html` and `user_base.html` stays. It runs synchronously in `<head>` before paint, reads `localStorage.getItem('darkMode')`, falls back to `window.matchMedia('(prefers-color-scheme: dark)')`, and adds the `dark` class to `documentElement` before the body renders.

```html
<script>
  (function () {
    if (localStorage.getItem('darkMode') === 'true' ||
        (!localStorage.getItem('darkMode') &&
         window.matchMedia('(prefers-color-scheme: dark)').matches)) {
      document.documentElement.classList.add('dark');
    }
  })();
</script>
```

The toggle button updates both the class and the same `localStorage` key, preserving the existing user-mental-model.

## 9. Accessibility Contract

- WCAG 2.1 AA. AAA where stated.
- Focus rings are always visible on keyboard navigation via `:focus-visible { box-shadow: var(--shadow-focus); outline: none; }`. Never remove focus styles outright.
- Body text contrast: minimum `4.5:1`. Headlines and UI labels (14px+, weight 500+): minimum `3:1`.
- Cited pairs:
  - `--color-text-primary` on `--color-bg-surface`: `#fafafa` on `#18181b` = **18.7:1** (AAA).
  - `--color-text-secondary` on `--color-bg-surface`: `#a1a1aa` on `#18181b` = **7.5:1** (AAA).
  - `--color-text-tertiary` on `--color-bg-surface`: `#71717a` on `#18181b` = **4.6:1** (AA).
  - `--color-accent-400` on `--color-bg-surface` (dark-mode accent text): `#60a5fa` on `#18181b` = **6.7:1** (AA). Use this for accent text on dark surfaces, never `--color-accent-500`.
  - White on `--color-accent-600` (light-mode primary button): `#ffffff` on `#2563eb` = **5.2:1** (AA). This is why the primary button uses accent-600 in light mode, accent-500 in dark mode.
  - `--color-text-primary` on `--color-bg-surface` in light: `#09090b` on `#ffffff` = **19.0:1** (AAA).
- Touch targets: minimum `40px x 40px`. Icon buttons are exactly 40px square.
- Keyboard: every interactive element is reachable via Tab. Modals trap focus. Dropdowns restore focus to trigger on close. Escape closes overlays.
- `prefers-reduced-motion` disables non-essential animation (see section 7).
- Form inputs always render with an associated `<label>`. Error messages link via `aria-describedby`.

## 10. Asset Conventions

- Icons: Lucide self-hosted via npm. Rendered server-side as inline SVG in Jinja2 macros, or client-side via `lucide.createIcons()`. Stroke width `1.5` everywhere. No emoji icons.
- Fonts: `@fontsource-variable/inter` and `@fontsource-variable/jetbrains-mono` only. Both self-hosted, served from the same origin. Preload the Inter Variable woff2 in `<head>` with `font-display: swap`.
- No external CDN URLs anywhere. The current Bootstrap CDN link and Google Fonts preconnect (if present) are removed in the build.
- SVG icons live inline; no separate sprite file. Macros under `app/templates/macros/icon.html` render `<svg>` directly from a name lookup.

## 11. Token to Tailwind Mapping

Every CSS variable becomes a Tailwind config entry. The Tailwind config written in the next wave mirrors this table verbatim.

| CSS variable | Tailwind config path | Tailwind utility examples |
|---|---|---|
| `--color-bg-canvas` | `theme.colors.canvas` | `bg-canvas`, `text-canvas` |
| `--color-bg-surface` | `theme.colors.surface` | `bg-surface`, `border-surface` |
| `--color-bg-elevated` | `theme.colors.elevated` | `bg-elevated` |
| `--color-bg-hover` | `theme.colors.hover` | `bg-hover` |
| `--color-bg-sidebar` | `theme.colors.sidebar` | `bg-sidebar` |
| `--color-bg-topbar` | `theme.colors.topbar` | `bg-topbar` |
| `--color-bg-overlay` | `theme.colors.overlay` | `bg-overlay` |
| `--color-text-primary` | `theme.colors.text.primary` | `text-text-primary` (aliased `text-primary`) |
| `--color-text-secondary` | `theme.colors.text.secondary` | `text-secondary` |
| `--color-text-tertiary` | `theme.colors.text.tertiary` | `text-tertiary` |
| `--color-text-quaternary` | `theme.colors.text.quaternary` | `text-quaternary` |
| `--color-text-inverse` | `theme.colors.text.inverse` | `text-inverse` |
| `--color-border-default` | `theme.colors.border.default` | `border-default` |
| `--color-border-subtle` | `theme.colors.border.subtle` | `border-subtle` |
| `--color-border-strong` | `theme.colors.border.strong` | `border-strong` |
| `--color-border-focus` | `theme.colors.border.focus` | `border-focus` |
| `--color-border-input` | `theme.colors.border.input` | `border-input` |
| `--color-accent-50..950` | `theme.colors.accent.50..950` | `bg-accent-500`, `text-accent-400` |
| `--color-success` / `-bg` | `theme.colors.success` / `.bg` | `bg-success-bg`, `text-success` |
| `--color-warning` / `-bg` | `theme.colors.warning` / `.bg` | `bg-warning-bg`, `text-warning` |
| `--color-danger` / `-bg` | `theme.colors.danger` / `.bg` | `bg-danger-bg`, `text-danger` |
| `--color-info` | `theme.colors.info` | `text-info` |
| `--color-cal-*` (6) | `theme.colors.calendar.accent` etc. | `bg-calendar-accent` |
| `--color-perm-*` (4) | `theme.colors.perm.admin` etc. | `text-perm-admin` |
| `--text-display..overline` | `theme.fontSize.display..overline` | `text-display`, `text-h1` |
| `--space-0..20` | `theme.spacing.0..20` | `p-6`, `m-8`, `gap-4` |
| `--radius-sm..2xl` | `theme.radius.sm..2xl` | `rounded-lg`, `rounded-modal` |
| `--shadow-popover/modal/toast/focus` | `theme.boxShadow.popover` etc. | `shadow-popover`, `shadow-focus` |
| `--duration-instant/fast/base/slow` | `theme.transitionDuration.*` | `duration-instant`, `duration-base` |
| `--ease-out/in-out/spring/standard` | `theme.transitionTimingFunction.*` | `ease-out`, `ease-spring` |
| `--z-base/dropdown/sticky/sidebar/modal-backdrop/modal/toast` | `theme.zIndex.*` | `z-dropdown`, `z-modal` |
| `--font-sans` / `--font-mono` | `theme.fontFamily.sans` / `.mono` | `font-sans`, `font-mono` |
| `--sidebar-width` etc. | `theme.width.sidebar` etc. | `w-sidebar` |
| `--topbar-height` | `theme.height.topbar` | `h-topbar` |
| `--content-max-width` | `theme.maxWidth.content` | `max-w-content` |

Dark mode strategy: every color utility above is overridden under the `.dark` variant. The Tailwind config writes a `darkColor` key for each token and the CSS variable on `:root` and `.dark` is what the utility reads from. This keeps the Tailwind classes stable across themes (the HTML never references a different class in dark mode; the underlying CSS variable flips).

```css
:root {
  --color-bg-canvas: #fafafa;
  /* ...light values... */
}
.dark {
  --color-bg-canvas: #09090b;
  /* ...dark values... */
}
@layer base {
  body { background-color: var(--color-bg-canvas); color: var(--color-text-primary); }
}
```

## 12. Validation Checklist

Before declaring any template or component done:

- All hex values reference tokens from this file. No raw hex in templates.
- All font sizes map to the type scale. No `text-[13.5px]` arbitrary values.
- All spacing values are multiples of `--space-1` (4px) and use a token.
- Every interactive element has hover, active, focus-visible, and disabled states.
- Depth treatment matches the chosen strategy: cards use border + luminance, only modals/dropdowns/toasts use shadow.
- Motion uses the timing and easing tokens. No arbitrary durations.
- Accent color appears only on interactive surfaces. Decorative use is a violation.
- No emojis. No external CDN URLs. No Bootstrap class names.

## 13. Memory Discipline

This file grows when a genuinely new pattern emerges (a component used twice, a new semantic color). It does not grow on "might need later". Every addition must remove ambiguity, not add options.
