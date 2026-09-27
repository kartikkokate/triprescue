# Travel Disruption Recovery Engine

Intelligent travel resilience platform — models a trip as a connected itinerary graph,
detects disruptions, propagates downstream impact, and generates ranked recovery plans.

## Structure

```
backend/    FastAPI service — graph engine, impact propagation, recovery generation
frontend/   React + TypeScript dashboard — itinerary graph, disruption trigger, plan comparison
```

## Quickstart

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Frontend runs on http://localhost:5180 (not Vite's default 5173), talks to backend on http://localhost:8000. Screens: `#console`, `#twin`, `#ai`.

### Tests
```bash
cd backend
pip install -r requirements-dev.txt
pytest
```
56 tests across graph traversal, impact propagation (delay/cancel/weather cascades),
recovery-plan generation and preference weighting, the LLM-explainer fallback path, the
live-monitor background job, trip persistence, external-API fallback behavior, and full API
integration tests via FastAPI's `TestClient`. Each test gets an isolated `AppState` (or the
shared singleton and in-memory trip store are reset before/after every test via an autouse
fixture), so nothing leaks between tests regardless of order. No network calls or API keys
required — every external integration (LLM, weather, flights, Supabase) is tested via its
documented fallback path, not a live call.

## Demo flow
1. Load itinerary (seeded trip: Delhi → Goa, 3 days, flights + transfers + hotel + activities)
2. Trigger a disruption (e.g. delay `FL1` by 180 minutes)
3. See downstream nodes flip to `at_risk` / `broken` on the graph
4. Generate recovery plans, compare cost/time/convenience
5. Click "Explain what happened" / "Explain recovery plans" for a plain-English summary
6. Apply a plan → itinerary updates, graph turns green
7. Run a proactive risk scan → warnings for tight connections
8. Trigger a weather event (a whole day at once) or an activity cancellation with reason "weather" → recovery plans favor indoor alternatives
9. Watch the "Live proactive monitor" panel — a background job simulates live traffic conditions on same-day transfers and pushes new risk warnings the moment a buffer looks like it's eroding, with no manual trigger. Click "Simulate this delay now" on any event to turn the forecast into a real disruption and run the recovery flow
10. Open "Traveler preferences" and switch presets (Save money / Save time / Maximize comfort) or customize the weight sliders → the "Matched to Your Preferences" plan and the ranking of all plans update accordingly

## Recovery engine, money and monitoring (backend)

**Your own trip** - `POST /api/itinerary` replaces the demo trip with the traveler's bookings:
type, times, **user-entered price**, `cancellation_policy`, optional fixed `cancellation_penalty`,
`refund_mode` (`cash` / `credit` / `none`), `service_code` (flight/train number), coordinates or place
names (geocoded), and optional replacement `alternatives`. Dependencies are inferred from the timeline
(flight -> transfer needs 30 min, anything -> flight needs check-in time, ...) unless given; buffers never
exceed the traveler's own gaps.

**Recovery** (`GET /api/recovery-plans`) - deterministic, no LLM:
- every combination of one option per broken booking (including *keep the delayed booking*) is generated
- each is checked for **feasibility**: flights, trains and activity slots run at fixed times and can be
  missed; cabs and hotel check-in wait for the traveler; infeasible combinations are rejected with a reason
- money per plan: penalties, cash refund, provider credit, new spend, net cash. A provider cancellation
  means a full refund and a free same-provider reschedule; a traveler cancellation follows the booking's
  terms, and free-cancellation windows are respected
- plans come as **Best Balanced / Cheapest / Fastest / alternatives**, each with an explainable score
  (per-objective value, normalized value, weight and contribution)
- **nothing is booked or paid**: plans carry action items; applied replacements stay
  `pending_manual_booking`. Cabs have no live API, so every cab replacement is a manual booking
- replacement prices are labelled `user-entered` / `catalog` / `estimate`; `market_price` stays empty
  (`unavailable`) until a live fare API is configured - nothing is invented

**Proactive monitoring** - every 20 min (`MONITOR_INTERVAL_MINUTES`) on a light in-process timer, or from
an external cron via `POST /api/monitor/run` (set `MONITOR_SCHEDULER=off`, `MONITOR_CRON_TOKEN`):
- flights: AviationStack live status, only within 24 h of departure (protects the free quota)
- weather and flooding: Open-Meteo at each booking; roads/cabs are inferred from it (no live cab or traffic
  API): severe weather -> "existing cab unsafe, new cab required, book it yourself"
- rail and hotels: reported as `unavailable` (no free public status API), never faked
- each signal gets a **fingerprint**; repeats are suppressed, a worse signal alerts again
- a new alert carries the recalculated impact and recovery plan scores (computed on a copy); the traveler
  applies it with `POST /api/monitor/events/{id}/apply` or dismisses it
- `GET /api/monitor/status` shows the last run and every provider's status, freshness and evidence;
  `GET /api/notifications` lists alerts; a failing provider is recorded as `error` and never crashes a run

## Weather digital twin (HackCelestial midnight task)

An AI simulation layer inside the existing app (the **Weather Digital Twin** screen), not a separate product:

- **Live weather**: Open-Meteo hourly forecast (16 days) + GloFAS river-discharge flood forecast, per booking
  location and time. No API key needed.
- **Social signals**: public Mastodon hashtag posts + Google News reports for each place, filtered to real
  weather reports and classified (flooding / heavy rain / storm / heat / transport disruption). Their volume is a
  model feature, and fades with how far away the booking is.
- **Model**: per booking type, a Bayesian regression of delay on weather (rain, wind, heat, flooding, storm
  duration, social index), starting from expert priors and **updated as real observations arrive**
  (weather-caused disruptions, live flight-status checks, traveler reports). Cancellation hazards are logistic.
- **Simulation**: 400 Monte Carlo futures per run, pushed through a *copy* of the real itinerary graph with the
  app's own impact engine, so cascades follow the same dependency rules. Output: P(safe / at risk / broken) and
  p10–p90 delay per booking, trip-level risk and expected INR loss, a 1st/2nd/3rd-order effect chain, and
  ecosystem state per place (road time, cab availability, hotel occupancy, outdoor/indoor demand, dine-in demand,
  workforce), each with an 80% interval.
- **What-if / counterfactual**: sliders for rain, storm duration, temperature, wind, flooding, place and day,
  plus presets (normal day, monsoon, flash flood, cyclone, heatwave), each compared against the live forecast.
  The real trip is never touched unless you press *Apply this scenario to my real trip*, which hands it to the
  normal recovery flow.
- **Continuous**: re-simulated every 10 minutes and pushed over the websocket. Recovery plan cards show how
  likely each plan is to hold up under the forecast.
- **Nugen tie-in**: *Brief me* asks the Nugen-aligned advisor (task `WEATHER_TWIN`, 101 training samples).

API: `GET /api/twin/state`, `POST /api/twin/simulate`, `POST /api/twin/explain`, `POST /api/twin/observe`,
`POST /api/twin/promote`, `GET /api/twin/plan-risk`, `GET /api/twin/social?place=Goa`.

## Nugen domain-aligned model (TripRescue Advisor)

Base model → **Nugen alignment** → domain-specific **TripRescue Advisor** → used for inference in the app.

- **Dataset** (`backend/nugen/build_dataset.py`): 825 training samples generated by running our own impact
  and recovery engines over every booking × 13 delay lengths, cancellations and weather events, across 3
  connection-buffer settings and 4 traveler-preference profiles, plus Indian traveler-rights knowledge
  (DGCA cancellation/delay/denied-boarding rules, railway refunds, booking policies). Answers come from the
  engine itself, so they are correct by construction.
- **Held-out benchmark** (145 questions) is uploaded separately and never trained on; Nugen evaluates the
  aligned model against the base model on it.
- **Same prompt format in training and serving**: `app/advisor_prompts.py` builds the prompts for both, so
  the model is served exactly the inputs it was aligned on.
- **Pipeline** (`backend/nugen/align.py`, resumable, ids recorded in `backend/nugen/state.json`):

```bash
cd backend
python -m nugen.build_dataset                 # generate dataset + benchmark
python -m nugen.align base-models             # choose a base model
python -m nugen.align run --base-model <id>   # upload -> align -> deploy, writes NUGEN_MODEL_ID to .env
```

- **In the app**: `/api/explain-impact`, `/api/explain-plans` and `/api/traveler-rights` ask the aligned model
  first, then Gemini, then the rule-based expert answers. Each response says which one answered (`model`), and
  `/api/ai-model` shows the aligned model's provenance.

## LLM explanation layer

`POST /api/explain-impact` and `POST /api/explain-plans` use Gemini (`gemini-flash-lite-latest` by default,
override with `GEMINI_MODEL`) to turn the structured impact report / recovery plans into a short
natural-language explanation. Set `GEMINI_API_KEY` in `backend/.env` to enable it:

```bash
GEMINI_API_KEY=...   # from https://aistudio.google.com/apikey
```

Without a key (or if the call fails for any reason), both endpoints transparently fall back to a
rule-based summary built from the same data — the response includes `"source": "llm"` or
`"source": "rule-based"` so the UI can show which one ran. The demo works either way.

## Live proactive monitor

A background task (`app/live_monitor.py`, started on app startup) runs every 8 seconds and simulates
live traffic conditions on same-day transfer legs — a bounded random walk with a slight upward drift
and an occasional "traffic clears" reset. When the simulated estimate crosses 50%/80% of a
transfer's buffer, it pushes a `medium`/`high` risk event over `ws://localhost:8000/ws/risk-feed`
(history also available via `GET /api/risk-feed`). This is a forecast signal only — it never
mutates booking status on its own; the frontend's "Simulate this delay now" button is what turns it
into a real disruption via the existing `/api/disrupt` flow. This is what makes the risk scanner
"proactive" rather than purely reactive: warnings can surface before the traveler does anything.

## Traveler preferences

`GET`/`PUT /api/preferences` store weights (cost, time, convenience, minimize-itinerary-disruption)
plus two hard filters (minimum acceptable alternative rating, avoid next-day pushes). These feed
`generate_recovery_plans` in two places:

- A 4th strategy, **"Matched to Your Preferences"**, picks per-node alternatives by a locally
  normalized weighted score (cost/time min-max normalized within that node's own candidate list,
  since a flight's cost scale and a transfer's cost scale aren't comparable).
- The final ranking **score** for all four plans (including the canned fastest/cheapest/most-convenient
  ones) uses the traveler's weights instead of a fixed formula, so preferences change which plan comes
  out on top even when the underlying alternative-picking logic is unchanged.

Preferences persist across itinerary resets (they're a traveler-level setting, not trip state) but
default to weights that exactly reproduce the original hardcoded scoring (cost 0.2 / time 0.3 /
convenience 0.4 / disruption 0.1), so nothing changes until the traveler actually customizes them.
Weights don't need to sum to 1 — they're normalized before use.

## Multi-trip persistence (Supabase)

`app/trip_repository.py` saves/loads/lists/deletes trips as a single JSONB row each
(`{nodes, edges}` + preferences) — see `supabase/schema.sql`. **Without any setup it falls back
to an in-memory dict**, so trip save/load/list/delete all work locally with zero configuration;
they just don't survive a server restart. To get real persistence:

1. Create a free project at [supabase.com](https://supabase.com).
2. Open the SQL editor and run `backend/supabase/schema.sql` once.
3. Grab **Project Settings → API → Project URL** and the **anon public key** (or the
   **service_role key** if you skip Supabase Auth entirely, since anon-key writes require the
   RLS policy's `auth.uid()` check, which only resolves for a signed-in user — the schema's
   `user_id is null` clause is what makes anonymous/demo trips work with just the anon key).
4. Set on the backend: `SUPABASE_URL=https://xxxx.supabase.co` and `SUPABASE_KEY=<anon-or-service-role-key>`.

**Not built yet**: Supabase Auth sign-in/sign-up in the frontend. Right now every trip is
effectively "anonymous" (`user_id` stays null) — real per-user account isolation needs a login
flow added to the frontend (Supabase's JS client + a protected route), which is the natural next
step once the app has actual users instead of one shared demo session.

## Real external data (weather + flight status)

`app/external_apis.py` — two "check, then let the traveler confirm" endpoints, same fallback
philosophy as the LLM layer: no key set → `{"configured": false, "message": "..."}` , no crash.

- **`GET /api/weather-check?location=...&date=...`** — real forecast via OpenWeatherMap's free
  5-day/3-hour endpoint. Sign up at [openweathermap.org/api](https://openweathermap.org/api),
  set `OPENWEATHER_API_KEY`. Returns a `severity_suggestion` ("moderate"/"severe"/null) the
  "Check real forecast" button in the weather panel uses to pre-fill the severity dropdown —
  you still click "Trigger Weather Event" to actually apply it.
- **`GET /api/flight-status?flight_iata=...`** — real live flight status via AviationStack's
  free tier. Sign up at [aviationstack.com](https://aviationstack.com), set
  `AVIATIONSTACK_API_KEY`. Note: AviationStack's free tier is **HTTP only**, not HTTPS — that's
  their limitation, not a bug here. Returns a `suggested_action` ("delay"/"cancel"/null) the
  "Check real flight status" button (shown for flight bookings) uses to pre-fill the disrupt form.

## Deployment

Nothing is deployed yet — this all runs locally today. To actually host it:

**Backend** (`backend/Dockerfile` provided, untested against a real Docker daemon in this
environment — standard FastAPI/uvicorn image, should work but verify before relying on it):
- Render or Railway (either handles WebSockets fine, which this app needs for the live risk
  feed — a plain serverless/Vercel function won't keep the `/ws/risk-feed` connection open).
- Env vars to set there: `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`,
  `OPENWEATHER_API_KEY`, `AVIATIONSTACK_API_KEY` (all optional — each feature just falls back
  gracefully without its key), plus `CORS_ALLOWED_ORIGINS=https://your-frontend-domain` once the
  frontend has a real URL.

**Frontend**: Vercel auto-detects Vite. Set `VITE_API_BASE_URL=https://your-backend.onrender.com`
(or wherever the backend ends up) in Vercel's project environment variables before deploying —
without it, the deployed frontend will try to talk to `localhost:8000` and fail.

**Database**: Supabase is already hosted — no deployment step, just the SQL migration above.

### All the keys/signups you need, in one place

| Env var | Where to get it | Required? |
|---|---|---|
| `NUGEN_API_KEY` | [nugen.in/signup?invite=PILLAIUNIV2026](https://nugen.in/signup?invite=PILLAIUNIV2026) | Yes for the hackathon (Nugen is mandatory); the app still runs without it |
| `GEMINI_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | No — falls back to rule-based explanations |
| `SUPABASE_URL` / `SUPABASE_KEY` | Free project at [supabase.com](https://supabase.com), run `backend/supabase/schema.sql` | No — falls back to in-memory (resets on restart) |
| `OPENWEATHER_API_KEY` | Free tier at [openweathermap.org/api](https://openweathermap.org/api) | No — the forecast check and digital twin use keyless Open-Meteo |
| `AVIATIONSTACK_API_KEY` | Free tier at [aviationstack.com](https://aviationstack.com) | No — falls back to manual flight disruption only |
| `CORS_ALLOWED_ORIGINS` | Your deployed frontend's URL | Only once actually deployed |
| `VITE_API_BASE_URL` | Your deployed backend's URL (frontend build-time env var) | Only once actually deployed |

Nothing here is required to run the full demo locally — every one of these has a working
fallback. They only matter once you want real persistence, real explanations, or real live data
instead of the simulated/manual versions.

