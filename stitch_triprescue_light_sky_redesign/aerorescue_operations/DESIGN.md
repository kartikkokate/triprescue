---
name: AeroRescue Operations
colors:
  surface: '#f8f9ff'
  surface-dim: '#c4dcfd'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eef4ff'
  surface-container: '#e4efff'
  surface-container-high: '#dbe9ff'
  surface-container-highest: '#d1e4ff'
  on-surface: '#011d35'
  on-surface-variant: '#404752'
  inverse-surface: '#19324b'
  inverse-on-surface: '#e9f1ff'
  outline: '#707783'
  outline-variant: '#c0c7d4'
  surface-tint: '#0061a7'
  primary: '#005ea3'
  on-primary: '#ffffff'
  primary-container: '#0077cc'
  on-primary-container: '#fdfcff'
  inverse-primary: '#a1c9ff'
  secondary: '#0060ac'
  on-secondary: '#ffffff'
  secondary-container: '#64a8fe'
  on-secondary-container: '#003c70'
  tertiary: '#00647c'
  on-tertiary: '#ffffff'
  tertiary-container: '#007f9d'
  on-tertiary-container: '#fafdff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d2e4ff'
  primary-fixed-dim: '#a1c9ff'
  on-primary-fixed: '#001c37'
  on-primary-fixed-variant: '#00487f'
  secondary-fixed: '#d4e3ff'
  secondary-fixed-dim: '#a4c9ff'
  on-secondary-fixed: '#001c39'
  on-secondary-fixed-variant: '#004883'
  tertiary-fixed: '#b7eaff'
  tertiary-fixed-dim: '#60d4fb'
  on-tertiary-fixed: '#001f28'
  on-tertiary-fixed-variant: '#004e61'
  background: '#f8f9ff'
  on-background: '#011d35'
  surface-variant: '#d1e4ff'
typography:
  display:
    fontFamily: Geist
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Geist
    fontSize: 30px
    fontWeight: '600'
    lineHeight: 38px
    letterSpacing: -0.015em
  headline-lg-mobile:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Geist
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 30px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: -0.005em
  body-lg:
    fontFamily: Geist
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-lg:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-md:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Geist
    fontSize: 10px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.04em
  data-mono:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: '0'
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.25rem
  gutter-mobile: 0.75rem
  margin: 2rem
  margin-mobile: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.25rem
---

## Brand & Style

This design system embodies the calm, lucid clarity of an unclouded flight corridor at 38,000 feet. Designed specifically for mission-critical travel disruption recovery and aviation resilience across India's dynamic transport network, it balances the razor-sharp precision of an operational control center (OCC) with the reassuring serenity of high-altitude light.

The emotional core is **controlled optimism and clarity under pressure**. When delays, weather anomalies, or missed connections disrupt itineraries, the interface must dissolve operational stress through an ultra-airy atmospheric palette, decisive typographic hierarchy, and unambiguous status signaling.

The aesthetic blends **Modern Corporate Operations with Weightless Glass-Air Minimalism**:
- **Atmospheric Luminance:** Pure whites layered over delicate sky gradients eliminate interface heaviness.
- **Precision Instrumentation:** Compact tabular data, crisp flight corridors, and telemetry-inspired telemetry badges inspired by flight navigation avionics.
- **Human-Centered Reassurance:** Soft rounded surfaces paired with high-contrast, deep navy type eliminate cognitive fatigue during emergency re-routing workflows.

## Colors

The color palette is built around airy tropospheric blue layers contrasted against deep maritime navy ink.

### Canvas & Surface Hierarchy
- **Base Background:** `#F3FAFF` stepping to `#EDF8FF` and `#E8F5FD` across secondary panels and canvas viewports.
- **Raised Surfaces / Cards:** Pure `#FFFFFF` with boundary borders in `#E2EDF4` and `#D9EAF5`.
- **Subtle Backdrops:** `#FCFEFF` for nested sub-cards and inner wells.
- **Pale Icy Tints:** `#DDF3FF` for interactive hover wells and active tab pill containers.

### Typography & Readability
- **Primary Ink:** `#102A43` (Deep Navy) delivers AAA contrast against pale sky backgrounds.
- **Secondary Ink:** `#486581` (Slate Blue) for operational metadata, route labels, and auxiliary descriptions.
- **Muted Ink:** `#829AB1` (Atmospheric Grey) for inactive labels, divider hints, and secondary axis markers.

### Accents & Gradients
- **Primary Aviation Blue:** `#228BE6` anchors actionable focal points.
- **Sky Gradient:** `#2F80ED` to `#56CCF2` used selectively on primary recovery triggers, progress indicators, and active journey markers.
- **Secondary Sky:** `#60A5FA` provides soft selection states and focus rings.

### Operational Semantic Status Tokens
- **Safe / Confirmed:** `#10B981` (Emerald) on `#ECFDF5` background.
- **At Risk / Weather Alert:** `#F59E0B` (Amber) on `#FEF3C7` background.
- **Broken / Conflict:** `#EF4444` (Vibrant Red) on `#FEF2F2` background.
- **Cancelled:** `#DC2626` (Deep Crimson) on `#FEE2E2` background.
- **Pending Manual Booking / Intervention:** `#8B5CF6` (Aviation Violet) on `#F5F3FF` background.
- **Dropped / Inactive:** `#94A3B8` (Cool Slate) on `#F1F5F9` background.

## Typography

The type system relies on **Geist**, leveraging its monoline geometry, clinical neutral phrasing, and engineered legibility for rapid data ingestion.

### Numerical & Tabular Data
- Always enable `font-feature-settings: "tnum" 1, "cv01" 1` for departure/arrival schedules, PNR identifiers, flight numbers, delay duration badges, and Indian Rupee (`₹`) fare structures. This prevents layout shifting during real-time web-socket telemetry updates.

### Hierarchy & Proportion
- **Headlines:** Set with tightened letter-spacing (`-0.01em` to `-0.02em`) to project operational authority and technical sophistication.
- **Labels & Micro-copy:** Formulated in medium and semi-bold weights with slight positive tracking (`+0.02em` to `+0.04em`) to ensure legibility when rendered as micro-capsules on status badges.
- **Responsive Handling:** Display-scale typography steps down systematically on handheld viewports to preserve density without wrapping vital aviation acronyms (e.g., DEL, BOM, BLR).

## Layout & Spacing

The layout model adapts a mission-control dual-plane framework: a persistent atmospheric utility header coupled with a multi-column modular workspace.

### Grid & Canvas Structure
- **Desktop (>= 1280px):** 12-column dynamic fluid layout with `1.25rem` (20px) gutters and max-width bounded at `1536px`. Supports simultaneous side-by-side operations: Route Disruption Ledger, Weather Digital Twin telemetry, and AI Alternative Resolver.
- **Tablet (768px - 1279px):** 8-column layout with `1rem` gutters; secondary telemetry blocks collapse into segmented slide-over sheets.
- **Mobile (< 768px):** 4-column layout with `0.75rem` gutters and `1rem` safe-margin edges. Recovery actions anchor to a floating bottom execution bar.

### Spacing Rhythm
Spacing distances follow an 8-point baseline rhythm. Tight intervals (`space-xs` and `space-sm`) structure the dense flight parameters (gate, terminal, aircraft type, runway queue times), while generous layout bounds (`space-lg` and `space-xl`) isolate actionable recovery decision panels, preventing visual crowding.

## Elevation & Depth

Visual hierarchy is maintained through daylight-inspired ambient backdrops, crisp 1px structural boundaries, and cool, low-saturation atmospheric drop shadows.

### Atmospheric Shadow Scale
- **Flat Surface (Level 0):** Used on canvas foundations (`#F3FAFF`). Borderless or bounded strictly by `#E2EDF4`.
- **Card Rest (Level 1):** `0 1px 3px 0 rgba(16, 42, 67, 0.04), 0 4px 12px 0 rgba(34, 139, 230, 0.05)`. Encased in a `1px solid #E2EDF4` border.
- **Card Hover / Focused Instrument (Level 2):** `0 4px 16px 0 rgba(16, 42, 67, 0.06), 0 8px 24px -4px rgba(34, 139, 230, 0.10)`. Border transitions to `#D9EAF5`.
- **Floating Overlays & Popovers (Level 3):** `0 12px 32px -4px rgba(16, 42, 67, 0.08), 0 20px 48px -8px rgba(34, 139, 230, 0.12)`. Applied to passenger rebooking drawers, quick trip switchers, and live AI impact overlays.

### Translucent Glass Layers
- Sticky navigation headers and pinned status bars use a daylight frost effect: `background: rgba(255, 255, 255, 0.85); backdrop-filter: blur(12px); border-bottom: 1px solid #E2EDF4;`.

## Shapes

The geometry strikes a deliberate synthesis of aerospace aerodynamic curvature and precise software ergonomics.

- **Primary Container Radius:** Primary operational cards, data consoles, and dialogs utilize an exact `16px` (`1rem`) border radius (`rounded-lg`).
- **Interactive Micro-Elements:** Buttons, input fields, dropdown trigger buttons, and segment tabs adopt an `8px` (`0.5rem`) corner radius (`rounded`).
- **Pill Geometry:** Segmented mode selectors, status indicator chips, live connection indicators, and flight leg transit nodes adopt full-pill bounds (`9999px`).
- **Dividers & Connectors:** 1px stroke geometry, rendered in `#E2EDF4`, with dotted or dash variants applied specifically to simulated alternate flight paths.

## Components

### 1. Navigation & Utility Bar
- **Brand Wordmark:** Deep navy (`#102A43`) for "Trip" paired with vibrant aviation blue (`#228BE6`) for "Rescue".
- **Segmented Capsule Bar:** An icy-tinted pill track (`#E8F5FD`) housing items: "Trip Builder", "Recovery Console", "Weather Digital Twin", "Monitoring", and "AI Model". Active item is pure `#FFFFFF` with faint shadow `0 2px 6px rgba(16, 42, 67, 0.06)` and `#102A43` semi-bold text.
- **Live Backend Node:** A micro-capsule featuring a pulsing `6px` emerald green (`#10B981`) ping indicator beside tabular text (`"CONNECTED: 42ms"`).
- **Trip Selector & Notifications:** Bordered button triggers (`#FFFFFF`, border `#E2EDF4`) with deep navy text and unread count badges in primary blue.

### 2. Buttons
- **Primary Recovery CTA:** Gradient fill (`linear-gradient(135deg, #2F80ED 0%, #56CCF2 100%)`), text `#FFFFFF`, font weight `600`, with faint blue halo on hover (`box-shadow: 0 4px 14px rgba(34, 139, 230, 0.3)`).
- **Secondary Operations:** Solid `#FFFFFF`, border `1px solid #D9EAF5`, text `#102A43`. Hover transitions to `#F3FAFF` surface with `#228BE6` border.
- **Destructive / Abort Action:** Subtle `#FEE2E2` fill, text `#DC2626`, border `1px solid #FCA5A5`.

### 3. Status Badges & Chips
- Compact pills with a height of `24px` and horizontal padding of `10px`.
- Built with a `6px` solid status beacon dot and semibold uppercase micro-type:
  - *Safe:* Dot `#10B981`, background `#ECFDF5`, text `#065F46`.
  - *At Risk:* Dot `#F59E0B`, background `#FEF3C7`, text `#92400E`.
  - *Broken:* Dot `#EF4444`, background `#FEF2F2`, text `#991B1B`.
  - *Cancelled:* Dot `#DC2626`, background `#FEE2E2`, text `#7F1D1D`.
  - *Pending Manual:* Dot `#8B5CF6`, background `#F5F3FF`, text `#5B21B6`.
  - *Dropped:* Dot `#94A3B8`, background `#F1F5F9`, text `#475569`.

### 4. Input Fields & Selectors
- Background `#FFFFFF`, border `1px solid #E2EDF4`, height `40px`, padding `0 12px`.
- Placeholder text in `#829AB1`.
- Active focus state: border `#228BE6`, outline `3px solid rgba(34, 139, 230, 0.15)`.
- Currency inputs automatically prefix the Indian Rupee symbol (`₹`) in fixed tabular spacing with `#486581` secondary text.

### 5. Cards & Journey Consoles
- Surfaces are `#FFFFFF` wrapped with a delicate `1px solid #E2EDF4` contour and `16px` border radius.
- Headers contain flight routing coordinates (e.g., `DEL → BLR`), current flight status chip, and AI confidence telemetry metric.
- Section dividers within cards utilize a clean 1px solid rule in `#F3FAFF`.

### 6. Checkboxes & Radio Controls
- Radio & Checkbox bounds are `18px × 18px` with `1.5px` border in `#CBD5E1`.
- Selected state fills with `#228BE6` carrying a pure white icon/inner dot, accented by a subtle soft sky focus halo.