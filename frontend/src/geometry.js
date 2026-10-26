const EARTH_RADIUS_MI = 3958.8;

function haversineMi([lat1, lon1], [lat2, lon2]) {
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLon = (lon2 - lon1) * rad;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_MI * Math.asin(Math.sqrt(h));
}

/**
 * Split a route's line into runs of equal risk, so the selected route can be
 * drawn in the colour of the weather the truck meets along it. Each vertex
 * takes the level of the nearest checkpoint along the road.
 */
export function riskSegments(route) {
  const line = route.geometry;
  const cps = route.checkpoints;
  const cum = [0];
  for (let i = 1; i < line.length; i++) cum.push(cum[i - 1] + haversineMi(line[i - 1], line[i]));
  const scale = cum[cum.length - 1] ? route.distance_mi / cum[cum.length - 1] : 1;

  const levels = [];
  let j = 0;
  for (let i = 0; i < line.length; i++) {
    const mile = cum[i] * scale;
    while (j < cps.length - 1 && mile > (cps[j].mile + cps[j + 1].mile) / 2) j++;
    levels.push(cps[j].level);
  }

  const runs = [];
  let start = 0;
  for (let i = 1; i <= line.length; i++) {
    if (i === line.length || levels[i] !== levels[start]) {
      // Overlap by one vertex so consecutive runs join without a gap.
      runs.push({ level: levels[start], positions: line.slice(start, Math.min(i + 1, line.length)) });
      start = i;
    }
  }
  return runs;
}

const SUBDIVISIONS = 4;

/**
 * Heatmap samples [lat, lon, risk level] along every route's corridor for one forecast hour.
 * Checkpoints can be 50 miles apart, so values are interpolated between them
 * to keep the heat band continuous instead of a string of separate blobs.
 */
export function heatPoints(routes, hour) {
  const points = [];
  for (const route of routes) {
    const cps = route.checkpoints;
    for (let i = 0; i < cps.length; i++) {
      const a = cps[i];
      const aLevel = a.forecast.level[hour];
      points.push([a.lat, a.lon, aLevel]);
      const b = cps[i + 1];
      if (!b) continue;
      const bLevel = b.forecast.level[hour];
      for (let k = 1; k < SUBDIVISIONS; k++) {
        const t = k / SUBDIVISIONS;
        points.push([a.lat + (b.lat - a.lat) * t, a.lon + (b.lon - a.lon) * t, aLevel + (bLevel - aLevel) * t]);
      }
    }
  }
  return points;
}
