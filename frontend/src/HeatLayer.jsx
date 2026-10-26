import { useEffect, useRef } from 'react';
import L from 'leaflet';
import { useMap } from 'react-leaflet';
import { LEVELS } from './levels';

const RADIUS_PX = 34;

/**
 * Canvas layer that paints soft blobs of risk colour along the corridor.
 * Points are drawn from lowest to highest level with normal blending, so the
 * worst weather nearby always wins instead of intensities adding up (which is
 * what makes a stock density heatmap glow red over a long, dense route).
 */
const RiskHeat = L.Layer.extend({
  initialize() {
    this._points = [];
  },

  setPoints(points) {
    this._points = [...points].sort((a, b) => a[2] - b[2]);
    if (this._map) this._draw();
  },

  onAdd(map) {
    this._map = map;
    this._canvas = L.DomUtil.create('canvas', 'risk-heat');
    // First child, so the routes and markers draw on top of the heat.
    const pane = map.getPane('overlayPane');
    pane.insertBefore(this._canvas, pane.firstChild);
    map.on('moveend zoomend resize', this._draw, this);
    this._draw();
  },

  onRemove(map) {
    map.off('moveend zoomend resize', this._draw, this);
    this._canvas.remove();
  },

  _draw() {
    const map = this._map;
    const canvas = this._canvas;
    const { x: width, y: height } = map.getSize();
    canvas.width = width;
    canvas.height = height;
    L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]));

    const ctx = canvas.getContext('2d');
    for (const [lat, lon, level] of this._points) {
      const { x, y } = map.latLngToContainerPoint([lat, lon]);
      if (x < -RADIUS_PX || y < -RADIUS_PX || x > width + RADIUS_PX || y > height + RADIUS_PX) continue;
      const color = LEVELS[Math.round(level)].color;
      const glow = ctx.createRadialGradient(x, y, 0, x, y, RADIUS_PX);
      glow.addColorStop(0, `${color}d9`);
      glow.addColorStop(0.55, `${color}80`);
      glow.addColorStop(1, `${color}00`);
      ctx.fillStyle = glow;
      ctx.fillRect(x - RADIUS_PX, y - RADIUS_PX, RADIUS_PX * 2, RADIUS_PX * 2);
    }
  },
});

/** Weather-risk heatmap; `points` are [lat, lon, risk level 0-4]. */
export default function HeatLayer({ points }) {
  const map = useMap();
  const layerRef = useRef(null);

  useEffect(() => {
    const layer = new RiskHeat().addTo(map);
    layerRef.current = layer;
    return () => {
      layer.remove();
      layerRef.current = null;
    };
  }, [map]);

  useEffect(() => {
    layerRef.current?.setPoints(points);
  }, [points]);

  return null;
}
