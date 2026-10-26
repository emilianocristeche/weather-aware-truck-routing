export async function planTrip(form) {
  const response = await fetch('/api/plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      origin: form.origin,
      destination: form.destination,
      departure: new Date(form.departure).toISOString(),
      load_lb: Number(form.load),
      interval_mi: Number(form.interval),
    }),
  });
  let data = null;
  try {
    data = await response.json();
  } catch {
    // Non-JSON body (e.g. a gateway error page); handled below.
  }
  if (!response.ok) throw new Error(data?.error ?? `Request failed (${response.status}).`);
  return data;
}
