"""Small geometry helpers: distances, resampling along a polyline."""

import math
from bisect import bisect_left

EARTH_RADIUS_M = 6_371_008.8
METERS_PER_MILE = 1609.344


def haversine_m(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def cumulative_m(coords):
    cum = [0.0]
    for prev, cur in zip(coords, coords[1:]):
        cum.append(cum[-1] + haversine_m(prev, cur))
    return cum


def point_at(coords, cum, distance_m):
    """Interpolate the coordinate `distance_m` along the polyline."""
    if distance_m <= 0:
        return coords[0]
    if distance_m >= cum[-1]:
        return coords[-1]
    i = bisect_left(cum, distance_m)
    span = cum[i] - cum[i - 1]
    t = 0 if span == 0 else (distance_m - cum[i - 1]) / span
    (lat1, lon1), (lat2, lon2) = coords[i - 1], coords[i]
    return (lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t)


def downsample(coords, max_points=500):
    """Thin a polyline for the browser while keeping both endpoints."""
    if len(coords) <= max_points:
        return coords
    stride = (len(coords) - 1) / (max_points - 1)
    picked = [coords[round(i * stride)] for i in range(max_points)]
    picked[-1] = coords[-1]
    return picked


def overlap_ratio(a, b, tolerance_m=3000, samples=40):
    """Share of `a` that runs within `tolerance_m` of a vertex of `b`."""
    cum_a = cumulative_m(a)
    if cum_a[-1] == 0:
        return 1.0
    b_thin = downsample(b, 800)
    close = 0
    for k in range(samples):
        p = point_at(a, cum_a, cum_a[-1] * k / (samples - 1))
        if min(haversine_m(p, q) for q in b_thin) <= tolerance_m:
            close += 1
    return close / samples
