import { useEffect, useState } from 'react';
import { planTrip } from './api';
import MapView from './MapView';
import RoutePanel from './RoutePanel';
import { LEVELS, formatTime } from './levels';

function defaultDeparture() {
  const d = new Date(Date.now() + 3600_000);
  d.setMinutes(0, 0, 0);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); // datetime-local wants local time
  return d.toISOString().slice(0, 16);
}

export default function App() {
  const [form, setForm] = useState({
    origin: '',
    destination: '',
    departure: defaultDeparture(),
    load: '40000',
    interval: '25',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [hour, setHour] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [showHeat, setShowHeat] = useState(true);

  const update = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    setPlaying(false);
    try {
      const data = await planTrip(form);
      setResult(data);
      setSelectedId(data.recommended);
      setHour(0);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  // Auto-advance the forecast slider while playing.
  useEffect(() => {
    if (!playing || !result) return undefined;
    const timer = setInterval(() => {
      setHour((h) => (h >= result.forecast_hours ? 0 : h + 1));
    }, 350);
    return () => clearInterval(timer);
  }, [playing, result]);

  const forecastTime = result
    ? new Date(new Date(result.departure).setMinutes(0, 0, 0) + hour * 3600_000).toISOString()
    : null;

  return (
    <div className="app">
      <aside className="sidebar">
        <h1>Weather-Aware Truck Routing</h1>
        <p className="lede">Pick the safest of three routes for your load.</p>

        <form onSubmit={submit}>
          <label>
            Origin
            <input value={form.origin} onChange={update('origin')} placeholder="Denver, CO" required />
          </label>
          <label>
            Destination
            <input value={form.destination} onChange={update('destination')} placeholder="Chicago, IL" required />
          </label>
          <label>
            Departure
            <input type="datetime-local" value={form.departure} onChange={update('departure')} required />
          </label>
          <div className="row">
            <label>
              Load weight (lb)
              <input type="number" min="0" max="200000" step="500" value={form.load} onChange={update('load')} required />
            </label>
            <label>
              Weather every
              <select value={form.interval} onChange={update('interval')}>
                <option value="10">10 miles</option>
                <option value="25">25 miles</option>
                <option value="50">50 miles</option>
              </select>
            </label>
          </div>
          <button type="submit" className="primary" disabled={loading}>
            {loading ? 'Planning…' : 'Find safest route'}
          </button>
        </form>

        {error && <p className="error" role="alert">{error}</p>}
        {result && <RoutePanel result={result} selectedId={selectedId} onSelect={setSelectedId} />}
      </aside>

      <main className="map-area">
        <MapView result={result} selectedId={selectedId} onSelect={setSelectedId} hour={hour} showHeat={showHeat} />

        <div className="legend">
          {LEVELS.map((l) => (
            <span key={l.name}>
              <i style={{ background: l.color }} />
              {l.name}
            </span>
          ))}
        </div>

        {result && (
          <div className="slider-bar">
            <button type="button" onClick={() => setPlaying((p) => !p)} aria-label={playing ? 'Pause' : 'Play'}>
              {playing ? '❚❚' : '▶'}
            </button>
            <div className="slider-main">
              <div className="slider-label">
                <strong>Forecast heatmap: +{hour}h</strong>
                <span>{formatTime(forecastTime)}</span>
              </div>
              <input
                type="range"
                min="0"
                max={result.forecast_hours}
                value={hour}
                onChange={(e) => setHour(Number(e.target.value))}
                aria-label="Forecast hours after departure"
              />
            </div>
            <label className="toggle">
              <input type="checkbox" checked={showHeat} onChange={(e) => setShowHeat(e.target.checked)} /> Heatmap
            </label>
          </div>
        )}
        {loading && <div className="loading">Fetching routes and weather…</div>}
      </main>
    </div>
  );
}
