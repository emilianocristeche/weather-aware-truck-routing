"""Weather risk classification for a single checkpoint.

Thresholds come straight from the assessment brief. A band's lower bound is
inclusive, except the "No Travel" band for rain and snow, which the brief
defines as strictly greater than its bound (> 1.00 in/hr, > 3.0 in/hr).
"""

LEVELS = ("Low", "Moderate", "High", "Severe", "No Travel")
LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = range(5)

# (lower bound, strict) for Moderate, High, Severe, No Travel.
WIND_BANDS = ((25, False), (35, False), (45, False), (55, False))  # mph
RAIN_BANDS = ((0.10, False), (0.25, False), (0.50, False), (1.00, True))  # in/hr
SNOW_BANDS = ((0.5, False), (1.0, False), (2.0, False), (3.0, True))  # in/hr


def _band(value, bands):
    level = LOW
    for threshold, strict in bands:
        if value > threshold or (not strict and value >= threshold):
            level += 1
        else:
            break
    return level


def classify(wind_mph, rain_in_hr, snow_in_hr, load_lb):
    """Return the overall risk level (0-4) plus the per-factor levels."""
    wind = _band(wind_mph, WIND_BANDS)
    rain = _band(rain_in_hr, RAIN_BANDS)
    snow = _band(snow_in_hr, SNOW_BANDS)
    level = max(wind, rain, snow)

    # Load rules from the brief.
    if 45 <= wind_mph < 55 and load_lb > 30_000:
        level = NO_TRAVEL
    elif 35 <= wind_mph < 45 and load_lb > 40_000:
        level = max(level, SEVERE)

    return {"level": level, "wind": wind, "rain": rain, "snow": snow}
