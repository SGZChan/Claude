import { useState } from "react";

export interface Series { key: string; label: string; color: string; }

interface LineProps {
  data: Record<string, any>[];
  x: string;
  series: Series[];
  format?: (v: number) => string;
  yMax?: number;
  height?: number;
}

/** Multi-series line chart: 2px lines, recessive grid, crosshair + tooltip, direct end labels. */
export function LineChart({ data, x, series, format = String, yMax, height = 220 }: LineProps) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 640, H = height, m = { l: 48, r: 78, t: 12, b: 24 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const max = yMax ?? Math.max(1e-9, ...data.flatMap((d) => series.map((s) => +d[s.key] || 0)));
  const X = (i: number) => m.l + (data.length < 2 ? iw / 2 : (i / (data.length - 1)) * iw);
  const Y = (v: number) => m.t + ih - (v / max) * ih;
  const ticks = [0, 0.5, 1].map((f) => f * max);
  const path = (k: string) => data.map((d, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(+d[k] || 0).toFixed(1)}`).join("");
  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    setHover(data.length ? Math.max(0, Math.min(data.length - 1, Math.round(((px - m.l) / iw) * (data.length - 1)))) : null);
  };
  const last = data[data.length - 1];
  return (
    <div className="chart">
      <div className="legend" aria-hidden={series.length < 2}>
        {series.length > 1 && series.map((s) => (
          <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>
        ))}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={series.map((s) => s.label).join(", ")}
        onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={m.l} x2={W - m.r} y1={Y(t)} y2={Y(t)} className="gridline" />
            <text x={m.l - 6} y={Y(t) + 4} textAnchor="end" className="axis">{format(t)}</text>
          </g>
        ))}
        {data.map((d, i) => (i % Math.ceil(data.length / 7) === 0 ? (
          <text key={i} x={X(i)} y={H - 6} textAnchor="middle" className="axis">{String(d[x])}</text>) : null))}
        {series.map((s) => <path key={s.key} d={path(s.key)} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />)}
        {last && series.map((s) => (
          <text key={s.key} x={X(data.length - 1) + 8} y={Y(+last[s.key] || 0) + 4} className="endlabel">{format(+last[s.key] || 0)}</text>))}
        {hover !== null && data[hover] && (
          <g>
            <line x1={X(hover)} x2={X(hover)} y1={m.t} y2={m.t + ih} className="cross" />
            {series.map((s) => <circle key={s.key} cx={X(hover)} cy={Y(+data[hover][s.key] || 0)} r={4} fill={s.color} className="dot" />)}
          </g>
        )}
      </svg>
      {hover !== null && data[hover] && (
        <div className="tooltip" style={{ left: `${(X(hover) / W) * 100}%` }}>
          <b>{String(data[hover][x])}</b>
          {series.map((s) => <div key={s.key}><i style={{ background: s.color }} />{s.label}: {format(+data[hover][s.key] || 0)}</div>)}
        </div>
      )}
      <details className="tableview"><summary>View as table</summary>
        <table><thead><tr><th>{x}</th>{series.map((s) => <th key={s.key}>{s.label}</th>)}</tr></thead>
          <tbody>{data.map((d, i) => <tr key={i}><td>{String(d[x])}</td>{series.map((s) => <td key={s.key}>{format(+d[s.key] || 0)}</td>)}</tr>)}</tbody></table>
      </details>
    </div>
  );
}

/** Single-series bar chart with rounded data-ends and per-bar hover title. */
export function BarChart({ data, x, y, color, height = 160 }: { data: Record<string, any>[]; x: string; y: string; color: string; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 640, H = height, m = { l: 32, r: 8, t: 8, b: 22 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const max = Math.max(1, ...data.map((d) => +d[y] || 0));
  const bw = iw / Math.max(data.length, 1);
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={y}>
        <line x1={m.l} x2={W - m.r} y1={m.t + ih} y2={m.t + ih} className="gridline" />
        <text x={m.l - 6} y={m.t + 8} textAnchor="end" className="axis">{max}</text>
        {data.map((d, i) => {
          const h = ((+d[y] || 0) / max) * ih;
          return (
            <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={m.l + i * bw} y={m.t} width={bw} height={ih} fill="transparent" />
              <rect x={m.l + i * bw + 3} y={m.t + ih - h} width={Math.max(bw - 6, 1)} height={h} rx={3} fill={color} opacity={hover === null || hover === i ? 1 : 0.55} />
              {i % Math.ceil(data.length / 7) === 0 && <text x={m.l + i * bw + bw / 2} y={H - 6} textAnchor="middle" className="axis">{String(d[x])}</text>}
            </g>
          );
        })}
      </svg>
      {hover !== null && <div className="tooltip" style={{ left: `${((m.l + hover * bw + bw / 2) / W) * 100}%` }}><b>{String(data[hover][x])}</b><div>{y.replace("_", " ")}: {data[hover][y]}</div></div>}
    </div>
  );
}

export function Kpi({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {hint && <div className="kpi-hint">{hint}</div>}
    </div>
  );
}
