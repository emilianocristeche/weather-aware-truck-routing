import { LEVELS, ROUTE_COLORS, formatDuration, formatTime } from './levels';

function RiskBar({ route }) {
  const miles = route.summary.miles_by_level;
  return (
    <div className="riskbar" role="img" aria-label="Miles by risk level">
      {LEVELS.map((level) => {
        const share = (miles[level.name] / route.distance_mi) * 100;
        return share > 0 ? (
          <span key={level.name} style={{ width: `${share}%`, background: level.color }} title={`${level.name}: ${miles[level.name]} mi`} />
        ) : null;
      })}
    </div>
  );
}

function RouteCard({ route, selected, recommended, onSelect }) {
  const miles = route.summary.miles_by_level;
  return (
    <button type="button" className={`route-card${selected ? ' selected' : ''}`} onClick={onSelect}>
      <div className="route-head">
        <span className="swatch" style={{ background: ROUTE_COLORS[route.id] }} />
        <strong>{route.label}</strong>
        {recommended && <span className="badge best">Recommended</span>}
        <span className="rank">#{route.rank}</span>
      </div>
      <div className="route-stats">
        <span>{route.distance_mi.toLocaleString()} mi</span>
        <span>{formatDuration(route.duration_h)}</span>
        <span>Arrive {formatTime(route.arrival)}</span>
      </div>
      <RiskBar route={route} />
      <div className="route-risk">
        <span>Severe {miles.Severe} mi</span>
        <span>High {miles.High} mi</span>
        {miles['No Travel'] > 0 && <span className="notravel">No Travel {miles['No Travel']} mi</span>}
        <span>Avg risk {route.summary.avg_risk}</span>
      </div>
    </button>
  );
}

function CheckpointTable({ route }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Mile</th>
            <th>ETA</th>
            <th>Wind</th>
            <th>Rain</th>
            <th>Snow</th>
            <th>Risk</th>
          </tr>
        </thead>
        <tbody>
          {route.checkpoints.map((p) => (
            <tr key={p.mile}>
              <td>{p.mile}</td>
              <td>{formatTime(p.eta, { weekday: undefined })}</td>
              <td>{p.wind_mph}</td>
              <td>{p.rain_in_hr}</td>
              <td>{p.snow_in_hr}</td>
              <td>
                <span className="pill" style={{ background: LEVELS[p.level].color }}>
                  {p.level_name}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="units">Wind in mph, rain and snow in in/hr, at the truck's estimated arrival time.</p>
    </div>
  );
}

export default function RoutePanel({ result, selectedId, onSelect }) {
  const routes = [...result.routes].sort((a, b) => a.rank - b.rank);
  const selected = routes.find((r) => r.id === selectedId);
  return (
    <section className="results">
      <div className="recommendation">
        <strong>Best route: {routes[0].label}</strong>
        <p>{result.reason}</p>
      </div>
      {routes.map((route) => (
        <RouteCard
          key={route.id}
          route={route}
          selected={route.id === selectedId}
          recommended={route.id === result.recommended}
          onSelect={() => onSelect(route.id)}
        />
      ))}
      {selected && (
        <details open>
          <summary>
            {selected.label} checkpoints ({selected.checkpoints.length})
          </summary>
          <CheckpointTable route={selected} />
        </details>
      )}
    </section>
  );
}
