"use client";

import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import type { TracePoint } from "@/lib/types";

const axis = { axisLine: { lineStyle: { color: "#3a4a57" } }, axisLabel: { color: "#8495a3", fontSize: 10 }, splitLine: { lineStyle: { color: "rgba(91,111,126,.16)" } } };

export function LongitudinalChart({ data, unit = "N·s·kg⁻¹", height = 250 }: { data: { week: number; arm: string; mean: number; sd: number }[]; unit?: string; height?: number }) {
  const option = useMemo<EChartsOption>(() => {
    const intervention = data.filter((item) => item.arm === "INTERVENTION");
    const comparison = data.filter((item) => item.arm === "COMPARISON");
    const toSeries = (rows: typeof data, name: string, color: string) => ({ name, type: "line" as const, smooth: true, symbol: "circle", symbolSize: 5, data: rows.map((row) => [row.week, row.mean]), lineStyle: { width: 2, color }, itemStyle: { color }, areaStyle: { color: `${color}12` }, markLine: name === "Intervention" ? { silent: true, symbol: "none", lineStyle: { color: "#62788a", type: "dashed" }, label: { color: "#9eafbb", formatter: "block" }, data: [{ xAxis: 3 }, { xAxis: 10 }] } : undefined });
    return { animationDuration: 450, grid: { left: 46, right: 18, top: 18, bottom: 30 }, tooltip: { trigger: "axis", backgroundColor: "#121d26", borderColor: "#30424f", textStyle: { color: "#d8e3e8", fontSize: 11 }, formatter: (params: unknown) => { const rows = params as { axisValue: number; marker: string; seriesName: string; value: [number, number] }[]; return `<strong>Week ${rows[0]?.axisValue}</strong><br/>${rows.map((row) => `${row.marker}${row.seriesName}: ${Number(row.value[1]).toFixed(3)} ${unit}`).join("<br/>")}`; } }, xAxis: { type: "category", data: Array.from({ length: 16 }, (_, index) => index + 1), ...axis, name: "week", nameTextStyle: { color: "#6f8594" } }, yAxis: { type: "value", ...axis, name: unit, nameTextStyle: { color: "#6f8594", fontSize: 10 }, scale: true }, series: [toSeries(intervention, "Intervention", "#59d6c7"), toSeries(comparison, "Comparison", "#e5b567")] } as EChartsOption;
  }, [data, unit]);
  return <ReactECharts option={option} style={{ height, width: "100%" }} notMerge lazyUpdate />;
}

export function ForceTraceChart({ trace, boundaries, height = 330 }: { trace: TracePoint[]; boundaries: Record<string, number>; height?: number }) {
  const option = useMemo<EChartsOption>(() => {
    const times = trace.map((point) => point.time_s);
    const values = trace.map((point) => point.force_n);
    const bodyWeight = trace[0]?.body_weight_n ?? 0;
    const shade = (from: string, to: string, color: string) => [{ xAxis: from }, { xAxis: to, itemStyle: { color } }];
    return { animation: false, grid: { left: 54, right: 20, top: 18, bottom: 36 }, tooltip: { trigger: "axis", backgroundColor: "#121d26", borderColor: "#30424f", textStyle: { color: "#d8e3e8", fontSize: 11 }, formatter: (params: unknown) => { const rows = params as { axisValue: number; value: [number, number] }[]; return `t = ${Number(rows[0]?.axisValue).toFixed(3)} s<br/>${Number(rows[0]?.value[1]).toFixed(1)} N`; } }, xAxis: { type: "category", data: times, ...axis, name: "time (s)", nameTextStyle: { color: "#6f8594" } }, yAxis: { type: "value", ...axis, name: "vertical GRF (N)", nameTextStyle: { color: "#6f8594", fontSize: 10 }, scale: true }, dataZoom: [{ type: "inside", xAxisIndex: 0, filterMode: "none" }], series: [{ name: "Vertical GRF", type: "line", showSymbol: false, data: values, lineStyle: { color: "#59d6c7", width: 1.5 }, areaStyle: { color: "rgba(89,214,199,.08)" }, markLine: { silent: true, symbol: "none", label: { color: "#9eafbb", fontSize: 10 }, lineStyle: { color: "#6b8190", type: "dashed" }, data: [{ yAxis: bodyWeight, name: "body weight" }, { xAxis: boundaries.movement_onset, name: "onset" }, { xAxis: boundaries.braking_end, name: "braking → propulsion" }, { xAxis: boundaries.takeoff, name: "takeoff" }, { xAxis: boundaries.landing, name: "landing" }] }, markArea: { silent: true, data: [...shade(String(boundaries.movement_onset), String(boundaries.unweighting_end), "rgba(229,181,103,.10)"), ...shade(String(boundaries.unweighting_end), String(boundaries.braking_end), "rgba(227,123,123,.11)"), ...shade(String(boundaries.braking_end), String(boundaries.takeoff), "rgba(89,214,199,.11)"), ...shade(String(boundaries.takeoff), String(boundaries.landing), "rgba(129,151,168,.08)")] } }] } as EChartsOption;
  }, [trace, boundaries]);
  return <ReactECharts option={option} style={{ height, width: "100%" }} notMerge lazyUpdate />;
}

export function DistributionChart({ values, title, unit, color = "#59d6c7", height = 190 }: { values: number[]; title: string; unit: string; color?: string; height?: number }) {
  const option = useMemo<EChartsOption>(() => {
    const bins = 10;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const width = (max - min) / bins || 1;
    const counts = Array.from({ length: bins }, (_, index) => values.filter((value) => value >= min + index * width && (index === bins - 1 ? value <= max : value < min + (index + 1) * width)).length);
    return { animationDuration: 300, grid: { left: 8, right: 8, top: 12, bottom: 28 }, tooltip: { trigger: "axis", backgroundColor: "#121d26", borderColor: "#30424f", textStyle: { color: "#d8e3e8" } }, xAxis: { type: "category", data: counts.map((_, index) => `${(min + index * width).toFixed(2)}`), ...axis }, yAxis: { type: "value", ...axis, minInterval: 1 }, series: [{ type: "bar", data: counts, barMaxWidth: 22, itemStyle: { color, borderRadius: [2, 2, 0, 0] } }], title: { text: `${title} (${unit})`, left: 0, top: 0, textStyle: { color: "#a8b8c2", fontSize: 11, fontWeight: 500 } } } as EChartsOption;
  }, [values, title, unit, color]);
  return <ReactECharts option={option} style={{ height, width: "100%" }} notMerge lazyUpdate />;
}

export function ModelChart({ states, height = 220 }: { states: { week: number; load: number; performance_state: number }[]; height?: number }) {
  const option = useMemo<EChartsOption>(() => ({ animationDuration: 350, grid: { left: 42, right: 18, top: 18, bottom: 30 }, legend: { textStyle: { color: "#8495a3", fontSize: 10 }, top: 0 }, tooltip: { trigger: "axis", backgroundColor: "#121d26", borderColor: "#30424f", textStyle: { color: "#d8e3e8" } }, xAxis: { type: "category", data: states.map((state) => state.week), ...axis, name: "week" }, yAxis: { type: "value", ...axis, scale: true }, series: [{ name: "load", type: "bar", data: states.map((state) => state.load), itemStyle: { color: "#334957" } }, { name: "performance state", type: "line", data: states.map((state) => state.performance_state), smooth: true, lineStyle: { color: "#59d6c7", width: 2 }, itemStyle: { color: "#59d6c7" } }] }) as EChartsOption, [states]);
  return <ReactECharts option={option} style={{ height, width: "100%" }} notMerge lazyUpdate />;
}

export function AthleteChart({ data, unit = "N·s·kg⁻¹", height = 260 }: { data: { week: number; value: number | null; rolling_mean: number | null; rolling_sd: number | null; quality_state?: string }[]; unit?: string; height?: number }) {
  const option = useMemo<EChartsOption>(() => {
    const observed = data.filter((item) => item.value !== null && item.quality_state !== "WARNING");
    const flagged = data.filter((item) => item.value !== null && item.quality_state === "WARNING");
    const band = data.map((item) => (item.rolling_mean === null || item.rolling_sd === null ? null : [item.week, item.rolling_mean + item.rolling_sd]));
    const lower = data.map((item) => (item.rolling_mean === null || item.rolling_sd === null ? null : [item.week, item.rolling_mean - item.rolling_sd])).reverse();
    return {
      animationDuration: 350,
      grid: { left: 56, right: 20, top: 34, bottom: 34 },
      legend: { textStyle: { color: "#8495a3", fontSize: 10 }, top: 0 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#121d26",
        borderColor: "#30424f",
        textStyle: { color: "#d8e3e8", fontSize: 11 },
        formatter: (params: unknown) => {
          const rows = params as { axisValue: string; marker: string; seriesName: string; value: [number, number] | number }[];
          const week = rows[0]?.axisValue;
          const lines = rows
            .filter((row) => Array.isArray(row.value) && Number.isFinite(Number((row.value as [number, number])[1])))
            .map((row) => `${row.marker}${row.seriesName}: ${Number((row.value as [number, number])[1]).toFixed(3)} ${unit}`);
          return `<strong>Week ${week}</strong><br/>${lines.join("<br/>")}`;
        },
      },
      xAxis: { type: "category", data: data.map((item) => item.week), ...axis, name: "week", nameTextStyle: { color: "#6f8594" } },
      yAxis: { type: "value", ...axis, name: unit, nameTextStyle: { color: "#6f8594", fontSize: 10 }, scale: true },
      series: [
        {
          name: "Observed",
          type: "scatter",
          symbolSize: 9,
          data: observed.map((item) => [item.week, item.value]),
          itemStyle: { color: "#59d6c7", borderColor: "#d8fffa", borderWidth: 1 },
        },
        {
          name: "Flagged week",
          type: "scatter",
          symbolSize: 9,
          symbol: "triangle",
          data: flagged.map((item) => [item.week, item.value]),
          itemStyle: { color: "#e5b567", borderColor: "#ffe6b0", borderWidth: 1 },
        },
        { name: "Weekly mean", type: "line", smooth: true, data: data.map((item) => item.value), lineStyle: { color: "#59d6c7", width: 2 }, itemStyle: { color: "#59d6c7" }, connectNulls: false },
        { name: "Rolling baseline", type: "line", smooth: true, data: data.map((item) => item.rolling_mean), lineStyle: { color: "#e5b567", width: 1.5, type: "dashed" }, itemStyle: { color: "#e5b567" }, connectNulls: false },
        { name: "Reference band", type: "line", data: [...band, ...lower], lineStyle: { opacity: 0 }, areaStyle: { color: "rgba(229,181,103,.10)" }, stack: "reference", symbol: "none" },
      ],
    } as EChartsOption;
  }, [data, unit]);
  return <ReactECharts option={option} style={{ height, width: "100%" }} notMerge lazyUpdate />;
}

export function ModelFitChart({
  weeks,
  observed,
  modelled,
  residuals,
  unit = "N·s·kg⁻¹",
  height = 300,
}: {
  weeks: number[];
  observed: number[];
  modelled: number[];
  residuals: number[];
  unit?: string;
  height?: number;
}) {
  const option = useMemo<EChartsOption>(() => {
    const residualValues = residuals.map((value) => Math.abs(value));
    const maxResidual = Math.max(...residualValues, 0.0001);
    return {
      animationDuration: 350,
      grid: [
        { left: 62, right: 22, top: 34, height: 168 },
        { left: 62, right: 22, top: 232, height: 60 },
      ],
      legend: { textStyle: { color: "#8495a3", fontSize: 10 }, top: 0 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#121d26",
        borderColor: "#30424f",
        textStyle: { color: "#d8e3e8", fontSize: 11 },
        formatter: (params: unknown) => {
          const rows = params as { axisValue: string; marker: string; seriesName: string; value: [number, number] }[];
          const lines = rows.map((row) => `${row.marker}${row.seriesName}: ${Number(row.value[1]).toFixed(3)}`);
          return `<strong>Week ${rows[0]?.axisValue}</strong><br/>${lines.join("<br/>")}`;
        },
      },
      xAxis: [
        { type: "category", data: weeks, ...axis, name: "week", gridIndex: 0, nameTextStyle: { color: "#6f8594" } },
        { type: "category", data: weeks, ...axis, gridIndex: 1, axisLabel: { show: false } },
      ],
      yAxis: [
        { type: "value", ...axis, name: unit, nameTextStyle: { color: "#6f8594", fontSize: 10 }, scale: true, gridIndex: 0 },
        { type: "value", ...axis, name: "|residual|", nameTextStyle: { color: "#6f8594", fontSize: 9 }, max: Number((maxResidual * 1.15).toFixed(4)), gridIndex: 1, splitNumber: 2 },
      ],
      series: [
        { name: "Observed CMJ", type: "scatter", symbolSize: 8, data: observed.map((value, index) => [weeks[index], value]), itemStyle: { color: "#59d6c7", borderColor: "#d8fffa", borderWidth: 1 }, xAxisIndex: 0, yAxisIndex: 0 },
        { name: "Modelled", type: "line", smooth: true, data: modelled.map((value, index) => [weeks[index], value]), lineStyle: { color: "#e5b567", width: 2 }, itemStyle: { color: "#e5b567" }, xAxisIndex: 0, yAxisIndex: 0 },
        { name: "|Residual|", type: "bar", data: residualValues, barMaxWidth: 14, itemStyle: { color: "#7f9bb0" }, xAxisIndex: 1, yAxisIndex: 1 },
      ],
    } as EChartsOption;
  }, [modelled, observed, residuals, unit, weeks]);
  return <ReactECharts option={option} style={{ height, width: "100%" }} notMerge lazyUpdate />;
}

export function Sparkline({ values, color = "#59d6c7", width = 90, height = 24 }: { values: number[]; color?: string; width?: number; height?: number }) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const points = values.map((value, index) => `${(index / Math.max(1, values.length - 1)) * width},${height - 3 - ((value - min) / Math.max(0.0001, max - min)) * (height - 6)}`).join(" ");
  return <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true"><polyline points={points} fill="none" stroke={color} strokeWidth="1.5" /></svg>;
}
