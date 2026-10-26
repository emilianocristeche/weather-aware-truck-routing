// Risk levels in the same order as the backend (index = level number).
export const LEVELS = [
  { name: 'Low', color: '#2e9d57' },
  { name: 'Moderate', color: '#e0b100' },
  { name: 'High', color: '#ee7d1a' },
  { name: 'Severe', color: '#d63a3a' },
  { name: 'No Travel', color: '#4a1260' },
];

export const ROUTE_COLORS = { A: '#2563eb', B: '#7c3aed', C: '#0f766e' };

export function formatDuration(hours) {
  const total = Math.round(hours * 60);
  return `${Math.floor(total / 60)}h ${String(total % 60).padStart(2, '0')}m`;
}

export function formatTime(iso, options = {}) {
  return new Date(iso).toLocaleString([], {
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
    ...options,
  });
}
