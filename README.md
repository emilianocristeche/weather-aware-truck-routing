# Weather-Aware Truck Routing

A React + Django app that helps a truck driver pick the safest of three routes
for a given departure time and load weight. It samples the weather along each
route at the truck's estimated arrival time, classifies the risk with the
rules from the brief, recommends one route, and shows everything on a map with
a 0-48 hour weather-risk heatmap.

## How it works

1. **Geocode** origin and destination (Photon, falling back to Nominatim and
   Open-Meteo, since public geocoders rate-limit shared cloud IPs). A literal
   `lat,lon` also works.
2. **Routes**: ask OSRM for alternatives. When it returns fewer than three, extra
   routes are steered through a waypoint beside the corridor; near-duplicates
   (>=90% overlap) are dropped.
3. **Checkpoints** every 10 / 25 / 50 miles along each route (both ends always
   included). ETA at a checkpoint = departure + route duration x fraction of
   distance covered.
4. **Weather** (Open-Meteo hourly wind, rain, snowfall) at each checkpoint,
   read at the hour nearest its ETA. Open-Meteo's free tier is limited per IP,
   so after a 429 the app switches to MET Norway for ten minutes. MET reports
   total precipitation only; it is counted as snow at or below 0 °C, using a
   10:1 snow-to-liquid ratio.
5. **Risk** per checkpoint = worst of wind / rain / snow band, then the load rules.
6. **Recommendation** ranks routes by, in order: fewest No Travel miles, fewest
   Severe miles, fewest High miles, lowest average risk, shortest time.
7. **Heatmap**: for every checkpoint the same risk is computed for each of the
   48 hours after departure, so the slider is instant and needs no extra requests.

"Miles at a level" is measured by giving each checkpoint the stretch of road
halfway to its neighbours, so the per-level miles add up to the route length.

## Decisions worth knowing

- **Band edges.** Lower bounds are inclusive (rain of exactly 0.25 in/hr is High).
  Rain and snow No Travel are strictly greater than 1.00 / 3.0, as written.
- **No Travel ranks above Severe**, so it leads the ordering; otherwise the order
  is exactly the brief's.
- **Load rules** can only raise a level: 45-54 mph with a load over 30,000 lb is
  No Travel; 35-44 mph with a load over 40,000 lb is at least Severe.
- **Departure time** is read in the browser's timezone and sent as UTC.
- **Heatmap** is a small canvas layer where the worst nearby risk wins. A stock
  density heatmap adds intensities together, so a long, densely sampled route
  glows red even when every checkpoint is Low.
- **No API keys.** OSRM's public server only has a car profile, so travel times
  are car-like, not truck-specific. Routing, geocoding and weather results are
  cached in memory; for real traffic, swap in a self-hosted OSRM or a truck
  routing provider by changing `planner/providers.py` only.
- Forecast data reaches 16 days ahead (about 9 on the MET Norway fallback),
  so later departures are rejected with a message.

## Run locally

```bash
python -m venv .venv && .venv/Scripts/activate      # source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cd frontend && npm ci && npm run build && cd ..
python manage.py runserver                            # http://localhost:8000
```

For frontend development run `npm run dev` in `frontend/` (proxies `/api` to
Django on port 8000).

```bash
python manage.py test        # risk rules, checkpointing, ranking, validation
```

## API

`POST /api/plan`

```json
{ "origin": "Denver, CO", "destination": "Chicago, IL",
  "departure": "2026-10-27T15:00:00Z", "load_lb": 45000, "interval_mi": 25 }
```

Returns the three routes (geometry, checkpoints with ETA / weather / risk, 49-hour
forecast per checkpoint, miles by level), the recommended route id, and a one-line
reason. Errors are `{ "error": "..." }` with a 4xx/5xx status.

## Layout

```
planner/risk.py       thresholds and load rules (pure functions)
planner/providers.py  geocoding, OSRM, Open-Meteo clients + caching
planner/service.py    checkpoints, evaluation, ranking, request validation
planner/tests.py      unit tests
frontend/src/         React + Leaflet UI (MapView, HeatLayer, RoutePanel)
```

## Deploy

`Dockerfile` builds the React app and serves it, with the API, from one Django
process. `render.yaml` is a ready Render blueprint (New > Blueprint > pick this repo).
