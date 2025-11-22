# boringhannover Frontend Plan

> "You're in the metro on a rainy, cold day. You don't know what's happening in Hannover this week. You check the plan."

## Overview

This document outlines the frontend vision for **boringhannover** - a modern, minimal web interface inspired by Nothing's design language. The goal is to deliver event information fast, with a sleek aesthetic that feels at home on a phone screen.

---

## Final Decisions

| Decision | Choice |
|----------|--------|
| **Name** | boringhannover |
| **Domain** | boringhannover.de ✓ (registered) |
| **Accent Color** | `#ff3b3b` (Nothing red) |
| **Deployment** | Hetzner + Coolify |
| **Analytics** | Plausible / Umami (TBD) |

---

## Design Philosophy

### Core Principles

1. **Information velocity** - Get the answer in seconds, not minutes
2. **Mobile-first** - Designed for one-handed scrolling on public transport
3. **Nothing-inspired** - Dot-matrix accents, dark mode, typographic hierarchy
4. **Stateless simplicity** - Weekly rebuild, no backend complexity

### Visual Identity

| Element | Direction |
|---------|-----------|
| **Mode** | Dark only (for now) |
| **Color** | Near-black bg, off-white text, single accent |
| **Typography** | Monospace display + clean sans-serif body |
| **Density** | Compact but breathable - optimize for scanning |
| **Motion** | Minimal - subtle where it aids comprehension |

---

## Phase 1: MVP (Current Focus)

### Approach: A + B Hybrid

Combining **"Glyph Matrix"** (dot-matrix aesthetic) with **"Digital Brutalism"** (typography-first, raw, functional).

### Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Interactivity | Info display only | Ship fast, add features later |
| Platform focus | Mobile-first | Primary use case is on-the-go |
| Page structure | Single page | Everything visible, no navigation needed |
| Images | No posters | Text-pure for speed, posters are Phase 2 |
| Update frequency | Weekly static build | Matches existing workflow |
| Content hierarchy | Flat, informative | No venue highlighting yet |

### Target Layout (Mobile)

```
┌─────────────────────────────┐
│                             │
│  ▪▪▪ BORINGHANNOVER ▪▪▪    │
│  W47 · 2025                 │
│                             │
├─────────────────────────────┤
│                             │
│  MOVIES THIS WEEK           │
│  ═══════════════            │
│                             │
│  FRI 21.11 ─────────────    │
│                             │
│  CHAINSAW MAN              │
│  Reze Arc (2025)            │
│  22:50 · JP→DE · 1h41m     │
│  FSK16                      │
│                             │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   │
│                             │
│  SAT 22.11 ─────────────    │
│                             │
│  GLADIATOR II              │
│  19:30 · EN→DE · 2h28m     │
│  FSK16                      │
│                             │
│  WICKED                    │
│  20:00 · EN→DE · 2h40m     │
│  FSK12                      │
│                             │
├─────────────────────────────┤
│                             │
│  ON THE RADAR              │
│  ═══════════════            │
│                             │
│  29 Nov · Sa                │
│  LUCIANO                   │
│  20:00 @ ZAG Arena          │
│                             │
│  05 Dec · Fr                │
│  SIMPLY RED                │
│  20:00 @ Swiss Life Hall    │
│                             │
│  12 Dec · Fr                │
│  MAT KEARNEY              │
│  19:30 @ MusikZentrum       │
│                             │
├─────────────────────────────┤
│                             │
│  Updated: Mon 18 Nov 09:00  │
│  ▪ ▪ ▪                      │
│                             │
└─────────────────────────────┘
```

### Design Tokens

```css
:root {
  /* Colors */
  --bg-primary: #0a0a0a;
  --bg-secondary: #141414;
  --bg-tertiary: #1a1a1a;

  --text-primary: #e5e5e5;
  --text-secondary: #888888;
  --text-muted: #555555;

  --accent: #ff3b3b;           /* Nothing red - or choose your own */
  --accent-dim: #ff3b3b33;

  --border: #2a2a2a;

  /* Typography */
  --font-display: 'Space Mono', 'SF Mono', monospace;
  --font-body: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;

  --text-xs: 0.75rem;    /* 12px */
  --text-sm: 0.875rem;   /* 14px */
  --text-base: 1rem;     /* 16px */
  --text-lg: 1.125rem;   /* 18px */
  --text-xl: 1.5rem;     /* 24px */
  --text-2xl: 2rem;      /* 32px */

  /* Spacing */
  --space-1: 0.25rem;    /* 4px */
  --space-2: 0.5rem;     /* 8px */
  --space-3: 0.75rem;    /* 12px */
  --space-4: 1rem;       /* 16px */
  --space-6: 1.5rem;     /* 24px */
  --space-8: 2rem;       /* 32px */

  /* Layout */
  --max-width: 480px;
  --padding-x: var(--space-4);
}
```

### Typography Hierarchy

```
HEADER (dot-matrix style)
├── Logo: Space Mono, 24px, bold, letter-spacing: 0.1em
└── Meta: Space Mono, 12px, muted

SECTION HEADER
├── Title: Space Mono, 14px, uppercase, accent color
└── Divider: ═══ character or border

DATE HEADER
└── Date: Space Mono, 14px, secondary color

EVENT CARD
├── Title: Inter, 18px, semibold, primary
├── Subtitle: Inter, 14px, secondary (year, director)
├── Details: Space Mono, 12px, muted (time, language, duration)
└── Badge: Space Mono, 11px, muted (FSK rating)

FOOTER
└── Timestamp: Space Mono, 11px, muted
```

### Tech Stack

```
Framework:    Astro (static site generator)
Styling:      TailwindCSS + custom CSS
Fonts:        Space Mono (Google Fonts) + Inter (system/Google)
Build:        Python exports JSON → Astro builds HTML
Deploy:       Hetzner + Coolify (Docker)
Domain:       boringhannover.de (Cloudflare DNS)
```

### Build Pipeline

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Python    │     │    Astro    │     │   Coolify   │
│  Scraper    │────▶│   Build     │────▶│   Deploy    │
│             │     │             │     │             │
│ events.json │     │ index.html  │     │  Live Site  │
└─────────────┘     └─────────────┘     └─────────────┘
     │                                        │
     │         Weekly (Monday 9 AM)           │
     └────────────────────────────────────────┘
```

---

## Phase 2: Enhancements (Future)

### 2.1 Movie Posters

Add visual richness with poster images (already available in metadata).

```
┌─────────────────────────────┐
│  FRI 21.11                  │
│  ┌────────┬────────────────┐│
│  │ POSTER │ CHAINSAW MAN   ││
│  │  img   │ 22:50 · JP→DE  ││
│  │  80px  │ 1h41m · FSK16  ││
│  └────────┴────────────────┘│
└─────────────────────────────┘
```

**Considerations:**
- Lazy loading for performance
- Placeholder/skeleton while loading
- Fallback for missing posters
- WebP format with JPEG fallback

### 2.2 Venue Filtering

Allow users to filter by venue or category.

```
┌─────────────────────────────┐
│  [All] [Movies] [Concerts]  │
│                             │
│  or                         │
│                             │
│  [●] ZAG Arena              │
│  [●] Swiss Life Hall        │
│  [○] Béi Chéz Heinz         │
│  [●] MusikZentrum           │
└─────────────────────────────┘
```

### 2.3 "Happening Now" Indicator

Real-time awareness of current/upcoming events.

```
│  ● LIVE NOW                 │
│  GLADIATOR II              │
│  Started 19:30 · Ends ~22:00│
```

### 2.4 Notifications / PWA

- Add to homescreen capability
- Push notifications for new events
- Offline support (cached last update)

### 2.5 Light Mode Toggle

For daytime/outdoor viewing.

---

## Phase 3: Timeline Approach (Alternative Design)

An alternative interaction model where TIME is the primary navigation axis.

### Concept

Instead of sections (Movies / Concerts), present a unified timeline. Scroll = travel through time.

### Visual Design

```
┌─────────────────────────────┐
│  BORINGHANNOVER             │
│                             │
│         ┃                   │
│    NOW ─╋─ ─ ─ ─ ─ ─ ─ ─   │
│         ┃                   │
│         ┃                   │
│   FRI   ┣━━[ Chainsaw Man ] │
│   21    ┃   22:50 · Astor   │
│         ┃                   │
│   SAT   ┣━━[ Gladiator II ] │
│   22    ┃   19:30 · Astor   │
│         ┣━━[ Wicked ]       │
│         ┃   20:00 · Astor   │
│         ┃                   │
│   SUN   ┃                   │
│   23    ┃   (no events)     │
│         ┃                   │
│  ───────╋─── RADAR ─────────│
│         ┃                   │
│   29    ┣━━[ LUCIANO ]      │
│   NOV   ┃   @ ZAG Arena     │
│         ┃                   │
│   05    ┣━━[ SIMPLY RED ]   │
│   DEC   ┃   @ Swiss Life    │
│         ┃                   │
│         ┇                   │
└─────────────────────────────┘
```

### Interaction

- Vertical scroll through time
- "NOW" marker stays visible (sticky) or snaps to top
- Events branch off the timeline to the right
- Tap event for details (expand in place or modal)
- Optional: horizontal swipe to filter (Movies ↔ All ↔ Concerts)

### Technical Notes

- More complex CSS (flexbox/grid for timeline layout)
- Requires calculating "NOW" position dynamically
- Mobile: works well with thumb scrolling
- Consider: infinite scroll for "radar" section?

### Pros

- Unique, memorable interaction
- Emphasizes the temporal nature of events
- "What's next?" is always clear
- Natural for weekly digest format

### Cons

- More complex to implement
- Empty days create visual gaps
- Desktop layout needs separate consideration
- May feel unfamiliar to users

### When to Consider

- After Phase 1 is stable
- If user feedback indicates "what's happening now?" is primary need
- As an optional "Timeline View" toggle

---

## File Structure (Proposed)

```
/home/user/KinoWeek/
├── src/
│   └── kinoweek/           # Existing Python package
│       └── ...
├── web/                    # NEW: Frontend
│   ├── src/
│   │   ├── layouts/
│   │   │   └── Base.astro
│   │   ├── components/
│   │   │   ├── Header.astro
│   │   │   ├── MovieCard.astro
│   │   │   ├── ConcertCard.astro
│   │   │   ├── SectionHeader.astro
│   │   │   └── Footer.astro
│   │   ├── pages/
│   │   │   └── index.astro
│   │   └── styles/
│   │       └── global.css
│   ├── public/
│   │   └── fonts/          # If self-hosting
│   ├── astro.config.mjs
│   ├── tailwind.config.mjs
│   └── package.json
├── output/
│   └── events.json         # Python outputs here, Astro reads
└── docs/
    └── frontend-plan.md    # This file
```

---

## Next Steps

1. [ ] Set up Astro project structure
2. [ ] Configure TailwindCSS with design tokens
3. [ ] Create base layout and typography
4. [ ] Build Header component (dot-matrix style)
5. [ ] Build MovieCard component
6. [ ] Build ConcertCard component
7. [ ] Build SectionHeader component
8. [ ] Build Footer component
9. [ ] Create index page assembling components
10. [ ] Connect to events.json data
11. [ ] Test on mobile devices
12. [ ] Deploy to GitHub Pages
13. [ ] Integrate into CI/CD pipeline

---

## References

### Design Inspiration

- [Nothing OS](https://nothing.tech) - Dot-matrix aesthetic, dark mode
- [dark.design](https://dark.design) - Curated dark websites
- [Brutalist Web Design](https://brutalist-web.design) - Raw typography

### Technical

- [Astro Docs](https://docs.astro.build)
- [TailwindCSS](https://tailwindcss.com)
- [Space Mono Font](https://fonts.google.com/specimen/Space+Mono)
- [Inter Font](https://rsms.me/inter/)

---

*Last updated: 2025-11-21*
*Status: Phase 1 implementation in progress*
