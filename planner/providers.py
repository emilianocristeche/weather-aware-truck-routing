"""Third-party API clients: Nominatim (geocoding), OSRM (routing), Open-Meteo (weather).

None of them needs an API key. All results are cached in-process, which keeps
repeat requests fast and stays well inside the public services' usage policies.
"""

import math
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

from .geo import overlap_ratio

USER_AGENT = "spotter-truck-routing/1.0 (assessment project)"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = os.environ.get("OSRM_URL", "https://router.project-osrm.org")
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 25

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


class ProviderError(Exception):
    """A user-presentable failure from an upstream service."""

    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


_COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
_geocode_cache = {}
_geocode_lock = threading.Lock()
_last_nominatim_call = 0.0


def geocode(query):
    """Resolve free text (or a literal "lat,lon") to (lat, lon, display_name)."""
    match = _COORD_RE.match(query)
    if match:
        lat, lon = float(match.group(1)), float(match.group(2))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ProviderError(f"Invalid coordinates: {query}", 400)
        return lat, lon, f"{lat:.4f}, {lon:.4f}"

    key = query.strip().lower()
    with _geocode_lock:
        if key in _geocode_cache:
            return _geocode_cache[key]
        # Nominatim allows at most one request per second.
        global _last_nominatim_call
        wait = 1.05 - (time.monotonic() - _last_nominatim_call)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = _session.get(
                NOMINATIM_URL,
                params={"q": query, "format": "jsonv2", "limit": 1},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(f"Geocoding service unavailable: {exc}") from exc
        finally:
            _last_nominatim_call = time.monotonic()
        hits = resp.json()
        if not hits:
            raise ProviderError(f'Could not find a place called "{query}".', 400)
        result = (float(hits[0]["lat"]), float(hits[0]["lon"]), hits[0]["display_name"])
        _geocode_cache[key] = result
        return result


def _osrm(waypoints, alternatives):
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in waypoints)
    try:
        resp = _session.get(
            f"{OSRM_URL}/route/v1/driving/{coords}",
            params={
                "alternatives": "3" if alternatives else "false",
                "overview": "full",
                "geometries": "geojson",
                "steps": "false",
            },
            timeout=TIMEOUT,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise ProviderError(f"Routing service unavailable: {exc}") from exc
    if data.get("code") != "Ok":
        raise ProviderError(
            f"No drivable route found ({data.get('code', 'unknown error')}).", 400
        )
    return [
        {
            "coords": [(lat, lon) for lon, lat in r["geometry"]["coordinates"]],
            "distance_m": r["distance"],
            "duration_s": r["duration"],
        }
        for r in data["routes"]
    ]


def _is_distinct(candidate, kept):
    return all(overlap_ratio(candidate["coords"], k["coords"]) < 0.9 for k in kept)


def _via_points(origin, destination):
    """Waypoints pushed sideways from the straight line, nearest first."""
    mid_lat = (origin[0] + destination[0]) / 2
    mid_lon = (origin[1] + destination[1]) / 2
    d_lat, d_lon = destination[0] - origin[0], destination[1] - origin[1]
    length = math.hypot(d_lat, d_lon) or 1e-6
    # Unit vector perpendicular to the origin -> destination line.
    perp_lat, perp_lon = -d_lon / length, d_lat / length
    for scale in (0.12, 0.25):
        for sign in (1, -1):
            offset = length * scale * sign
            yield (mid_lat + perp_lat * offset, mid_lon + perp_lon * offset)


def route_options(origin, destination, wanted=3):
    """Return up to `wanted` meaningfully different driving routes."""
    kept = []
    for route in _osrm([origin, destination], alternatives=True):
        if _is_distinct(route, kept):
            kept.append(route)
    kept = kept[:wanted]

    if len(kept) < wanted:
        # OSRM often returns fewer alternatives than asked for; steer extra
        # routes through a waypoint beside the corridor to fill the gap.
        for via in _via_points(origin, destination):
            if len(kept) >= wanted:
                break
            try:
                candidate = _osrm([origin, via, destination], alternatives=False)[0]
            except ProviderError:
                continue
            # Reject detours that are absurdly long compared to the fastest route.
            if candidate["duration_s"] > kept[0]["duration_s"] * 1.8:
                continue
            if _is_distinct(candidate, kept):
                kept.append(candidate)
    kept.sort(key=lambda r: r["duration_s"])
    return kept


# ---------------------------------------------------------------- weather

_weather_cache = {}
_weather_lock = threading.Lock()
WEATHER_TTL_S = 15 * 60
BATCH = 40


def _fetch_batch(points, forecast_days):
    resp = None
    for attempt in range(3):
        try:
            resp = _session.get(
                OPEN_METEO_URL,
                params={
                    "latitude": ",".join(f"{lat:.2f}" for lat, _ in points),
                    "longitude": ",".join(f"{lon:.2f}" for _, lon in points),
                    "hourly": "wind_speed_10m,rain,showers,snowfall",
                    "wind_speed_unit": "mph",
                    "precipitation_unit": "inch",
                    "timezone": "GMT",
                    "past_days": 1,
                    "forecast_days": forecast_days,
                },
                timeout=TIMEOUT,
            )
            if resp.status_code == 429:
                time.sleep(1.5 * (attempt + 1))
                continue
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            if attempt == 2:
                raise ProviderError(f"Weather service unavailable: {exc}") from exc
            time.sleep(1)
    else:
        raise ProviderError("Weather service is rate limiting us; try again shortly.")

    payload = resp.json()
    if isinstance(payload, dict):
        payload = [payload]
    series = []
    for item in payload:
        h = item["hourly"]
        series.append(
            {
                "start": datetime.fromisoformat(h["time"][0]).replace(tzinfo=timezone.utc),
                "wind": [v or 0.0 for v in h["wind_speed_10m"]],
                "rain": [(r or 0.0) + (s or 0.0) for r, s in zip(h["rain"], h["showers"])],
                "snow": [v or 0.0 for v in h["snowfall"]],
            }
        )
    return series


def hourly_weather(points, forecast_days):
    """Hourly wind/rain/snow for each (lat, lon), keyed by the rounded point."""
    now = time.monotonic()
    wanted = {(round(lat, 2), round(lon, 2)) for lat, lon in points}
    result, missing = {}, []
    with _weather_lock:
        for key in wanted:
            hit = _weather_cache.get((key, forecast_days))
            if hit and now - hit[0] < WEATHER_TTL_S:
                result[key] = hit[1]
            else:
                missing.append(key)

    batches = [missing[i : i + BATCH] for i in range(0, len(missing), BATCH)]
    if batches:
        with ThreadPoolExecutor(max_workers=4) as pool:
            fetched = list(pool.map(lambda b: _fetch_batch(b, forecast_days), batches))
        with _weather_lock:
            for batch, series in zip(batches, fetched):
                for key, data in zip(batch, series):
                    _weather_cache[(key, forecast_days)] = (now, data)
                    result[key] = data
    return result
