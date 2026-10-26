import { useEffect, useMemo } from 'react';
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet';
import HeatLayer from './HeatLayer';
import { heatPoints, riskSegments } from './geometry';
import { LEVELS, ROUTE_COLORS, formatTime } from './levels';

function FitToRoutes({ routes }) {
  const map = useMap();
  useEffect(() => {
    if (!routes.length) return;
    const bounds = routes.flatMap((r) => r.geometry);
    map.fitBounds(bounds, { padding: [40, 40] });
  }, [map, routes]);
  return null;
}

function CheckpointMarker({ route, point, selected, onSelect }) {
  const level = LEVELS[point.level];
  return (
    <CircleMarker
      center={[point.lat, point.lon]}
      radius={selected ? 7 : 4}
      pathOptions={{
        color: selected ? '#111' : ROUTE_COLORS[route.id],
        weight: selected ? 2 : 1.5,
        fillColor: level.color,
        fillOpacity: 1,
      }}
      eventHandlers={{ click: onSelect }}
    >
      <Tooltip>
        <strong>
          {route.label} · mile {point.mile}
        </strong>
        <br />
        {level.name} risk · ETA {formatTime(point.eta)}
        <br />
        Wind {point.wind_mph} mph · Rain {point.rain_in_hr} in/hr · Snow {point.snow_in_hr} in/hr
      </Tooltip>
    </CircleMarker>
  );
}

export default function MapView({ result, selectedId, onSelect, hour, showHeat }) {
  const routes = result?.routes ?? [];
  const selected = routes.find((r) => r.id === selectedId);
  const segments = useMemo(() => (selected ? riskSegments(selected) : []), [selected]);
  const heat = useMemo(() => (result ? heatPoints(routes, hour) : []), [result, routes, hour]);

  return (
    <MapContainer center={[39.5, -98.35]} zoom={4} className="map" preferCanvas>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitToRoutes routes={routes} />
      {showHeat && result && <HeatLayer points={heat} />}

      {/* Unselected routes first so the selected one is drawn on top. */}
      {routes
        .filter((r) => r.id !== selectedId)
        .map((route) => (
          <Polyline
            key={route.id}
            positions={route.geometry}
            pathOptions={{ color: ROUTE_COLORS[route.id], weight: 5, opacity: 0.55 }}
            eventHandlers={{ click: () => onSelect(route.id) }}
          />
        ))}
      {selected && (
        <>
          <Polyline positions={selected.geometry} pathOptions={{ color: '#111', weight: 10, opacity: 0.85 }} />
          {segments.map((run, i) => (
            <Polyline
              key={i}
              positions={run.positions}
              pathOptions={{ color: LEVELS[run.level].color, weight: 6, opacity: 1 }}
            />
          ))}
        </>
      )}

      {routes.flatMap((route) =>
        route.checkpoints.map((point) => (
          <CheckpointMarker
            key={`${route.id}-${point.mile}`}
            route={route}
            point={point}
            selected={route.id === selectedId}
            onSelect={() => onSelect(route.id)}
          />
        )),
      )}

      {result &&
        [result.origin, result.destination].map((place, i) => (
          <CircleMarker
            key={i}
            center={[place.lat, place.lon]}
            radius={9}
            pathOptions={{ color: '#fff', weight: 3, fillColor: i ? '#111' : '#2563eb', fillOpacity: 1 }}
          >
            <Tooltip permanent direction="top" offset={[0, -8]}>
              {i ? 'Destination' : 'Origin'}
            </Tooltip>
          </CircleMarker>
        ))}
    </MapContainer>
  );
}
