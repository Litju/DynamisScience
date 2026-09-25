"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { AlertTriangle, GitBranch, Microscope, ScanLine } from "lucide-react";
import type { Arm } from "@/lib/types";
import { ARM_LABEL, formatSig, shortChecksum } from "@/lib/scientific";

/** Maps the scientific status vocabulary to a colour token. The text is always rendered. */
export function toneFor(state: string | null | undefined): string {
  switch (state) {
    case "VALID":
    case "COMPLETED":
    case "CURRENT":
    case "ACTIVE":
    case "COMPUTED":
    case "CONVERGED":
    case "REPRODUCED":
    case "CITED":
      return "tone-valid";
    case "WARNING":
    case "DRAFT":
    case "INCOMPLETE":
    case "PROTOTYPE":
    case "MISSING":
    case "NOT RUN":
    case "FALLBACK":
      return "tone-warning";
    case "EXCLUDED":
    case "FAILED":
    case "UNAVAILABLE":
      return "tone-excluded";
    case "EXPLORATORY":
    case "DESCRIPTIVE":
      return "tone-exploratory";
    case "FROZEN":
    case "PLANNED":
    case "CONFIRMATORY":
      return "tone-frozen";
    case "SYNTHETIC":
      return "tone-synthetic";
    case "SUPERSEDED":
    case "ROADMAP":
      return "tone-superseded";
    default:
      return "tone-neutral";
  }
}

export function State({ children, tone, plain = false, title }: { children: string; tone?: string; plain?: boolean; title?: string }) {
  return <span className={`state ${tone ?? toneFor(children)} ${plain ? "plain" : ""}`} title={title}>{children}</span>;
}

export function ArmLabel({ arm }: { arm: Arm | string }) {
  const known = arm === "INTERVENTION" || arm === "COMPARISON";
  return <span className={`arm ${arm === "INTERVENTION" ? "arm-int" : "arm-cmp"}`}>{known ? ARM_LABEL[arm as Arm] : arm}</span>;
}

export function Button({ children, variant = "default", size = "md", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "primary" | "ghost"; size?: "sm" | "md" }) {
  return (
    <button type="button" className={`btn ${variant === "primary" ? "btn-primary" : variant === "ghost" ? "btn-ghost" : ""} ${size === "sm" ? "btn-sm" : ""} ${className}`} {...props}>
      {children}
    </button>
  );
}

export function IconButton({ label, children, onClick, pressed, disabled }: { label: string; children: ReactNode; onClick?: () => void; pressed?: boolean; disabled?: boolean }) {
  return (
    <button type="button" className="icon-btn" aria-label={label} title={label} onClick={onClick} aria-pressed={pressed} disabled={disabled}>
      {children}
    </button>
  );
}

export function KV({ rows }: { rows: [string, ReactNode, ("mono" | undefined)?][] }) {
  return (
    <dl className="kv">
      {rows.map(([label, value, style]) => (
        <div key={label} style={{ display: "contents" }}>
          <dt>{label}</dt>
          <dd className={style === "mono" ? "mono" : undefined}>{value === null || value === undefined || value === "" ? "—" : value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Readout({ label, value, unit, detail, large = false }: { label: string; value: ReactNode; unit?: string; detail?: ReactNode; large?: boolean }) {
  return (
    <div className="readout">
      <div className="k">{label}</div>
      <div className={`v ${large ? "lg" : ""}`}>{value}{unit && <span className="unit">{unit}</span>}</div>
      {detail && <div className="d">{detail}</div>}
    </div>
  );
}

export function Loading({ label }: { label: string }) {
  return <div className="loading" role="status"><span className="bar" />{label}</div>;
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div className="error" role="alert">
      <AlertTriangle size={15} />
      <div style={{ flex: 1 }}>
        <strong>Computation unavailable</strong>
        {message}
      </div>
      {onRetry && <Button size="sm" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

/**
 * One-dimensional interval plot. The scale always includes zero so the reader
 * sees whether the interval excludes the null value.
 */
export function Forest({ estimate, low, high, unit }: { estimate: number; low: number; high: number; unit: string }) {
  const min = Math.min(0, low);
  const max = Math.max(0, high);
  const pad = (max - min) * 0.18 || Math.abs(estimate) || 1;
  const lo = min - pad;
  const hi = max + pad;
  const x = (value: number) => `${((value - lo) / (hi - lo)) * 100}%`;
  return (
    <div aria-label={`Estimate ${formatSig(estimate)} ${unit}, 95% interval ${formatSig(low)} to ${formatSig(high)}`} role="img">
      <div className="forest">
        <div className="axis" />
        <div className="zero" style={{ left: x(0) }} />
        <div className="ci" style={{ left: x(low), width: `calc(${x(high)} - ${x(low)})` }} />
        <div className="pt" style={{ left: x(estimate) }} />
      </div>
      <div className="forest-labels"><span>{formatSig(lo, 2)}</span><span>0 {unit}</span><span>{formatSig(hi, 2)}</span></div>
    </div>
  );
}

export interface PassportProps {
  metricLabel: string;
  value: number | null;
  unit: string;
  metricId: string;
  canonicalId?: string;
  method?: string;
  algorithm?: string;
  protocolId: string;
  sourceId: string;
  snapshotId: string;
  quality: string;
  checksum?: string;
  reproducible: boolean;
  onInspectSource?: () => void;
  onInspectMethod?: () => void;
  onInspectLineage?: () => void;
}

/** Evidence Passport: the provenance contract behind one derived measurement. */
export function EvidencePassport(props: PassportProps) {
  return (
    <div className="frame">
      <div className="frame-head">
        <span className="upper faint">Evidence passport</span>
        <span style={{ marginLeft: "auto" }}><State>{props.quality}</State></span>
      </div>
      <div className="frame-body">
        <div className="readout" style={{ padding: 0, border: 0 }}>
          <div className="k">{props.metricLabel}</div>
          <div className="v lg">{formatSig(props.value, 4)}<span className="unit">{props.unit}</span></div>
        </div>
        <div className="hr" />
        <KV
          rows={[
            ["MetricDefinition", props.metricId, "mono"],
            ["Canonical ID", props.canonicalId, "mono"],
            ["Method", props.method],
            ["Algorithm", props.algorithm, "mono"],
            ["Protocol", props.protocolId, "mono"],
            ["Source trial", props.sourceId, "mono"],
            ["Snapshot", props.snapshotId, "mono"],
            ["Checksum", shortChecksum(props.checksum, 16), "mono"],
            ["Reproducibility", props.reproducible ? "deterministic (fixed seed)" : "not reproducible"],
          ]}
        />
        <div className="insp-actions" style={{ marginTop: 10 }}>
          <Button size="sm" onClick={props.onInspectSource} disabled={!props.onInspectSource}><ScanLine size={12} />Source</Button>
          <Button size="sm" onClick={props.onInspectMethod} disabled={!props.onInspectMethod}><Microscope size={12} />Methodology</Button>
          <Button size="sm" onClick={props.onInspectLineage} disabled={!props.onInspectLineage}><GitBranch size={12} />Lineage</Button>
        </div>
      </div>
    </div>
  );
}
