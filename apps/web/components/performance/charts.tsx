"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { ReliabilityMetric, WeeklyLoad } from "@/lib/performance/types";
import { fmt } from "@/lib/performance/format";

function useSize<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const measure = () => setSize({ width: node.clientWidth, height: node.clientHeight });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return { ref, ...size };
}

function Tooltip({ x, y, children, containerWidth }: { x: number; y: number; children: ReactNode; containerWidth: number }) {
  const left = Math.min(Math.max(x + 10, 4), Math.max(4, containerWidth - 130));
  return <div className="pos-chart-tip" style={{ left, top: Math.max(y - 8, 4) }}>{children}</div>;
}

/* ------------------------------------------------------------------------- */
/* Weekly load line                                                          */
/* ------------------------------------------------------------------------- */

export function LoadLineChart({
  data,
  height = 220,
  label = "Weekly team mean training impulse, weeks 1 to 16, with match weeks highlighted.",
  reference,
  showAverage = true,
  unit = "AU",
  valueKey = "training_impulse_au",
}: {
  data: WeeklyLoad[];
  height?: number;
  label?: string;
  reference?: number | null;
  showAverage?: boolean;
  unit?: string;
  valueKey?: keyof WeeklyLoad;
}) {
  const { ref, width } = useSize<HTMLDivElement>();
  const [hover, setHover] = useState<{ index: number; x: number; y: number } | null>(null);
  const chartWidth = Math.max(width, 280);
  const margin = { l: 36, r: 12, t: 10, b: 23 };
  const plotW = chartWidth - margin.l - margin.r;
  const plotH = height - margin.t - margin.b;
  const values = data.map((row) => Number(row[valueKey] ?? 0));
  const all = [...values, reference ?? values[0] ?? 0];
  const minValue = Math.min(...all);
  const maxValue = Math.max(...all);
  const pad = Math.max((maxValue - minValue) * 0.18, maxValue * 0.05, 1);
  const lo = Math.max(0, minValue - pad);
  const hi = maxValue + pad;
  const xs = (week: number) => margin.l + ((week - 1) / Math.max(1, data.length - 1)) * plotW;
  const ys = (value: number) => margin.t + plotH - ((value - lo) / Math.max(1e-9, hi - lo)) * plotH;
  const points = data.map((row, index) => [xs(index + 1), ys(Number(row[valueKey] ?? 0))]);
  const average = useMemo(
    () =>
      data.map((row, index) => {
        const slice = data.slice(Math.max(0, index - 3), index + 1);
        return [xs(index + 1), ys(slice.reduce((sum, item) => sum + Number(item[valueKey] ?? 0), 0) / slice.length)];
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, width, valueKey, lo, hi],
  );

  return (
    <div ref={ref} style={{ width: "100%", height, position: "relative" }} role="img" aria-label={label}>
      {width > 0 && (
        <svg viewBox={`0 0 ${chartWidth} ${height}`} width="100%" height="100%">
          {data.map((row, index) =>
            row.match_week ? (
              <rect
                key={`match-${row.week}`}
                x={xs(index + 1) - plotW / Math.max(1, data.length * 2)}
                y={margin.t}
                width={plotW / Math.max(1, data.length)}
                height={plotH}
                fill="rgba(224,164,88,.06)"
              />
            ) : null,
          )}
          {Array.from({ length: 5 }).map((_, index) => {
            const value = lo + ((hi - lo) * index) / 4;
            return (
              <g key={`grid-${index}`}>
                <line x1={margin.l} y1={ys(value)} x2={chartWidth - margin.r} y2={ys(value)} stroke="#22333e" strokeWidth={1} />
                <text x={margin.l - 6} y={ys(value) + 3} fill="#566873" fontFamily="'IBM Plex Mono',monospace" fontSize={7.5} textAnchor="end">
                  {fmt(value, 0)}
                </text>
              </g>
            );
          })}
          {data.map((row, index) =>
            (index + 1) % 2 === 1 ? (
              <text key={`x-${row.week}`} x={xs(index + 1)} y={height - 7} fill="#566873" fontFamily="'IBM Plex Mono',monospace" fontSize={6.5} textAnchor="middle">
                W{index + 1}
              </text>
            ) : null,
          )}
          {reference !== undefined && reference !== null && (
            <>
              <line x1={margin.l} y1={ys(reference)} x2={chartWidth - margin.r} y2={ys(reference)} stroke="#7f919d" strokeWidth={1} strokeDasharray="4 3" opacity={0.7} />
              <text x={chartWidth - margin.r - 2} y={ys(reference) - 4} fill="#7f919d" fontFamily="'IBM Plex Mono',monospace" fontSize={6.5} textAnchor="end">
                reference {fmt(reference, 1)} {unit}
              </text>
            </>
          )}
          <path
            d={`M${points[0][0]},${margin.t + plotH} ` + points.map((point) => `L${point[0]},${point[1]}`).join(" ") + ` L${points[points.length - 1][0]},${margin.t + plotH} Z`}
            fill="rgba(95,212,232,.08)"
          />
          {showAverage && (
            <path d={average.map((point, index) => `${index === 0 ? "M" : "L"}${point[0]},${point[1]}`).join(" ")} fill="none" stroke="#7f919d" strokeWidth={1} strokeDasharray="3 3" />
          )}
          <path d={points.map((point, index) => `${index === 0 ? "M" : "L"}${point[0]},${point[1]}`).join(" ")} fill="none" stroke="#5fd4e8" strokeWidth={1.8} strokeLinejoin="round" />
          {points.map((point, index) => (
            <circle
              key={`dot-${data[index].week}`}
              cx={point[0]}
              cy={point[1]}
              r={index === data.length - 1 ? 3.6 : 2.2}
              fill={index === data.length - 1 ? "#c8f36b" : "#5fd4e8"}
              stroke="#0a1016"
              strokeWidth={1}
            />
          ))}
          <text x={xs(data.length) - 4} y={ys(Number(data[data.length - 1][valueKey] ?? 0)) - 9} fill="#c8f36b" fontFamily="'IBM Plex Mono',monospace" fontSize={7.5} textAnchor="end">
            {fmt(Number(data[data.length - 1][valueKey] ?? 0), Number(data[data.length - 1][valueKey] ?? 0) >= 100 ? 1 : 2)}
          </text>
          {hover && (
            <line x1={points[hover.index][0]} y1={margin.t} x2={points[hover.index][0]} y2={margin.t + plotH} stroke="#304552" strokeWidth={1} strokeDasharray="2 2" />
          )}
          <rect
            x={margin.l}
            y={margin.t}
            width={plotW}
            height={plotH}
            fill="transparent"
            onMouseLeave={() => setHover(null)}
            onMouseMove={(event) => {
              const box = event.currentTarget.getBoundingClientRect();
              const x = event.clientX - box.left + margin.l;
              const index = Math.max(0, Math.min(data.length - 1, Math.round(((x - margin.l) / plotW) * (data.length - 1))));
              setHover({ index, x: points[index][0], y: points[index][1] });
            }}
          />
        </svg>
      )}
      {hover && (
        <Tooltip x={hover.x} y={hover.y} containerWidth={chartWidth}>
          <b>Week {data[hover.index].week}</b> · {fmt(Number(data[hover.index][valueKey] ?? 0), 1)} {unit}
          <br />
          {data[hover.index].phase} {data[hover.index].match_week ? "· match week" : ""}
        </Tooltip>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------------- */
/* Generic individual trend with reference band and visible gaps             */
/* ------------------------------------------------------------------------- */

export function TrendChart({
  data,
  unit,
  height = 210,
  digits = 2,
  band,
  bandLabel,
  reference,
  referenceLabel,
  color = "#5fd4e8",
  label = "Individual longitudinal trend with a reference band and visible missing values.",
}: {
  data: { week: number; value: number | null; phase?: string }[];
  unit: string;
  height?: number;
  digits?: number;
  band?: [number, number] | null;
  bandLabel?: string;
  reference?: number | null;
  referenceLabel?: string;
  color?: string;
  label?: string;
}) {
  const { ref, width } = useSize<HTMLDivElement>();
  const [hover, setHover] = useState<{ index: number; x: number; y: number } | null>(null);
  const chartWidth = Math.max(width, 280);
  const margin = { l: 38, r: 12, t: 10, b: 22 };
  const plotW = chartWidth - margin.l - margin.r;
  const plotH = height - margin.t - margin.b;
  const values = data.map((item) => item.value).filter((value): value is number => value !== null);
  const bandValues = band ? [band[0], band[1]] : [];
  const referenceValues = reference !== undefined && reference !== null ? [reference] : [];
  const all = [...values, ...bandValues, ...referenceValues];
  const min = all.length ? Math.min(...all) : 0;
  const max = all.length ? Math.max(...all) : 1;
  const pad = Math.max((max - min) * 0.18, Math.abs(max) * 0.04, 0.1);
  const lo = min - pad;
  const hi = max + pad;
  const xs = (week: number) => margin.l + ((week - 1) / 15) * plotW;
  const ys = (value: number) => margin.t + plotH - ((value - lo) / Math.max(1e-9, hi - lo)) * plotH;
  const segments = data.reduce<{ week: number; value: number }[][]>((groups, item) => {
    if (item.value === null) {
      if (groups[groups.length - 1]?.length) groups.push([]);
      return groups;
    }
    if (!groups.length || groups[groups.length - 1].length === 0) groups.push([]);
    groups[groups.length - 1].push({ week: item.week, value: item.value });
    return groups;
  }, []).filter((group) => group.length > 0);

  return (
    <div ref={ref} style={{ width: "100%", height, position: "relative" }} role="img" aria-label={label}>
      {width > 0 && (
        <svg viewBox={`0 0 ${chartWidth} ${height}`} width="100%" height="100%">
          {band && (
            <>
              <rect x={margin.l} y={ys(band[1])} width={plotW} height={Math.max(1, ys(band[0]) - ys(band[1]))} fill="rgba(200,243,107,.08)" />
              {bandLabel ? <text x={margin.l + 3} y={ys(band[1]) + 7} fill="#7f919d" fontFamily="'IBM Plex Mono',monospace" fontSize={6}>{bandLabel}</text> : null}
            </>
          )}
          {Array.from({ length: 5 }).map((_, index) => {
            const value = lo + ((hi - lo) * index) / 4;
            return (
              <g key={`tg-${index}`}>
                <line x1={margin.l} y1={ys(value)} x2={chartWidth - margin.r} y2={ys(value)} stroke="#22333e" strokeWidth={1} />
                <text x={margin.l - 5} y={ys(value) + 3} fill="#566873" fontFamily="'IBM Plex Mono',monospace" fontSize={6.5} textAnchor="end">{fmt(value, 0)}</text>
              </g>
            );
          })}
          {data.map((item, index) => (index % 2 === 0 ? <text key={`tw-${item.week}`} x={xs(item.week)} y={height - 6} fill="#566873" fontFamily="'IBM Plex Mono',monospace" fontSize={6} textAnchor="middle">W{item.week}</text> : null))}
          {reference !== undefined && reference !== null && (
            <>
              <line x1={margin.l} y1={ys(reference)} x2={chartWidth - margin.r} y2={ys(reference)} stroke="#7f919d" strokeWidth={1} strokeDasharray="4 3" />
              <text x={chartWidth - margin.r - 2} y={ys(reference) - 3} fill="#7f919d" fontFamily="'IBM Plex Mono',monospace" fontSize={6} textAnchor="end">{referenceLabel ?? "reference"} {fmt(reference, digits)} {unit}</text>
            </>
          )}
          {segments.map((segment, index) => (
            <path key={`seg-${index}`} d={segment.map((point, i) => `${i === 0 ? "M" : "L"}${xs(point.week)},${ys(point.value)}`).join(" ")} fill="none" stroke={color} strokeWidth={1.8} strokeLinejoin="round" />
          ))}
          {data.map((item) => item.value !== null ? (
            <circle key={`tdot-${item.week}`} cx={xs(item.week)} cy={ys(item.value)} r={2.4} fill={color} stroke="#0a1016" strokeWidth={1} />
          ) : (
            <circle key={`tmiss-${item.week}`} cx={xs(item.week)} cy={margin.t + plotH - 2} r={1.8} fill="#ef6b63" opacity={0.8} />
          ))}
          {hover && data[hover.index]?.value !== null && (
            <line x1={xs(data[hover.index].week)} y1={margin.t} x2={xs(data[hover.index].week)} y2={margin.t + plotH} stroke="#304552" strokeDasharray="2 2" />
          )}
          <rect
            x={margin.l}
            y={margin.t}
            width={plotW}
            height={plotH}
            fill="transparent"
            onMouseLeave={() => setHover(null)}
            onMouseMove={(event) => {
              const box = event.currentTarget.getBoundingClientRect();
              const x = event.clientX - box.left + margin.l;
              const index = Math.max(0, Math.min(data.length - 1, Math.round(((x - margin.l) / plotW) * 15)));
              const value = data[index]?.value;
              if (value !== null && value !== undefined) setHover({ index, x: xs(data[index].week), y: ys(value) });
              else setHover(null);
            }}
          />
        </svg>
      )}
      {hover && data[hover.index]?.value !== null && (
        <Tooltip x={hover.x} y={hover.y} containerWidth={chartWidth}>
          <b>Week {data[hover.index].week}</b> · {fmt(data[hover.index].value, digits)} {unit}
          <br />
          {data[hover.index].phase ?? "observed"}
        </Tooltip>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------------- */
/* Force–time chart                                                          */
/* ------------------------------------------------------------------------- */

const PHASE_COLORS: Record<string, string> = {
  QUIET_STANDING: "rgba(127,145,157,.08)",
  UNWEIGHTING: "rgba(95,212,232,.08)",
  BRAKING: "rgba(224,164,88,.10)",
  PROPULSION: "rgba(200,243,107,.10)",
  FLIGHT: "rgba(167,139,250,.10)",
  LANDING: "rgba(239,107,99,.10)",
};

export function ForceTimeChart({
  trace,
  bodyWeight,
  height = 220,
  label = "Vertical ground reaction force over time for a countermovement jump, with quiet standing, unweighting, braking, propulsion, flight and landing phases.",
}: {
  trace: { time_s: number; force_n: number; phase: string }[];
  bodyWeight: number;
  height?: number;
  label?: string;
}) {
  const { ref, width } = useSize<HTMLDivElement>();
  const [hover, setHover] = useState<{ index: number; x: number; y: number } | null>(null);
  const chartWidth = Math.max(width, 280);
  const margin = { l: 40, r: 8, t: 10, b: 20 };
  const plotW = chartWidth - margin.l - margin.r;
  const plotH = height - margin.t - margin.b;
  const tMax = trace.length ? trace[trace.length - 1].time_s : 1;
  const fMin = Math.min(0, ...trace.map((point) => point.force_n));
  const fMax = Math.max(...trace.map((point) => point.force_n), bodyWeight) + 80;
  const xs = (t: number) => margin.l + (t / Math.max(1e-9, tMax)) * plotW;
  const ys = (f: number) => margin.t + plotH - ((f - fMin) / Math.max(1e-9, fMax - fMin)) * plotH;
  const phases = useMemo(() => {
    const groups: { phase: string; start: number; end: number }[] = [];
    for (const point of trace) {
      const last = groups[groups.length - 1];
      if (!last || last.phase !== point.phase) groups.push({ phase: point.phase, start: point.time_s, end: point.time_s });
      else last.end = point.time_s;
    }
    return groups;
  }, [trace]);
  const path = trace.map((point, index) => `${index === 0 ? "M" : "L"}${xs(point.time_s)},${ys(point.force_n)}`).join(" ");
  const peak = trace.reduce((best, point) => (point.force_n > best.force_n ? point : best), trace[0] ?? { time_s: 0, force_n: 0, phase: "" });
  return (
    <div ref={ref} style={{ width: "100%", height, position: "relative" }} role="img" aria-label={label}>
      {width > 0 && (
        <svg viewBox={`0 0 ${chartWidth} ${height}`} width="100%" height="100%">
          {phases.map((phase) => (
            <rect
              key={`${phase.phase}-${phase.start}`}
              x={xs(phase.start)}
              y={margin.t}
              width={Math.max(1, xs(phase.end) - xs(phase.start))}
              height={plotH}
              fill={PHASE_COLORS[phase.phase] ?? "transparent"}
            />
          ))}
          {Array.from({ length: 5 }).map((_, index) => {
            const value = fMin + ((fMax - fMin) * index) / 4;
            return (
              <g key={`fgrid-${index}`}>
                <line x1={margin.l} y1={ys(value)} x2={chartWidth - margin.r} y2={ys(value)} stroke="#22333e" strokeWidth={1} />
                <text x={margin.l - 5} y={ys(value) + 3} fill="#566873" fontFamily="'IBM Plex Mono',monospace" fontSize={6.5} textAnchor="end">
                  {fmt(value, 0)}
                </text>
              </g>
            );
          })}
          <line x1={margin.l} y1={ys(bodyWeight)} x2={chartWidth - margin.r} y2={ys(bodyWeight)} stroke="#e0a458" strokeWidth={1} strokeDasharray="3 3" opacity={0.7} />
          <text x={chartWidth - margin.r - 2} y={ys(bodyWeight) - 3} fill="#e0a458" fontFamily="'IBM Plex Mono',monospace" fontSize={6} textAnchor="end">
            body weight
          </text>
          <path d={path} fill="none" stroke="#5fd4e8" strokeWidth={1.5} strokeLinejoin="round" />
          {trace.length > 0 && (
            <>
              <circle cx={xs(peak.time_s)} cy={ys(peak.force_n)} r={2.6} fill="#c8f36b" />
              <text x={xs(peak.time_s) + 4} y={ys(peak.force_n) - 4} fill="#c8f36b" fontFamily="'IBM Plex Mono',monospace" fontSize={6.2}>
                peak {fmt(peak.force_n, 0)} N
              </text>
            </>
          )}
          {phases.map((phase) => (
            <text key={`label-${phase.phase}-${phase.start}`} x={xs(phase.start) + 2} y={height - 5} fill="#566873" fontFamily="'IBM Plex Mono',monospace" fontSize={5.8}>
              {phase.phase.slice(0, 4)}
            </text>
          ))}
          <text x={margin.l} y={height - 5} fill="#566873" fontFamily="'IBM Plex Mono',monospace" fontSize={6.2}>time (s)</text>
          <text x={9} y={margin.t + plotH / 2} fill="#566873" fontFamily="'IBM Plex Mono',monospace" fontSize={6.2} textAnchor="middle" transform={`rotate(-90 9 ${margin.t + plotH / 2})`}>force (N)</text>
          {hover && <line x1={xs(trace[hover.index].time_s)} y1={margin.t} x2={xs(trace[hover.index].time_s)} y2={margin.t + plotH} stroke="#304552" strokeWidth={1} strokeDasharray="2 2" />}
          <rect
            x={margin.l}
            y={margin.t}
            width={plotW}
            height={plotH}
            fill="transparent"
            onMouseLeave={() => setHover(null)}
            onMouseMove={(event) => {
              const box = event.currentTarget.getBoundingClientRect();
              const x = event.clientX - box.left + margin.l;
              const t = ((x - margin.l) / plotW) * tMax;
              let nearest = 0;
              let distance = Infinity;
              trace.forEach((point, index) => {
                const d = Math.abs(point.time_s - t);
                if (d < distance) { distance = d; nearest = index; }
              });
              setHover({ index: nearest, x: xs(trace[nearest].time_s), y: ys(trace[nearest].force_n) });
            }}
          />
        </svg>
      )}
      {hover && (
        <Tooltip x={hover.x} y={hover.y} containerWidth={chartWidth}>
          <b>{trace[hover.index].time_s.toFixed(3)} s</b> · {fmt(trace[hover.index].force_n, 0)} N
          <br />
          {trace[hover.index].phase.replaceAll("_", " ").toLowerCase()}
        </Tooltip>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------------- */
/* Sparkline                                                                 */
/* ------------------------------------------------------------------------- */

export function Sparkline({ values, width = 110, height = 26, color = "#5fd4e8", band }: { values: (number | null)[]; width?: number; height?: number; color?: string; band?: [number, number] | null }) {
  const clean = values.map((value, index) => ({ value, index })).filter((item) => item.value !== null) as { value: number; index: number }[];
  if (!clean.length) return <div style={{ width, height }} />;
  const min = Math.min(...clean.map((item) => item.value), band?.[0] ?? Infinity);
  const max = Math.max(...clean.map((item) => item.value), band?.[1] ?? -Infinity);
  const xs = (index: number) => 2 + (index / Math.max(1, values.length - 1)) * (width - 4);
  const ys = (value: number) => height - 3 - ((value - min) / Math.max(1e-9, max - min)) * (height - 6);
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" style={{ display: "block" }}>
      {band && <rect x={0} y={ys(band[1])} width={width} height={Math.max(1, ys(band[0]) - ys(band[1]))} fill="rgba(200,243,107,.08)" />}
      <path d={clean.map((item, index) => `${index === 0 ? "M" : "L"}${xs(item.index)},${ys(item.value)}`).join(" ")} fill="none" stroke={color} strokeWidth={1.4} />
      <circle cx={xs(clean[clean.length - 1].index)} cy={ys(clean[clean.length - 1].value)} r={2} fill={color} />
    </svg>
  );
}

/* ------------------------------------------------------------------------- */
/* Planned vs actual bars                                                    */
/* ------------------------------------------------------------------------- */

export function PlannedActualBars({
  weeks,
  actual,
  planned,
  height = 150,
  unit = "AU",
}: {
  weeks: number[];
  actual: (number | null)[];
  planned: (number | null)[];
  height?: number;
  unit?: string;
}) {
  const { ref, width } = useSize<HTMLDivElement>();
  const [hover, setHover] = useState<{ index: number; x: number; y: number } | null>(null);
  const chartWidth = Math.max(width, 280);
  const margin = { l: 32, r: 8, t: 8, b: 18 };
  const plotW = chartWidth - margin.l - margin.r;
  const plotH = height - margin.t - margin.b;
  const max = Math.max(...actual.filter((value): value is number => value !== null), ...planned.filter((value): value is number => value !== null), 1) * 1.12;
  const slot = plotW / Math.max(1, weeks.length);
  const ys = (value: number) => margin.t + plotH - (value / max) * plotH;
  return (
    <div ref={ref} style={{ width: "100%", height, position: "relative" }} role="img" aria-label="Planned versus actual weekly training load with a separate planned marker for each week.">
      {width > 0 && (
        <svg viewBox={`0 0 ${chartWidth} ${height}`} width="100%" height="100%">
          {[0, max / 2, max].map((value, index) => (
            <g key={`pg-${index}`}>
              <line x1={margin.l} y1={ys(value)} x2={chartWidth - margin.r} y2={ys(value)} stroke="#22333e" strokeWidth={1} />
              <text x={margin.l - 4} y={ys(value) + 3} fill="#566873" fontFamily="'IBM Plex Mono',monospace" fontSize={6.5} textAnchor="end">{fmt(value, 0)}</text>
            </g>
          ))}
          {weeks.map((week, index) => {
            const x = margin.l + index * slot;
            const actualValue = actual[index];
            const plannedValue = planned[index];
            return (
              <g key={`bar-${week}`} onMouseEnter={() => setHover({ index, x: x + slot / 2, y: actualValue ? ys(actualValue) : margin.t })} onMouseLeave={() => setHover(null)}>
                {actualValue !== null && <rect x={x + slot * 0.18} y={ys(actualValue)} width={slot * 0.42} height={plotH - (ys(actualValue) - margin.t)} fill="#5fd4e8" opacity={0.55} />}
                {plannedValue !== null && <line x1={x + slot * 0.12} y1={ys(plannedValue)} x2={x + slot * 0.86} y2={ys(plannedValue)} stroke="#c8f36b" strokeWidth={1.4} strokeDasharray="3 2" />}
                {(index + 1) % 2 === 1 && <text x={x + slot / 2} y={height - 5} fill="#566873" fontFamily="'IBM Plex Mono',monospace" fontSize={6} textAnchor="middle">W{week}</text>}
              </g>
            );
          })}
        </svg>
      )}
      {hover && (
        <Tooltip x={hover.x} y={hover.y} containerWidth={chartWidth}>
          <b>Week {weeks[hover.index]}</b><br />
          actual {actual[hover.index] === null ? "not recorded" : `${fmt(actual[hover.index], 1)} ${unit}`}<br />
          planned {planned[hover.index] === null ? "not recorded" : `${fmt(planned[hover.index], 1)} ${unit}`}
        </Tooltip>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------------- */
/* Squad heatmap                                                             */
/* ------------------------------------------------------------------------- */

export function SquadHeatmap({
  athletes,
  weeks,
  height = 188,
  metric = "readiness",
}: {
  athletes: { display_id: string; position: string; weeks: { week: number; readiness: number | null; cmj_delta_pct?: number | null }[] }[];
  weeks: number[];
  height?: number;
  metric?: "readiness" | "cmj";
}) {
  const { ref, width } = useSize<HTMLDivElement>();
  const [hover, setHover] = useState<{ x: number; y: number; text: string } | null>(null);
  const chartWidth = Math.max(width, 280);
  const labelW = 54;
  const cellW = Math.max(6, (chartWidth - labelW - 4) / Math.max(1, weeks.length));
  const cellH = Math.max(3, (height - 18) / Math.max(1, athletes.length));
  const color = (value: number | null, kind: "readiness" | "cmj") => {
    if (value === null) return "#1a2a35";
    if (kind === "readiness") {
      if (value < 5.5) return "#ef6b63";
      if (value < 6.5) return "#e0a458";
      if (value < 7.5) return "#5fd4e8";
      return "#c8f36b";
    }
    if (value < -5) return "#ef6b63";
    if (value < -2.5) return "#e0a458";
    if (value < 2.5) return "#5fd4e8";
    return "#c8f36b";
  };
  return (
    <div ref={ref} style={{ width: "100%", height, position: "relative" }}>
      {width > 0 && (
        <svg viewBox={`0 0 ${chartWidth} ${height}`} width="100%" height="100%" role="img" aria-label={`Squad ${metric} heatmap, athletes by week. Missing values are visible as dark cells.`}>
          {weeks.map((week, index) => (
            <text key={`hw-${week}`} x={labelW + index * cellW + cellW / 2} y={8} fill="#566873" fontFamily="'IBM Plex Mono',monospace" fontSize={5.5} textAnchor="middle">{week % 2 === 1 ? `W${week}` : ""}</text>
          ))}
          {athletes.map((athlete, row) => (
            <g key={athlete.display_id}>
              <text x={0} y={15 + row * cellH + cellH / 2 + 2} fill="#7f919d" fontFamily="'IBM Plex Mono',monospace" fontSize={6}>{athlete.display_id}</text>
              {weeks.map((week, column) => {
                const cell = athlete.weeks.find((item) => item.week === week);
                const value = metric === "readiness" ? cell?.readiness ?? null : cell?.cmj_delta_pct ?? null;
                return (
                  <rect
                    key={`${athlete.display_id}-${week}`}
                    x={labelW + column * cellW + 0.5}
                    y={13 + row * cellH + 0.5}
                    width={Math.max(1, cellW - 1)}
                    height={Math.max(1, cellH - 1)}
                    fill={color(value, metric)}
                    opacity={value === null ? 0.55 : 0.9}
                    onMouseEnter={() => setHover({
                      x: labelW + column * cellW + cellW / 2,
                      y: 13 + row * cellH,
                      text: `${athlete.display_id} · W${week} · ${value === null ? "no data" : `${fmt(value, 1)}${metric === "readiness" ? "/10" : "%"}`}`,
                    })}
                    onMouseLeave={() => setHover(null)}
                  />
                );
              })}
            </g>
          ))}
        </svg>
      )}
      {hover && (
        <div className="pos-heat-tip" style={{ left: Math.min(hover.x + 8, chartWidth - 120), top: Math.max(4, hover.y - 18) }}>{hover.text}</div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------------- */
/* Reliability forest                                                       */
/* ------------------------------------------------------------------------- */

export function ReliabilityForest({ metrics }: { metrics: ReliabilityMetric[] }) {
  return (
    <div className="pos-reliability">
      {metrics.map((metric) => {
        const icc = metric.icc ?? 0;
        const low = metric.icc_ci_low ?? icc;
        const high = metric.icc_ci_high ?? icc;
        return (
          <div key={metric.metric_id} className="pos-rel-card">
            <div className="k">{metric.label}</div>
            <div className="v">{metric.icc === null ? "—" : fmt(metric.icc, 2)}<span>ICC</span></div>
            <div className="s">95% CI {fmt(low, 2)}–{fmt(high, 2)}</div>
            <div className="s">TE {fmt(metric.typical_error, metric.unit === "N" ? 1 : 3)} {metric.unit} · CV {fmt(metric.mean_cv_percent, 1)}%</div>
            <div className="s">n={metric.n_subjects} · k={metric.trials_per_subject} trials</div>
            <div style={{ marginTop: 5 }}>
              <div style={{ height: 3, background: "#23333e", position: "relative" }}>
                <div style={{ position: "absolute", left: `${Math.max(0, low) * 100}%`, width: `${Math.max(1, (high - low) * 100)}%`, top: 0, bottom: 0, background: "#304552" }} />
                <div style={{ position: "absolute", left: `${Math.max(0, Math.min(1, icc)) * 100}%`, top: -2, width: 2, height: 7, background: "#c8f36b" }} />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------------- */
/* Speed zones                                                              */
/* ------------------------------------------------------------------------- */

export function SpeedZoneBars({ distance, hsr, maxSpeed }: { distance: number; hsr: number; maxSpeed: number }) {
  const zones = [
    { label: "0–2", value: Math.max(0, distance - hsr), color: "#304552" },
    { label: "2–4.5", value: 0, color: "#3f6270" },
    { label: "4.5–5.5", value: 0, color: "#3c8b99" },
    { label: "≥5.5", value: hsr, color: "#c8f36b" },
  ];
  const total = Math.max(1, zones.reduce((sum, zone) => sum + zone.value, 0));
  return (
    <div>
      <div style={{ display: "flex", height: 16, gap: 1 }}>
        {zones.map((zone) => (
          <div key={zone.label} title={`${zone.label} m·s⁻¹ · ${fmt(zone.value, 1)} m`} style={{ width: `${(zone.value / total) * 100}%`, background: zone.color, minWidth: zone.value > 0 ? 2 : 0 }} />
        ))}
      </div>
      <div className="pos-legend-row" style={{ marginTop: 4 }}>
        {zones.map((zone) => (
          <span key={zone.label}><i style={{ display: "inline-block", width: 6, height: 6, background: zone.color, marginRight: 3 }} />{zone.label} m·s⁻¹ · {fmt(zone.value, 0)} m</span>
        ))}
        <span style={{ marginLeft: "auto", color: "#7f919d" }}>max {fmt(maxSpeed, 1)} m·s⁻¹</span>
      </div>
    </div>
  );
}
