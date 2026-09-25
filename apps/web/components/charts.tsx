"use client";

import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import type { ExploreAthlete, ExploreContextRow, ExploreSummaryRow, FigureSeriesPoint, ScenarioState, TracePoint } from "@/lib/types";
import { formatSig } from "@/lib/scientific";

export const COLORS = {
  int: "#4fc4b6",
  cmp: "#86a0f0",
  signal: "#e3a74e",
  axis: "#3a4750",
  label: "#7d8a92",
  grid: "rgba(150,170,180,0.08)",
  text: "#dde4e8",
  excluded: "#e5716c",
  faint: "#56636b",
};

const FONT = "IBM Plex Mono, Consolas, monospace";

const tooltipBase = {
  backgroundColor: "#151a1e",
  borderColor: "#3a4750",
  borderWidth: 1,
  padding: [6, 8],
  textStyle: { color: COLORS.text, fontSize: 11, fontFamily: FONT },
  extraCssText: "border-radius:3px;box-shadow:0 8px 24px rgba(0,0,0,.45);",
};

function axisStyle(name: string, extra: Record<string, unknown> = {}) {
  return {
    name,
    nameTextStyle: { color: COLORS.label, fontSize: 10, fontFamily: FONT },
    axisLine: { lineStyle: { color: COLORS.axis } },
    axisTick: { lineStyle: { color: COLORS.axis } },
    axisLabel: { color: COLORS.label, fontSize: 10, fontFamily: FONT },
    splitLine: { lineStyle: { color: COLORS.grid } },
    ...extra,
  };
}

const armColor = (arm: string) => (arm === "INTERVENTION" ? COLORS.int : COLORS.cmp);
const armName = (arm: string) => (arm === "INTERVENTION" ? "Intervention" : "Comparison");

/**
 * 95% interval band drawn as one polygon per week-to-week segment. A custom
 * series is used because ECharts area stacking does not stack on a value axis,
 * and gaps (missing weeks) must stay visible rather than be bridged.
 */
function bandSeries(rows: { week: number; ci_low: number | null; ci_high: number | null }[], arm: string, xAxisIndex = 0, yAxisIndex = 0) {
  const points = rows.map((row) => [row.week, row.ci_low, row.ci_high]);
  return [
    {
      name: `${arm}-band`,
      type: "custom" as const,
      xAxisIndex,
      yAxisIndex,
      silent: true,
      z: 2,
      clip: true,
      tooltip: { show: false },
      data: points,
      encode: { x: 0, y: [1, 2] },
      renderItem: (params: { dataIndex: number }, api: { coord: (value: [number, number]) => [number, number] }) => {
        const current = points[params.dataIndex];
        const next = points[params.dataIndex + 1];
        if (!next || current[1] === null || current[2] === null || next[1] === null || next[2] === null) return null;
        return {
          type: "polygon",
          shape: { points: [api.coord([current[0] as number, current[1] as number]), api.coord([next[0] as number, next[1] as number]), api.coord([next[0] as number, next[2] as number]), api.coord([current[0] as number, current[2] as number])] },
          style: { fill: armColor(arm), opacity: 0.16 },
        };
      },
    },
  ];
}

export interface CohortChartProps {
  summary: ExploreSummaryRow[];
  athletes: ExploreAthlete[];
  context: ExploreContextRow[];
  unit: string;
  metricLabel: string;
  population: "ALL" | "INTERVENTION" | "COMPARISON";
  blockWeeks: [number, number];
  loadPeaks: number[];
  showContext: boolean;
  selectedAthlete?: string | null;
  selectedWeek?: number | null;
  onSelectAthlete?: (subjectId: string) => void;
  onSelectWeek?: (week: number) => void;
  height?: number;
}

/**
 * Cohort longitudinal trajectory: arm mean ± 95% CI across athletes, every
 * athlete as a thin trace, the intervention block, computed load peaks and an
 * optional training-load / match-exposure context panel on the same week axis.
 */
export function CohortLongitudinalChart(props: CohortChartProps) {
  const { summary, athletes, context, unit, metricLabel, population, blockWeeks, loadPeaks, showContext, selectedAthlete, selectedWeek, onSelectAthlete, onSelectWeek } = props;
  const arms = useMemo(() => (population === "ALL" ? ["INTERVENTION", "COMPARISON"] : [population]), [population]);
  const option = useMemo<EChartsOption>(() => {
    const mainHeight = showContext ? 218 : 290;
    const grids = [{ left: 58, right: 16, top: 16, height: mainHeight }];
    if (showContext) grids.push({ left: 58, right: 16, top: mainHeight + 44, height: 62 });
    const visibleAthletes = athletes.filter((athlete) => arms.includes(athlete.intervention_arm));
    const athleteSeries = visibleAthletes.map((athlete) => {
      const selected = athlete.subject_id === selectedAthlete;
      return {
        name: athlete.display_id,
        id: `ath-${athlete.subject_id}`,
        type: "line" as const,
        data: athlete.values.map((value, index) => [index + 1, value]),
        symbol: selected ? "circle" : "none",
        symbolSize: 5,
        showSymbol: selected,
        z: selected ? 10 : 1,
        lineStyle: { width: selected ? 2.2 : 1, color: selected ? COLORS.signal : armColor(athlete.intervention_arm), opacity: selected ? 1 : 0.16 },
        itemStyle: { color: COLORS.signal },
        emphasis: { focus: "none" as const, lineStyle: { width: 1.8, opacity: 0.8 } },
        connectNulls: false,
        triggerLineEvent: true,
        tooltip: { show: false },
      };
    });
    const meanSeries = arms.flatMap((arm) => {
      const rows = summary.filter((row) => row.arm === arm);
      return [
        ...bandSeries(rows, arm),
        {
          name: armName(arm),
          type: "line" as const,
          data: rows.map((row) => [row.week, row.mean]),
          symbol: "circle",
          symbolSize: 5,
          lineStyle: { width: 2.2, color: armColor(arm) },
          itemStyle: { color: armColor(arm), borderColor: "#0f1316", borderWidth: 1 },
          z: 6,
          connectNulls: false,
        },
      ];
    });
    const markArea = {
      silent: true,
      itemStyle: { color: "rgba(79,196,182,0.05)", borderColor: "rgba(79,196,182,0.25)", borderWidth: 0 },
      label: { color: COLORS.label, fontSize: 9.5, fontFamily: FONT, position: "insideTopLeft" as const },
      data: [[{ xAxis: blockWeeks[0] - 0.5, name: `strength block w${blockWeeks[0]}–${blockWeeks[1]}` }, { xAxis: blockWeeks[1] + 0.5 }]] as never,
    };
    const markLines = [
      ...loadPeaks.map((week) => ({ xAxis: week, name: `load peak w${week}`, lineStyle: { color: COLORS.signal, type: "dashed" as const, opacity: 0.6 }, label: { formatter: `load peak w${week}`, color: COLORS.signal, fontSize: 9.5, fontFamily: FONT } })),
      ...(selectedWeek ? [{ xAxis: selectedWeek, name: "selected", lineStyle: { color: "#dde4e8", type: "solid" as const, opacity: 0.35 }, label: { show: false } }] : []),
    ];
    const anchor = {
      name: "annotations",
      type: "line" as const,
      data: [],
      markArea,
      markLine: { silent: true, symbol: "none", data: markLines as never },
      tooltip: { show: false },
    };
    const contextSeries = showContext
      ? arms.flatMap((arm) => [
          {
            name: `${armName(arm)} load`,
            type: "bar" as const,
            xAxisIndex: 1,
            yAxisIndex: 1,
            data: context.filter((row) => row.arm === arm).map((row) => [row.week, row.training_impulse_au]),
            itemStyle: { color: armColor(arm), opacity: 0.45 },
            barGap: "10%",
            barMaxWidth: 9,
          },
          {
            name: `${armName(arm)} match min`,
            type: "line" as const,
            xAxisIndex: 1,
            yAxisIndex: 2,
            data: context.filter((row) => row.arm === arm).map((row) => [row.week, row.match_minutes]),
            symbol: "rect",
            symbolSize: 4,
            lineStyle: { width: 1, type: "dotted" as const, color: armColor(arm) },
            itemStyle: { color: armColor(arm) },
          },
        ])
      : [];
    const xAxis = [
      { type: "value" as const, min: 0.5, max: 16.5, interval: 1, gridIndex: 0, ...axisStyle(showContext ? "" : "week"), axisLabel: { color: COLORS.label, fontSize: 10, fontFamily: FONT, formatter: (value: number) => (Number.isInteger(value) ? String(value) : "") }, splitLine: { show: false } },
      ...(showContext ? [{ type: "value" as const, min: 0.5, max: 16.5, interval: 1, gridIndex: 1, ...axisStyle("week"), axisLabel: { color: COLORS.label, fontSize: 10, fontFamily: FONT, formatter: (value: number) => (Number.isInteger(value) ? String(value) : "") }, splitLine: { show: false } }] : []),
    ];
    const yAxis = [
      { type: "value" as const, scale: true, gridIndex: 0, ...axisStyle(unit, { nameLocation: "end" as const }) },
      ...(showContext
        ? [
            { type: "value" as const, gridIndex: 1, splitNumber: 2, ...axisStyle("AU"), axisLabel: { color: COLORS.label, fontSize: 9, fontFamily: FONT } },
            { type: "value" as const, gridIndex: 1, splitNumber: 2, position: "right" as const, ...axisStyle("min"), splitLine: { show: false }, axisLabel: { color: COLORS.label, fontSize: 9, fontFamily: FONT } },
          ]
        : []),
    ];
    return {
      animation: false,
      grid: grids,
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      tooltip: {
        ...tooltipBase,
        trigger: "axis",
        axisPointer: { type: "line", lineStyle: { color: "#56636b" } },
        formatter: (raw: unknown) => {
          const rows = Array.isArray(raw) ? (raw as { axisValue: number }[]) : [];
          const week = Math.round(Number(rows[0]?.axisValue ?? 0));
          if (!week) return "";
          const lines = arms.map((arm) => {
            const row = summary.find((item) => item.arm === arm && item.week === week);
            if (!row) return "";
            const missing = row.missing_athletes > 0 ? ` · ${row.missing_athletes} athlete(s) missing` : "";
            const excluded = row.excluded_trials > 0 ? ` · ${row.excluded_trials} trial excluded` : "";
            return `<span style="color:${armColor(arm)}">■</span> ${armName(arm)} ${formatSig(row.mean, 4)} ${unit} <span style="color:#7d8a92">[${formatSig(row.ci_low, 3)}, ${formatSig(row.ci_high, 3)}] n=${row.n}${missing}${excluded}</span>`;
          });
          const athlete = athletes.find((item) => item.subject_id === selectedAthlete);
          if (athlete) lines.push(`<span style="color:${COLORS.signal}">■</span> ${athlete.display_id} ${formatSig(athlete.values[week - 1], 4)} ${unit} <span style="color:#7d8a92">${athlete.n_valid[week - 1]}/2 valid</span>`);
          const load = arms.map((arm) => context.find((row) => row.arm === arm && row.week === week)).filter(Boolean) as ExploreContextRow[];
          if (showContext && load.length) lines.push(`<span style="color:#7d8a92">load ${load.map((row) => `${armName(row.arm).slice(0, 3)} ${row.training_impulse_au.toFixed(0)} AU / ${row.match_minutes.toFixed(0)} min`).join(" · ")}</span>`);
          return `<strong>Week ${week}</strong> · ${metricLabel}<br/>${lines.filter(Boolean).join("<br/>")}`;
        },
      },
      xAxis,
      yAxis,
      series: [...athleteSeries, ...meanSeries, anchor, ...contextSeries] as never,
    } as EChartsOption;
  }, [arms, athletes, blockWeeks, context, loadPeaks, metricLabel, selectedAthlete, selectedWeek, showContext, summary, unit]);

  const events = useMemo(
    () => ({
      click: (params: { seriesId?: string; componentType?: string; data?: unknown }) => {
        if (params.seriesId?.startsWith("ath-")) onSelectAthlete?.(params.seriesId.slice(4));
        const data = params.data as [number, number] | undefined;
        if (Array.isArray(data) && typeof data[0] === "number") onSelectWeek?.(Math.round(data[0]));
      },
    }),
    [onSelectAthlete, onSelectWeek],
  );
  return <ReactECharts option={option} style={{ height: props.height ?? (showContext ? 360 : 330), width: "100%" }} notMerge lazyUpdate onEvents={events} />;
}

export function GroupFigureChart({ series, unit, height = 260 }: { series: FigureSeriesPoint[]; unit: string; height?: number }) {
  const option = useMemo<EChartsOption>(() => {
    const arms = ["INTERVENTION", "COMPARISON"];
    return {
      animation: false,
      grid: { left: 58, right: 16, top: 26, bottom: 30 },
      legend: { top: 0, right: 8, textStyle: { color: COLORS.label, fontSize: 10, fontFamily: FONT }, itemWidth: 12, itemHeight: 2, data: arms.map(armName) },
      tooltip: {
        ...tooltipBase,
        trigger: "axis",
        formatter: (raw: unknown) => {
          const week = Math.round(Number((raw as { axisValue: number }[])[0]?.axisValue ?? 0));
          return `<strong>Week ${week}</strong><br/>${arms
            .map((arm) => {
              const row = series.find((item) => item.arm === arm && item.week === week);
              return row ? `<span style="color:${armColor(arm)}">■</span> ${armName(arm)} ${formatSig(row.mean, 4)} ${unit} [${formatSig(row.ci_low, 3)}, ${formatSig(row.ci_high, 3)}] n=${row.n}` : "";
            })
            .join("<br/>")}`;
        },
      },
      xAxis: { type: "value", min: 0.5, max: 16.5, interval: 1, ...axisStyle("week"), axisLabel: { color: COLORS.label, fontSize: 10, fontFamily: FONT, formatter: (value: number) => (Number.isInteger(value) ? String(value) : "") }, splitLine: { show: false } },
      yAxis: { type: "value", scale: true, ...axisStyle(unit) },
      series: [
        { name: "block", type: "line", data: [], markArea: { silent: true, itemStyle: { color: "rgba(79,196,182,0.05)" }, label: { color: COLORS.label, fontSize: 9.5, fontFamily: FONT, position: "insideTopLeft" }, data: [[{ xAxis: 2.5, name: "strength block w3–10" }, { xAxis: 10.5 }]] as never } },
        ...arms.flatMap((arm) => {
          const rows = series.filter((row) => row.arm === arm);
          return [
            ...bandSeries(rows, arm),
            { name: armName(arm), type: "line", data: rows.map((row) => [row.week, row.mean]), symbol: "circle", symbolSize: 5, lineStyle: { width: 2.2, color: armColor(arm) }, itemStyle: { color: armColor(arm) } },
          ];
        }),
      ] as never,
    } as EChartsOption;
  }, [series, unit]);
  return <ReactECharts option={option} style={{ height, width: "100%" }} notMerge lazyUpdate />;
}

const PHASE_COLORS: Record<string, string> = {
  QUIET_STANDING: "rgba(150,170,180,0.05)",
  UNWEIGHTING: "rgba(227,167,78,0.10)",
  BRAKING: "rgba(229,113,108,0.11)",
  PROPULSION: "rgba(79,196,182,0.12)",
  FLIGHT: "rgba(134,160,240,0.10)",
  LANDING: "rgba(150,170,180,0.08)",
};

export const PHASES: { key: string; label: string; from: string; to: string; color: string }[] = [
  { key: "UNWEIGHTING", label: "Unweighting", from: "movement_onset", to: "unweighting_end", color: "#e3a74e" },
  { key: "BRAKING", label: "Braking", from: "unweighting_end", to: "braking_end", color: "#e5716c" },
  { key: "PROPULSION", label: "Propulsion", from: "braking_end", to: "takeoff", color: "#4fc4b6" },
  { key: "FLIGHT", label: "Flight", from: "takeoff", to: "landing", color: "#86a0f0" },
];

/** Vertical GRF on a true time axis (s) with body-weight reference and phase boundaries. */
export function ForceTraceChart({ trace, boundaries, bodyWeight, height = 380 }: { trace: TracePoint[]; boundaries: Record<string, number>; bodyWeight: number; height?: number }) {
  const option = useMemo<EChartsOption>(() => {
    const data = trace.map((point) => [point.time_s, point.force_n]);
    const phaseAreas = PHASES.map((phase) => [
      { xAxis: boundaries[phase.from], name: phase.label, itemStyle: { color: PHASE_COLORS[phase.key] } },
      { xAxis: boundaries[phase.to] },
    ]);
    const landing = boundaries.landing;
    const end = trace.length ? trace[trace.length - 1].time_s : landing;
    const boundaryLines = [
      ["movement_onset", "onset"],
      ["unweighting_end", "unweighting end"],
      ["braking_end", "braking → propulsion"],
      ["takeoff", "takeoff"],
      ["landing", "landing"],
    ].map(([key, label], index) => ({ xAxis: boundaries[key], label: { formatter: label, color: COLORS.label, fontSize: 9, fontFamily: FONT, position: (index % 2 ? "insideEndBottom" : "insideEndTop") as "insideEndTop", rotate: 90 }, lineStyle: { color: "#56636b", type: "dashed" as const } }));
    const phaseAt = (t: number) => trace.reduce((closest, point) => (Math.abs(point.time_s - t) < Math.abs(closest.time_s - t) ? point : closest), trace[0])?.phase ?? "";
    return {
      animation: false,
      grid: { left: 62, right: 18, top: 30, bottom: 58 },
      tooltip: {
        ...tooltipBase,
        trigger: "axis",
        axisPointer: { type: "cross", lineStyle: { color: "#56636b" }, label: { backgroundColor: "#1f262c", fontFamily: FONT, fontSize: 10 } },
        formatter: (raw: unknown) => {
          const row = (raw as { value: [number, number] }[])[0];
          if (!row) return "";
          const [time, force] = row.value;
          return `t = ${time.toFixed(3)} s<br/>F = ${force.toFixed(1)} N<br/>${(force / bodyWeight).toFixed(2)} × BW · ${phaseAt(time).replaceAll("_", " ").toLowerCase()}`;
        },
      },
      xAxis: { type: "value", min: 0, max: Math.ceil(end * 20) / 20, ...axisStyle("time (s)", { nameLocation: "middle" as const, nameGap: 24 }) },
      yAxis: { type: "value", ...axisStyle("vertical GRF (N)"), min: 0 },
      dataZoom: [{ type: "inside", filterMode: "none" }, { type: "slider", height: 14, bottom: 8, borderColor: "#2a343b", fillerColor: "rgba(227,167,78,0.12)", handleStyle: { color: COLORS.signal }, textStyle: { color: COLORS.label, fontSize: 9 }, dataBackground: { lineStyle: { color: "#3a4750" }, areaStyle: { color: "#1a2025" } } }],
      series: [
        {
          name: "Vertical GRF",
          type: "line",
          data,
          showSymbol: false,
          sampling: "lttb",
          lineStyle: { width: 1.4, color: COLORS.text },
          markArea: { silent: true, label: { show: false }, data: phaseAreas as never },
          markLine: { silent: true, symbol: "none", data: [{ yAxis: bodyWeight, label: { formatter: `body weight ${bodyWeight.toFixed(0)} N`, color: COLORS.signal, fontSize: 9.5, fontFamily: FONT, position: "insideEndTop" }, lineStyle: { color: COLORS.signal, type: "solid", opacity: 0.7 } }, ...boundaryLines] as never },
        },
      ],
    } as EChartsOption;
  }, [bodyWeight, boundaries, trace]);
  return <ReactECharts option={option} style={{ height, width: "100%" }} notMerge lazyUpdate />;
}

export function ResidualByWeekChart({ rows, unit, height = 150 }: { rows: { week: number; mean_residual: number }[]; unit: string; height?: number }) {
  const option = useMemo<EChartsOption>(() => ({
    animation: false,
    grid: { left: 54, right: 10, top: 12, bottom: 26 },
    tooltip: { ...tooltipBase, trigger: "axis", formatter: (raw: unknown) => { const row = (raw as { value: [number, number] }[])[0]; return row ? `week ${row.value[0]}<br/>mean residual ${formatSig(row.value[1], 3)} ${unit}` : ""; } },
    xAxis: { type: "category", data: rows.map((row) => row.week), ...axisStyle("week", { nameGap: 4 }) },
    yAxis: { type: "value", ...axisStyle(unit) },
    series: [{ type: "bar", data: rows.map((row) => [String(row.week), row.mean_residual]), barMaxWidth: 12, itemStyle: { color: (item: { value: [string, number] }) => (item.value[1] >= 0 ? "#7f9aaa" : "#56636b") } as never, markLine: { silent: true, symbol: "none", data: [{ yAxis: 0 }], lineStyle: { color: "#7d8a92" }, label: { show: false } } }],
  }) as EChartsOption, [rows, unit]);
  return <ReactECharts option={option} style={{ height, width: "100%" }} notMerge lazyUpdate />;
}

export function QQChart({ points, height = 150 }: { points: { theoretical: number; observed: number }[]; height?: number }) {
  const option = useMemo<EChartsOption>(() => {
    const extent = Math.max(3, ...points.map((point) => Math.max(Math.abs(point.theoretical), Math.abs(point.observed))));
    const bound = 2 * Math.ceil(extent / 2);
    return {
      animation: false,
      grid: { left: 40, right: 10, top: 12, bottom: 26 },
      tooltip: { ...tooltipBase, trigger: "item", formatter: (raw: unknown) => { const value = (raw as { value: [number, number] }).value; return `normal quantile ${value[0].toFixed(2)}<br/>standardised residual ${value[1].toFixed(2)}`; } },
      xAxis: { type: "value", min: -bound, max: bound, interval: 2, ...axisStyle("N(0,1)", { nameGap: 4 }) },
      yAxis: { type: "value", min: -bound, max: bound, interval: 2, ...axisStyle("z") },
      series: [
        { type: "line", data: [[-bound, -bound], [bound, bound]], symbol: "none", lineStyle: { color: COLORS.signal, type: "dashed", width: 1 }, silent: true, tooltip: { show: false } },
        { type: "scatter", data: points.map((point) => [point.theoretical, point.observed]), symbolSize: 4, itemStyle: { color: "#9fb1bc" } },
      ],
    } as EChartsOption;
  }, [points]);
  return <ReactECharts option={option} style={{ height, width: "100%" }} notMerge lazyUpdate />;
}

export function DistributionChart({ values, unit, label, height = 200 }: { values: number[]; unit: string; label: string; height?: number }) {
  const option = useMemo<EChartsOption>(() => {
    const bins = 10;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const width = (max - min) / bins || 1;
    const counts = Array.from({ length: bins }, (_, index) => values.filter((value) => value >= min + index * width && (index === bins - 1 ? value <= max : value < min + (index + 1) * width)).length);
    return {
      animation: false,
      grid: { left: 40, right: 10, top: 14, bottom: 34 },
      tooltip: { ...tooltipBase, trigger: "axis", formatter: (raw: unknown) => { const row = (raw as { dataIndex: number; value: number }[])[0]; return row ? `${(min + row.dataIndex * width).toFixed(2)}–${(min + (row.dataIndex + 1) * width).toFixed(2)} ${unit}<br/>${row.value} athletes` : ""; } },
      xAxis: { type: "category", data: counts.map((_, index) => (min + (index + 0.5) * width).toFixed(1)), ...axisStyle(`${label} (${unit})`, { nameLocation: "middle" as const, nameGap: 22 }) },
      yAxis: { type: "value", minInterval: 1, ...axisStyle("athletes") },
      series: [{ type: "bar", data: counts, barCategoryGap: "12%", itemStyle: { color: "#7f9aaa" } }],
    } as EChartsOption;
  }, [label, unit, values]);
  return <ReactECharts option={option} style={{ height, width: "100%" }} notMerge lazyUpdate />;
}

export function ChangeScatterChart({ points, typicalError, unit, height = 220 }: { points: { subject_id: string; baseline: number; change: number }[]; typicalError?: number; unit: string; height?: number }) {
  const option = useMemo<EChartsOption>(() => ({
    animation: false,
    grid: { left: 54, right: 12, top: 14, bottom: 34 },
    tooltip: { ...tooltipBase, trigger: "item", formatter: (raw: unknown) => { const item = raw as { value: [number, number, string] }; return `${item.value[2]}<br/>baseline ${formatSig(item.value[0], 4)} ${unit}<br/>change ${formatSig(item.value[1], 3)} ${unit}`; } },
    xAxis: { type: "value", scale: true, ...axisStyle(`baseline (${unit})`, { nameLocation: "middle" as const, nameGap: 22 }) },
    yAxis: { type: "value", ...axisStyle(`change (${unit})`) },
    series: [{
      type: "scatter",
      data: points.map((point) => [point.baseline, point.change, point.subject_id]),
      symbolSize: 6,
      itemStyle: { color: "#9fb1bc" },
      markArea: typicalError ? { silent: true, itemStyle: { color: "rgba(227,167,78,0.07)" }, label: { show: true, formatter: "± typical error", color: COLORS.label, fontSize: 9, position: "insideTopLeft" }, data: [[{ yAxis: -typicalError }, { yAxis: typicalError }]] as never } : undefined,
    }],
  }) as EChartsOption, [points, typicalError, unit]);
  return <ReactECharts option={option} style={{ height, width: "100%" }} notMerge lazyUpdate />;
}

export function ModelScenarioChart({ states, observedWeeks, observed, unit, height = 300 }: { states: ScenarioState[]; observedWeeks: number[]; observed: number[]; unit: string; height?: number }) {
  const option = useMemo<EChartsOption>(() => {
    const history = states.filter((state) => state.segment === "OBSERVED_LOAD");
    const lastHistory = history[history.length - 1];
    const scenario = states.filter((state) => state.segment === "SCENARIO");
    const horizon = states.length;
    return {
      animation: false,
      grid: [{ left: 58, right: 16, top: 34, height: 158 }, { left: 58, right: 16, top: 222, height: 52 }],
      legend: { top: 2, right: 8, itemWidth: 12, itemHeight: 3, textStyle: { color: COLORS.label, fontSize: 10, fontFamily: FONT }, data: ["Observed (group mean)", "Fitted model", "Scenario simulation"] },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      tooltip: {
        ...tooltipBase,
        trigger: "axis",
        formatter: (raw: unknown) => {
          const week = Math.round(Number((raw as { axisValue: number }[])[0]?.axisValue ?? 0));
          const state = states.find((item) => item.week === week);
          const observedIndex = observedWeeks.indexOf(week);
          if (!state) return "";
          return `<strong>Week ${week}</strong> · ${state.segment === "SCENARIO" ? "scenario" : "observed load"}<br/>load ${state.load_au.toFixed(0)} AU<br/>modelled ${formatSig(state.modelled_performance, 4)} ${unit}${observedIndex >= 0 ? `<br/>observed ${formatSig(observed[observedIndex], 4)} ${unit}` : ""}`;
        },
      },
      xAxis: [
        { type: "value", min: 0.5, max: horizon + 0.5, interval: 1, gridIndex: 0, ...axisStyle(""), axisLabel: { show: false }, splitLine: { show: false } },
        { type: "value", min: 0.5, max: horizon + 0.5, interval: 1, gridIndex: 1, ...axisStyle("week"), axisLabel: { color: COLORS.label, fontSize: 10, fontFamily: FONT, formatter: (value: number) => (Number.isInteger(value) && value % 2 === 0 ? String(value) : "") }, splitLine: { show: false } },
      ],
      yAxis: [{ type: "value", scale: true, gridIndex: 0, ...axisStyle(unit) }, { type: "value", gridIndex: 1, splitNumber: 2, ...axisStyle("AU") }],
      series: [
        { name: "Observed (group mean)", type: "scatter", data: observedWeeks.map((week, index) => [week, observed[index]]), symbolSize: 6, itemStyle: { color: COLORS.text }, xAxisIndex: 0, yAxisIndex: 0 },
        { name: "Fitted model", type: "line", data: history.map((state) => [state.week, state.modelled_performance]), symbol: "none", lineStyle: { width: 2, color: COLORS.int }, xAxisIndex: 0, yAxisIndex: 0, markArea: scenario.length ? { silent: true, itemStyle: { color: "rgba(227,167,78,0.05)" }, label: { color: COLORS.signal, fontSize: 9.5, fontFamily: FONT, position: "insideTopLeft" }, data: [[{ xAxis: history.length + 0.5, name: "scenario" }, { xAxis: horizon + 0.5 }]] as never } : undefined },
        { name: "Scenario simulation", type: "line", data: [...(lastHistory ? [[lastHistory.week, lastHistory.modelled_performance]] : []), ...scenario.map((state) => [state.week, state.modelled_performance])], symbol: "circle", symbolSize: 4, lineStyle: { width: 2, type: "dashed", color: COLORS.signal }, itemStyle: { color: COLORS.signal }, xAxisIndex: 0, yAxisIndex: 0 },
        { name: "load", type: "bar", data: states.map((state) => ({ value: [state.week, state.load_au], itemStyle: { color: state.segment === "SCENARIO" ? "rgba(227,167,78,0.55)" : "#3d4b54" } })), barMaxWidth: 10, xAxisIndex: 1, yAxisIndex: 1 },
      ] as never,
    } as EChartsOption;
  }, [observed, observedWeeks, states, unit]);
  return <ReactECharts option={option} style={{ height, width: "100%" }} notMerge lazyUpdate />;
}
