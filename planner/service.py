"""Trip planning: routes -> checkpoints -> weather -> risk -> recommendation."""

import math
from datetime import datetime, timedelta, timezone

from . import providers
from .geo import METERS_PER_MILE, cumulative_m, downsample, point_at
from .risk import LEVELS, classify

FORECAST_HOURS = 48  # heatmap slider range
MAX_FORECAST_DAYS = 16  # Open-Meteo limit
ALLOWED_INTERVALS = (10, 25, 50)
ROUTE_LABELS = "ABC"


class PlanError(Exception):
    """Invalid input or an unplannable trip; `status` is the HTTP code to use."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def build_checkpoints(coords, total_m, total_s, interval_mi):
    """Sample the route every `interval_mi` miles, always including both ends.

    Each checkpoint also gets the length of road it stands for: the stretch
    halfway to its neighbours. Those lengths sum to the route length and are
    what "miles at risk level X" is measured with.
    """
    cum = cumulative_m(coords)
    scale = total_m / cum[-1] if cum[-1] else 1.0
    cum = [c * scale for c in cum]

    step = interval_mi * METERS_PER_MILE
    distances = [k * step for k in range(int(total_m // step) + 1)]
    if total_m - distances[-1] > 1:
        distances.append(total_m)
    else:
        distances[-1] = total_m
    if len(distances) == 1:
        distances.append(total_m)

    checkpoints = []
    for i, d in enumerate(distances):
        lo = (distances[i - 1] + d) / 2 if i else 0.0
        hi = (d + distances[i + 1]) / 2 if i + 1 < len(distances) else total_m
        lat, lon = point_at(coords, cum, d)
        checkpoints.append(
            {
                "lat": lat,
                "lon": lon,
                "mile": d / METERS_PER_MILE,
                "seconds": total_s * d / total_m if total_m else 0.0,
                "segment_mi": (hi - lo) / METERS_PER_MILE,
            }
        )
    return checkpoints


def _hour_index(moment, series_start, length):
    hours = round((moment - series_start).total_seconds() / 3600)
    return max(0, min(length - 1, hours))


def evaluate_route(route, label, departure, load_lb, interval_mi, weather):
    checkpoints = build_checkpoints(
        route["coords"], route["distance_m"], route["duration_s"], interval_mi
    )
    dep_hour = departure.replace(minute=0, second=0, microsecond=0)

    miles_by_level = [0.0] * len(LEVELS)
    weighted_risk = 0.0
    out_points = []
    for cp in checkpoints:
        series = weather[(round(cp["lat"], 2), round(cp["lon"], 2))]
        n = len(series["wind"])
        eta = departure + timedelta(seconds=cp["seconds"])
        at = _hour_index(eta, series["start"], n)
        here = classify(series["wind"][at], series["rain"][at], series["snow"][at], load_lb)

        base = _hour_index(dep_hour, series["start"], n)
        forecast = {"level": [], "wind": [], "rain": [], "snow": []}
        for h in range(FORECAST_HOURS + 1):
            j = min(n - 1, base + h)
            risk = classify(series["wind"][j], series["rain"][j], series["snow"][j], load_lb)
            forecast["level"].append(risk["level"])
            forecast["wind"].append(round(series["wind"][j], 1))
            forecast["rain"].append(round(series["rain"][j], 3))
            forecast["snow"].append(round(series["snow"][j], 3))

        miles_by_level[here["level"]] += cp["segment_mi"]
        weighted_risk += here["level"] * cp["segment_mi"]
        out_points.append(
            {
                "lat": round(cp["lat"], 5),
                "lon": round(cp["lon"], 5),
                "mile": round(cp["mile"], 1),
                "eta": eta.isoformat(),
                "wind_mph": round(series["wind"][at], 1),
                "rain_in_hr": round(series["rain"][at], 3),
                "snow_in_hr": round(series["snow"][at], 3),
                "level": here["level"],
                "level_name": LEVELS[here["level"]],
                "segment_mi": round(cp["segment_mi"], 1),
                "forecast": forecast,
            }
        )

    distance_mi = route["distance_m"] / METERS_PER_MILE
    return {
        "id": label,
        "label": f"Route {label}",
        "distance_mi": round(distance_mi, 1),
        "duration_h": round(route["duration_s"] / 3600, 2),
        "arrival": (departure + timedelta(seconds=route["duration_s"])).isoformat(),
        "geometry": [[round(a, 5), round(b, 5)] for a, b in downsample(route["coords"])],
        "checkpoints": out_points,
        "summary": {
            "miles_by_level": {
                name: round(m, 1) for name, m in zip(LEVELS, miles_by_level)
            },
            "avg_risk": round(weighted_risk / distance_mi, 2) if distance_mi else 0.0,
            "worst_level": max(p["level"] for p in out_points),
        },
    }


# Priority order from the brief; `no_travel` leads because it is worse than Severe.
CRITERIA = (
    ("no_travel", "No Travel miles", lambda r: r["summary"]["miles_by_level"]["No Travel"]),
    ("severe", "Severe miles", lambda r: r["summary"]["miles_by_level"]["Severe"]),
    ("high", "High miles", lambda r: r["summary"]["miles_by_level"]["High"]),
    ("avg_risk", "average risk", lambda r: r["summary"]["avg_risk"]),
    ("duration", "travel time", lambda r: r["duration_h"]),
)


def rank_routes(routes):
    """Order routes best-first and explain the winner."""
    routes.sort(key=lambda r: tuple(round(fn(r), 1) for _, _, fn in CRITERIA[:3])
                + (round(CRITERIA[3][2](r), 2), CRITERIA[4][2](r)))
    reason = "Only one drivable route was found."
    if len(routes) > 1:
        best, other = routes[0], routes[1]
        reason = "Equivalent on weather risk; it is the fastest."
        for _, name, fn in CRITERIA:
            if round(fn(best), 2) != round(fn(other), 2):
                reason = f"Lowest on {name}: {round(fn(best), 1)} vs {round(fn(other), 1)} on {other['label']}."
                break
    for rank, route in enumerate(routes, start=1):
        route["rank"] = rank
    return reason


def _parse_departure(value):
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise PlanError("Departure must be an ISO date/time.") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def plan_trip(payload, now=None):
    origin_q = str(payload.get("origin", "")).strip()
    dest_q = str(payload.get("destination", "")).strip()
    if not origin_q or not dest_q:
        raise PlanError("Enter an origin and a destination.")
    try:
        load_lb = float(payload.get("load_lb"))
        interval = int(payload.get("interval_mi", 25))
    except (TypeError, ValueError) as exc:
        raise PlanError("Load weight and checkpoint interval must be numbers.") from exc
    if not 0 <= load_lb <= 200_000:
        raise PlanError("Load weight must be between 0 and 200,000 lb.")
    if interval not in ALLOWED_INTERVALS:
        raise PlanError(f"Checkpoint interval must be one of {ALLOWED_INTERVALS} miles.")

    now = now or datetime.now(timezone.utc)
    departure = _parse_departure(payload.get("departure"))
    if departure < now - timedelta(hours=2):
        raise PlanError("Departure can't be in the past: the forecast starts now.")

    try:
        o_lat, o_lon, o_name = providers.geocode(origin_q)
        d_lat, d_lon, d_name = providers.geocode(dest_q)
        raw_routes = providers.route_options((o_lat, o_lon), (d_lat, d_lon))

        # past_days=1 means the weather series starts at yesterday 00:00 UTC.
        series_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) - timedelta(days=1)
        end = departure + timedelta(seconds=max(r["duration_s"] for r in raw_routes))
        end += timedelta(hours=FORECAST_HOURS + 1)
        forecast_days = math.ceil((end - series_start).total_seconds() / 86400) - 1
        if forecast_days > MAX_FORECAST_DAYS:
            raise PlanError(
                f"Forecast data only reaches {MAX_FORECAST_DAYS} days ahead; "
                "pick an earlier departure."
            )

        all_points = []
        for r in raw_routes:
            total_m = r["distance_m"]
            all_points += [
                (cp["lat"], cp["lon"])
                for cp in build_checkpoints(r["coords"], total_m, r["duration_s"], interval_mi=interval)
            ]
        weather = providers.hourly_weather(all_points, max(forecast_days, 1))
    except providers.ProviderError as exc:
        raise PlanError(str(exc), exc.status) from exc

    routes = [
        evaluate_route(r, ROUTE_LABELS[i], departure, load_lb, interval, weather)
        for i, r in enumerate(raw_routes)
    ]
    reason = rank_routes(routes)
    return {
        "origin": {"name": o_name, "lat": o_lat, "lon": o_lon},
        "destination": {"name": d_name, "lat": d_lat, "lon": d_lon},
        "departure": departure.isoformat(),
        "load_lb": load_lb,
        "interval_mi": interval,
        "levels": list(LEVELS),
        "forecast_hours": FORECAST_HOURS,
        "recommended": routes[0]["id"],
        "reason": reason,
        "routes": routes,
    }
