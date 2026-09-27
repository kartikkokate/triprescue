# TripRescue: UI/UX redesign prompts for Google Stitch

How to use: paste **Part 0** first in every Stitch session (it sets the design system), then paste
ONE screen prompt at a time (Parts 1–7). Part 8 is not for Stitch: it maps every button to the
existing backend API, so the generated screens can be wired without changing the backend.

---

## Part 0: Global brief (paste first, every time)

Design a web app called **TripRescue**, an intelligent travel disruption recovery platform for
travelers in India. A trip is a connected chain of bookings (flights, trains, cabs/transfers,
hotels, activities). When one booking is delayed or cancelled, the app shows what else breaks,
generates feasible recovery plans, explains them, and predicts weather risk with a live
"digital twin". It never books or pays; it tells the traveler exactly what to book themselves.

Users: stressed travelers, mid-trip, often on a phone. Also hackathon judges on a laptop.
The UI must feel calm, trustworthy and fast to read under stress.

Design system:
- Dark theme. Background near-black navy (#0B1220), surfaces slate (#0F172A / #111827), 1px
  borders (#1F2937 / #334155), 12–16px rounded corners, soft inner glow on focused cards.
- Brand gradient indigo (#6366F1) to cyan (#06B6D4) for primary actions and the active nav item.
  Logo wordmark "Trip" white + "Rescue" cyan.
- Status colors used everywhere, consistently: Safe = green #22C55E, At risk = amber #F59E0B,
  Broken = red #EF4444, Cancelled = deep red #B91C1C with a strike-through label,
  Pending manual booking = violet #A78BFA, Dropped = grey.
- AI-model badge colors: "Nugen-aligned" = fuchsia #D946EF, "Gemini (fallback)" = emerald,
  "Rule-based" = slate.
- Type: Inter or Geist. Numbers (money, minutes, %) in tabular figures. Money is INR shown as
  "₹4,500"; signed deltas "+₹2,000" (red) / "−₹350" (green).
- 12-column grid on desktop (1280–1440px, 24px gutters), 8-column tablet, single column mobile
  (360–430px). Minimum touch target 44px.
- Motion: 200–300ms ease-out. Screen changes cross-fade + 12px slide. Cards stagger in (40–80ms).
  Progress bars and gauges animate from 0. Live indicators use a slow pulse. Respect
  prefers-reduced-motion.
- Every data area has four designed states: loading (skeleton shimmer), empty (friendly
  one-line explanation + primary action), error (inline red banner with retry), and live/success.

Global layout (all screens):
- Sticky top bar: logo left, then the main navigation as a segmented pill control with an
  animated sliding highlight: **Trip Builder · Recovery Console · Weather Digital Twin ·
  Monitoring · AI Model**. On mobile the nav becomes a bottom tab bar with icons.
- Right side of the top bar: active trip name chip (click opens Trip Switcher), a notification
  bell with an unread-count badge (opens the Alerts drawer), and a small connection dot
  (green = backend live, grey = offline).
- A toast area top-center for confirmations ("Scenario applied to your real trip").
- Each screen can be deep-linked with a URL hash: #builder, #console, #twin, #monitor, #ai.

Tone of copy: short, plain, reassuring. Never claim something was booked or paid.

---

## Part 1: Trip Builder screen (#builder)

Purpose: the traveler enters their own trip instead of using the demo trip. Every booking has
the price and terms the traveler actually paid.

Layout (desktop): two columns, 7/5 split.

Left column: "Your bookings" editor
- Header row: trip name text field (default "My Trip"), button "Load demo trip (Delhi → Goa)",
  button "Clear all".
- Vertical list of booking cards sorted by start time, with drag handles. Each card is
  collapsible and shows, collapsed: type icon, title, start → end, price, status chip.
- "+ Add booking" split button with a type menu: Flight, Train, Cab / Transfer, Hotel,
  Activity, Event.
- Expanded booking card form fields (grid, 2 columns):
  - Type (select), Title, Provider
  - Start date-time, End date-time
  - Location (place name) and, for flights/trains/cabs, Destination (place name)
  - Price paid (₹), Cancellation policy (select: Free until 24 h before / 50% refund /
    Non-refundable), Fixed cancellation penalty (₹, optional, overrides the policy),
    Refund comes back as (segmented: Cash / Provider credit / None)
  - Flight or train number (for live status checks, e.g. "6E204")
  - Toggle "Outdoor / weather-sensitive" (activities)
  - Collapsible "Known alternatives (optional)" sub-table: title, provider, price, starts
    how many minutes later, rating 0–100, action (Keep / Reschedule / New booking / Book
    yourself), next-day toggle, weather-safe toggle; add/remove rows.
- Inline validation: end before start, missing price, duplicate names.

Right column: "Trip preview" (sticky)
- A small vertical timeline of the bookings with the inferred connections between them,
  each connection labelled with its type (Transfer required / Check-in / Same day / Sequential)
  and the minimum buffer in minutes. Tight gaps get an amber "tight" tag.
- Toggle "Let TripRescue infer connections" (default on). When off, show an editable list of
  connections: from booking, to booking, type, buffer minutes.
- Summary card: total trip cost, number of bookings, cities (auto-detected), days.
- Primary button (full width, gradient): "Use this trip". Secondary: "Save as named trip".
- After success: toast "Trip loaded. Monitoring and the digital twin now follow this trip"
  and a button to go to the Recovery Console.

Mobile: preview becomes a bottom sheet with a "Preview" handle.

---

## Part 2: Recovery Console screen (#console)

Purpose: see the trip as a connected graph, trigger or receive a disruption, and choose a
recovery plan. This is the main demo screen.

Top strip (full width):
- Trip header: trip name, route summary ("Delhi → Goa · 10–12 Oct"), persistence badge
  ("Saved to cloud" or "Not saved"), buttons "Save", "Trips…", "Reset trip".
- Proactive warnings row: horizontally scrollable chips, each with severity (Medium/High)
  and a sentence like "Only 15 min between 'Airport → Hotel' and 'Hotel check-in'". Clicking a
  chip highlights that connection in the graph.

Main grid (desktop 12 cols):
- Left 8 cols: **Itinerary graph** card.
  - Left-to-right node-link diagram. Each node is a card: type icon + label (FLIGHT, CAB,
    HOTEL, ACTIVITY), title, date-time, price, and a status pill in the status colors.
    Pending-manual-booking nodes get a violet dashed border and a "Book yourself" tag.
  - Edges are arrows labelled with type and buffer ("transfer · 30 min"). Edges into broken
    nodes turn red, into at-risk nodes amber.
  - Zoom / fit / fullscreen controls. Clicking a node opens a side panel with all booking
    details and its refund terms.
  - Legend chips for the statuses.
- Right 4 cols: stacked cards
  1. **Trigger a disruption** (tabs: Booking · Weather)
     - Booking tab: booking select, type segmented (Delay / Cancel), delay minutes stepper
       (when Delay), reason select (when Cancel: Operator cancellation, Weather, Traveler
       request, Overbooked), red button "Trigger disruption". For flights: flight number field
       + secondary button "Check real flight status" with a result line
       ("6E204: scheduled, 0 min delay, no disruption suggested").
     - Weather tab: day select (trip days), severity segmented (Moderate: delays outdoor plans /
       Severe: cancels outdoor plans), secondary button "Check real forecast" with result line,
       blue button "Trigger weather event".
  2. **Traveler preferences**: preset chips (Balanced, Save money, Save time, Maximize
     comfort) and an expandable "Customize" area with four sliders (Cost, Time, Convenience,
     Minimize disruption, shown as % weights that sum visibly), "Minimum acceptable rating"
     slider 0–100, toggle "Avoid pushing to the next day", button "Save preferences".

Impact banner (appears after a disruption, full width, slides down): headline
("IndiGo 6E-204 cancelled"), counts of broken / at-risk / safe bookings, and three buttons
from the AI advisor.

**AI recovery advisor** card (full width):
- Model provenance line under the title ("Llama 3.2 3B → Nugen alignment → TripRescue Advisor",
  or "Nugen model not deployed yet: using fallback").
- Three buttons: "Explain what happened", "Explain recovery plans", "Know your rights".
- Each answer appears as its own block with a heading (What happened / Recommendation /
  Your rights & next steps) and a colored model badge. Loading shows a thin animated bar.

**Recovery plans** section (full width):
- Header: "Recovery plans" + analysis line ("12 combinations checked · 12 feasible"). If some
  were rejected, a disclosure "Why some options were rejected" listing reasons like
  "you would miss Water Sports Session (15:00)".
- Plan cards in a 3-column grid (1 column on mobile), ordered: Best Balanced, Cheapest,
  Fastest, then Alternatives. A plan can carry several badges (e.g. BALANCED + FASTEST).
  Each card:
  - Title + badges; big score "89.8 / 100".
  - Key metrics row: Net cost (signed ₹), Lateness (min), Convenience (/100), Trip changed (%).
  - "Why this score" expandable: four horizontal bars (Cost, Time, Convenience, Disruption)
    showing each one's weight and points contributed; the points add up to the score.
  - Money breakdown: Penalties, Cash refund, Provider credit, New spend, Net cash.
  - Digital-twin reliability bar: "Holds up under the forecast: 97%" plus risk notes.
  - Options list, one row per affected booking: action pill (Keep / Reschedule / New
    booking / Book yourself / Drop), replacement title, provider, new time, price, price vs
    what you paid (+₹/−₹), price source tag (Your price / Catalog / Estimate), and
    "market price: unavailable" in small grey text.
  - "What you'll need to do" checklist (action items).
  - Primary button "Choose this plan" and a confirm step: "This updates your itinerary.
    TripRescue will not book or pay; you'll book the items marked 'Book yourself'."
- After choosing: graph animates back to green, replaced nodes show "Pending manual booking",
  and a checklist panel stays pinned until each item is ticked.

---

## Part 3: Weather Digital Twin screen (#twin)

Purpose: a live, probabilistic simulation of how weather will affect this trip and the local
hospitality ecosystem, with what-if scenarios that never touch the real trip.

Top row (3 cards + 1 status card):
- One card per trip place (auto-detected, e.g. Goa, Delhi): current temperature, condition
  icon + text, rain mm/h, wind km/h, and "Social signal" % (share of recent public
  weather-disruption reports).
- Live twin status card: pulsing green dot "LIVE TWIN", "updated 3 min ago", a sparkline of
  trip risk over recent refreshes, "9 forecast points · 400 simulations", refresh button.

Main grid: map left (8 cols), what-if simulator right (4 cols).
- **Map** (dark basemap): each booking is a circular marker colored by risk (green → amber →
  red) with a ping animation when risk is high; transport legs are animated dashed routes; each
  place has a translucent rain circle sized by rain intensity with a label "Goa · 35 mm/h".
  Controls: "Local view / Route view" toggle, zoom. Bottom-left badge: "LIVE FORECAST" (green)
  or "WHAT-IF SCENARIO (simulated)" (amber). Marker popup: booking, broken % / at-risk %,
  delay p50 / p90, weather at that booking.
- **What-if simulator** card:
  - Badge "Sandbox: your real trip is untouched".
  - Preset grid (3×2 buttons with icons): Live forecast, Normal day, Heavy monsoon, Flash flood,
    Cyclone, Heatwave.
  - Sliders, each showing "live" until moved and a reset ↺ icon: Rainfall intensity 0–100 mm/h,
    Storm duration 0–48 h, Temperature 15–48 °C, Wind speed 0–150 km/h, Flooding 0–100%.
  - Selects: Where (Everywhere / each place), When (Whole trip / each trip day).
  - Results update live about 0.3 s after a change (show a subtle "simulating…" state).
  - When risk ≥ 30%: warning-gradient button "Apply this scenario to my real trip →"
    with a confirm step; on success go to the Recovery Console with a toast.

Below the map (8 cols):
- **Trip risk gauge**: big radial gauge "Chance any booking breaks: 97%", delta vs live
  ("▲ 88% vs live forecast"), expected loss ₹ and expected extra delay.
- **Selected booking weather** card (click a marker or row): rain + probability, wind, temp,
  flood %, storm hours, most likely outcome, main driver.
- **Bookings under this weather**: one row per booking with a stacked probability bar
  (safe / at risk / broken), delay range "p10–p90: 0–238 min", driver chip (rain / wind / heat
  / flooding / storm / social reports), and change vs live (+/−%).
- Two side-by-side cards:
  - **Cascade of effects**: three labelled groups: 1st order (weather → booking),
    2nd order (booking → dependent booking), 3rd order (ecosystem → recovery options), each
    item with a sentence and a probability; items reveal in order with a stagger.
  - **Hospitality ecosystem**, per place: small metric tiles for Road travel time (×),
    Cab availability, Hotel occupancy, Outdoor attraction demand, Indoor venue demand, Dine-in
    restaurant demand, Hospitality workforce; each with value and an 80% interval bar.

Right column below the simulator (4 cols):
- **AI twin briefing**: "Brief me" button; answer with model badge.
- **Real-world social signals**: place tabs; category chips with counts (heavy rain, storm,
  flooding, heat, transport disruption); a scrollable feed of items (source, author, time ago,
  categories, link out). Empty state: "No weather reports in the last 72 h".
- **Continuous learning**: three tiles (Flight / Transfer / Activity) showing the learned
  "minutes of delay per mm/h of rain ± uncertainty" and observation count; a form "Booking +
  Observed delay (min) + Feed observation"; a list of recent observations
  ("predicted 1.7 → now 4.4 min").

Mobile: map on top (fixed height), simulator as a bottom sheet, other cards stacked.

---

## Part 4: Monitoring & Alerts screen (#monitor) + Alerts drawer

Purpose: show that TripRescue checks real providers every 20 minutes and alerts the traveler
only once per real change.

Top row:
- **Scheduler card**: "Checks every 20 min" (interval), mode (In-app timer / External cron),
  last run time and trigger, next run countdown, and buttons "Run check now" and, under an
  "Advanced" disclosure, "Replay as if it were…" (date-time picker) for demos.
- **Last run summary**: counts as colored chips: OK, Skipped, Unavailable, Error; new alerts;
  duplicates suppressed.

Main area (12 cols):
- **Provider health table** (8 cols): one row per provider × booking: provider (AviationStack,
  Open-Meteo, Road (derived from weather), Indian Railways, Hotel), booking, status pill
  (OK / Skipped / Unavailable / Error), checked at, fresh until (turns grey when stale), and an
  expandable evidence JSON rendered as key–value chips (e.g. flight 6E204 · status scheduled ·
  delay 0). Filter chips by status and by provider. Explain unavailable rows in plain words
  ("No free live train-status API: enter delays manually").
- **Open events** (4 cols): cards for detected disruptions not yet handled: severity, booking,
  kind (Delay ~150 min / Cancellation), reason, source, detected at; buttons "Apply to my trip"
  (then shows the recalculated plans) and "Dismiss".

**Alerts drawer** (global, from the bell icon; right-side sheet on desktop, full screen on
mobile):
- Tabs: All / Unread. Each alert: severity color bar, title ("IndiGo 6E-204: cancellation"),
  message, source + time, an "Impact" line of status pills for affected bookings, and a mini
  "Plans preview" list (label, badges, net ₹, lateness) with "Open in Recovery Console".
  Mark as read on open. Real-time alerts slide in with a soft sound-free pulse on the bell.

---

## Part 5: AI Model screen (#ai)

Purpose: prove the hackathon requirement "Base AI model → Nugen alignment → domain-specific
model → integration into the project".

- **Model provenance pipeline** (full width): five connected step cards with animated arrows:
  1 Base model (Llama 3.2 3B Reasoning), 2 TripRescue dataset (826 samples, 145 held-out
  benchmark questions), 3 Nugen alignment (alignment ID), 4 Domain-specific model (model ID),
  5 Integrated in TripRescue. Each step shows status: complete (green check), in progress
  (amber pulsing outline), pending (grey), or failed (red, listing the failed alignment job
  IDs so they can be shown to the Nugen team).
- Two cards side by side:
  - **What the model was aligned on**: horizontal bars per task with counts: Impact
    explanation, Traveler rights (DGCA / rail / policy), Plan recommendation, Weather
    digital-twin briefing, Travel policy knowledge. Short note: "Every sample pairs the exact
    prompt the app sends with an answer computed by our own engines".
  - **Where it runs in the app**: list of the four in-app features with the screen and button
    they live on; a "Test it on the live twin" button showing the answer and which model
    answered.
- **Evaluation** card (only when available): base vs aligned bars per metric from Nugen's
  held-out benchmark.
- Fallback explainer: "If the aligned model is unreachable, answers fall back to Gemini, then
  to rule-based text. Every answer shows which one replied."

---

## Part 6: Trip Switcher modal (global)

- Opened from the trip chip in the top bar or "Trips…" on the console.
- Shows "Stored in: Cloud (Supabase)" or "In memory".
- Field "New trip name" + "Save current trip as new".
- List of saved trips (name, last updated) with "Load" and "Delete" (confirm) actions; the
  active trip is marked. Empty state: "No saved trips yet".

---

## Part 7: Shared components to design once

- Status pill (Safe / At risk / Broken / Cancelled / Pending manual booking / Dropped).
- Model badge (Nugen-aligned / Gemini fallback / Rule-based).
- Money value (signed, colored) and Money breakdown table.
- Score bar with contribution segments.
- Probability stacked bar (safe / at risk / broken) with legend.
- Interval bar (mean marker + 10–90% band).
- Provider status pill (OK / Skipped / Unavailable / Error) + freshness dot.
- Evidence chip list (key · value).
- Toast, inline error banner with Retry, skeleton loaders, empty states.

---

## Part 8: Wiring map (for the developer, not for Stitch)

Base URL `http://localhost:8000` (or `VITE_API_BASE_URL`). WebSocket `ws://…/ws/risk-feed` sends
three message kinds: `{"type":"twin_update", trip, history}`, `{"type":"monitor_alert", …notification}`,
and legacy simulated traffic events (no `type` field; the old simulated feed can be dropped).

| Screen / control | API |
|---|---|
| Builder · Use this trip | `POST /api/itinerary` `{name, bookings:[{type,title,start,end,cost,provider,location,destination?,cancellation_policy,cancellation_penalty?,refund_mode,service_code?,weather_sensitive,lat?,lon?,dest_lat?,dest_lon?,alternatives:[{title,provider,cost,start_offset_minutes,duration_minutes?,rating,action?,next_day?,weather_safe?,notes}]}], dependencies?:[{source,target,type?,buffer_minutes?}], geocode}` → `{itinerary}`; 400 with `detail` on bad input |
| Builder · Load demo trip / Console · Reset | `POST /api/reset` |
| Graph data | `GET /api/itinerary` → `{nodes:[{id,type,title,location,start,end,cost,provider,cancellation_policy,status,weather_sensitive,lat,lon,dest_lat,dest_lon,cancellation_penalty,refund_mode,service_code,booking_status,alternatives}], edges:[{source,target,type,buffer_minutes}]}` |
| Proactive warnings | `GET /api/risk-scan` → `{warnings:[{node_id,title,message,severity}]}` |
| Trigger disruption | `POST /api/disrupt` `{node_id, kind:"delay"|"cancel", delay_minutes, reason}` |
| Trigger weather event | `POST /api/disrupt-weather` `{date, severity:"moderate"|"severe"}` |
| Check real flight status | `GET /api/flight-status?flight_iata=6E204` |
| Check real forecast | `GET /api/weather-check?location=Goa&date=2026-10-11` |
| Preferences | `GET` / `PUT /api/preferences` `{cost_weight,time_weight,convenience_weight,disruption_weight,min_rating,avoid_next_day}` (presets: Balanced .2/.3/.4/.1; Save money .7/.1/.1/.1; Save time .1/.7/.1/.1 + avoid_next_day; Maximize comfort .05/.15/.7/.1 + min_rating 70) |
| Recovery plans | `GET /api/recovery-plans` → `{plans:[{id,label,category,badges,score,score_breakdown:{cost|time|convenience|disruption:{value,unit,normalized,weight,contribution}},money:{penalty,cash_refund,credit,lost,new_spend,net_cash,net_after_credit},total_cost_delta,total_time_delta_minutes,convenience_score,pct_itinerary_affected,refund_recovered,options:[{node_id,replacement_title,provider,cost,start,end,notes,action,requires_manual_booking,price_source,original_cost,price_vs_original,market_price,market_price_source}],action_items}], analysis:{combinations_checked,feasible,infeasible_examples}}` |
| Plan twin reliability | `GET /api/twin/plan-risk` → `{plans:{[plan_id]:{p_success,risks}}}` |
| Choose this plan | `POST /api/apply-plan/{plan_id}` |
| AI advisor buttons | `GET /api/explain-impact`, `GET /api/explain-plans`, `GET /api/traveler-rights` → `{explanation, source, model:"nugen-aligned"|"gemini"|"rule-based"}` |
| Trip switcher | `GET /api/trip-status`, `GET /api/trips`, `POST /api/trips {name}`, `POST /api/trips/{id}/save`, `POST /api/trips/{id}/load`, `DELETE /api/trips/{id}` |
| Twin live state | `GET /api/twin/state?refresh=false|true` → `{updated_at, trip, nodes, ecosystem, effect_chain, places, sources, history, learner, samples}` |
| What-if | `POST /api/twin/simulate` `{overrides:{rain_mm_h?,storm_hours?,temp_c?,wind_kmh?,flood_index?,social_index?}, target_place:"all"|<place>, target_date:null|"YYYY-MM-DD"}` → twin result + `baseline_trip`, `delta_vs_live` |
| Brief me | `POST /api/twin/explain` (same body or `null` for live) |
| Feed observation | `POST /api/twin/observe` `{node_id, delay_minutes}` |
| Apply scenario to real trip | `POST /api/twin/promote` (scenario body) |
| Social feed | `GET /api/twin/social?place=Goa` (also inside twin state `places[*].social`) |
| Monitoring status | `GET /api/monitor/status` → `{interval_minutes, scheduler, last_run, open_events, unread, providers:[{provider,category,node_id,status,checked_at,fresh_until,fresh,evidence}]}` |
| Run check now / Replay | `POST /api/monitor/run?now=2026-10-10T07:00:00` (header `X-Monitor-Token` if configured) |
| Alerts drawer | `GET /api/notifications?unread_only=false`, `POST /api/notifications/{id}/read` |
| Open event actions | `POST /api/monitor/events/{event_id}/apply` → `{itinerary, impact_report, plans}`; `POST /api/monitor/events/{event_id}/dismiss` |
| AI Model screen | `GET /api/ai-model` → `{active_tier, nugen_model_id, pipeline, dataset:{train_samples, benchmark_questions, by_task}}` |
