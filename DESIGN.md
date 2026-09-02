---
name: IRIS — Cognitive Obsidian
description: A calm, high-precision personal intelligence assistant design system; deep obsidian surfaces, luminous AI status lamps, and crisp telemetry typography.
palette:
  void: "#080A0F"
  ground: "#0D1117"
  panel: "#151B23"
  raised: "#1F2631"
  line: "#252D3A"
  line-bright: "#354052"
  ink: "#F0F6FC"
  ink-dim: "#94A3B8"
  ink-faint: "#64748B"
  ai: "#38BDF8"
  ai-dim: "#0C4A6E"
  go: "#10B981"
  go-dim: "#064E3B"
  caution: "#F59E0B"
  caution-dim: "#78350F"
  critical: "#F43F5E"
  critical-dim: "#881337"
typography:
  display: "Chakra Petch (500/600/700) — system markings, aperture branding, status caps"
  body: "Barlow / System Sans (400/500/600) — 15px/1.5 base, -0.011em tracking"
  telemetry: "JetBrains Mono (400/600), tabular numerals (.tnum) — times, clocks, countdowns"
radius:
  card: "rounded-xl (12px) — refined soft geometry"
  button: "rounded-lg (8px) / rounded-full (capsules)"
  lamp: "rounded-full (circular status beacons)"
spacing:
  unit: "4px base; panel padding 16px; conversation stream 24px"
motion:
  lamp-pulse: "2.4s ease-in-out subtle breath for active states"
  ai-glow: "3.0s ease-in-out luminescent ambient aura for AI cognition"
---

# Design System: IRIS — Cognitive Obsidian

## Overview

IRIS is engineered as a calm, high-precision personal intelligence assistant.
Every surface is optimized for effortless scanning, trust, and situational awareness.
Deep obsidian and slate grounds recede into the background, allowing current tasks,
actionable recommendations, and conversational responses to shine with pure clarity.

## Color System

### AI & Cognition
- **AI Azure/Cyan** `#38BDF8` — Luminous provenance of machine intelligence, active assistant presence, and glowing aperture indicator. Dim partner `#0C4A6E`.

### Action & Status Semantics
- **GO Green** `#10B981` / `#34D399` — Positive focus states, active timers, completed milestones. Dim partner `#064E3B`.
- **Caution Amber** `#F59E0B` — Upcoming commitments, deadlines inside 24h, trade-off notes. Dim partner `#78350F`.
- **Critical Rose** `#F43F5E` — Overdue tasks, attention warnings, destructive actions. Dim partner `#881337`.

### Neutral Surfaces
- **Abyssal Void** `#080A0F` & **Ground** `#0D1117` — Deep neutral slate backdrops.
- **Panel** `#151B23` & **Raised** `#1F2631` — Soft, layered card and conversation surfaces.
- **Dividers** `#252D3A` & **Borders** `#354052` — Restrained borders with subtle contrast.
- **Ink** `#F0F6FC` — High-legibility primary text. Secondary `#94A3B8`, Faint `#64748B`.

## Typography & Hierarchy

1. **Display & Identity**: Chakra Petch — aperture mark, uppercase status headers (`.label-caps`), and button labels.
2. **Conversation & Body**: Barlow / System Sans — high readability, comfortable line-height (1.5) and balanced letter spacing.
3. **Telemetry**: JetBrains Mono — tabular numbers (`.tnum`) for clocks, timers, countdowns, and metrics.

## Components & Interaction

- **Current Task Header**: Minimalist typographic indicator placed at the top of the Home canvas to answer "What should I be doing right now?".
- **Conversational Stream**: Open, clutter-free chat with sleek user bubbles and readable assistant responses.
- **Floating Composer**: Bottom glassmorphic capsule (`backdrop-blur-xl bg-ops-panel/95 border-ops-line-bright/80`) with auto-resizing textarea and circular submit trigger.
- **Buttons**: Tactile `rounded-lg` with subtle hover elevations, active compression (`active:scale-[0.98]`), and luminous AI/GO variants.
