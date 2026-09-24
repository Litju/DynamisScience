"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { ArrowUpRight, Check, CircleAlert, Copy, ExternalLink, FlaskConical, LockKeyhole, RefreshCw, ShieldCheck } from "lucide-react";
import type { Evidence, QualityState } from "@/lib/types";

export function StatusBadge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "good" | "warn" | "bad" | "cyan" | "purple" }) {
  return <span className={`status-badge status-${tone}`}><span className="status-dot" />{children}</span>;
}

export function Panel({ children, className = "", title, eyebrow, action }: { children: ReactNode; className?: string; title?: string; eyebrow?: string; action?: ReactNode }) {
  return <section className={`panel ${className}`}>
    {(title || eyebrow || action) && <div className="panel-heading">
      <div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}{title && <h2>{title}</h2>}</div>
      {action}
    </div>}
    {children}
  </section>;
}

export function SectionHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return <div className="section-header">
    <div><div className="eyebrow">{eyebrow ?? "Scientific workspace"}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>
    {actions && <div className="header-actions">{actions}</div>}
  </div>;
}

export function Button({ children, variant = "secondary", size = "md", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger"; size?: "sm" | "md" }) {
  return <button className={`button button-${variant} button-${size} ${className}`} {...props}>{children}</button>;
}

export function IconButton({ label, children, onClick, active = false }: { label: string; children: ReactNode; onClick?: () => void; active?: boolean }) {
  return <button className={`icon-button ${active ? "is-active" : ""}`} aria-label={label} title={label} onClick={onClick}>{children}</button>;
}

export function MetricTile({ label, value, unit, detail, state = "VALID", onClick }: { label: string; value: string; unit?: string; detail?: string; state?: QualityState; onClick?: () => void }) {
  return <button className={`metric-tile metric-${state.toLowerCase()}`} onClick={onClick}>
    <div className="metric-label"><span>{label}</span><span className="metric-state">{state}</span></div>
    <div className="metric-value">{value}<small>{unit}</small></div>
    {detail && <div className="metric-detail">{detail}</div>}
  </button>;
}

export function KeyValue({ label, value, mono = false, children }: { label: string; value?: ReactNode; mono?: boolean; children?: ReactNode }) {
  return <div className="key-value"><span>{label}</span><strong className={mono ? "mono" : ""}>{children ?? value ?? "—"}</strong></div>;
}

export function ProgressBar({ value, tone = "cyan" }: { value: number; tone?: "cyan" | "amber" | "bad" }) {
  return <div className="progress-track"><span className={`progress-fill progress-${tone}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div>;
}

export function EmptyState({ title, detail, action }: { title: string; detail: string; action?: ReactNode }) {
  return <div className="empty-state"><FlaskConical size={20} /><strong>{title}</strong><span>{detail}</span>{action}</div>;
}

export function LoadingState({ label = "Loading local analytical store" }: { label?: string }) {
  return <div className="loading-state"><RefreshCw size={16} className="spin" /><span>{label}</span></div>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="error-state"><CircleAlert size={18} /><div><strong>Local service unavailable</strong><span>{message}</span></div>{onRetry && <Button size="sm" onClick={onRetry}>Retry</Button>}</div>;
}

export function EvidencePassport({ evidence, onNavigate }: { evidence: Evidence; onNavigate?: (view: string, id?: string) => void }) {
  return <div className="passport">
    <div className="passport-top"><div><div className="eyebrow">Evidence passport</div><h3>{evidence.title}</h3></div><StatusBadge tone={evidence.quality === "VALID" ? "good" : "warn"}>{evidence.quality}</StatusBadge></div>
    <div className="passport-value"><span>{evidence.value === null ? "—" : evidence.value.toFixed(3)}</span><small>{evidence.unit}</small><em>{evidence.uncertainty_label ?? "estimate"}{evidence.uncertainty !== null ? ` · ${evidence.uncertainty.toFixed(3)} ${evidence.unit}` : ""}</em></div>
    <div className="passport-grid"><KeyValue label="Method" value={String(evidence.provenance.algorithm ?? evidence.metric_id)} /><KeyValue label="Algorithm" value={`${String(evidence.provenance.algorithm_version ?? "1.0.0")}`} mono /><KeyValue label="Protocol" value={evidence.protocol_id} mono /><KeyValue label="Population" value={evidence.population} /><KeyValue label="Sample size" value={String(evidence.sample_size)} /><KeyValue label="Snapshot" value={evidence.dataset_snapshot_id} mono /></div>
    <div className="passport-provenance"><ShieldCheck size={14} /><span>Input provenance complete</span><span className="provenance-checksum">{String(evidence.provenance.snapshot_checksum ?? "checksum recorded").slice(0, 12)}…</span></div>
    <div className="passport-actions"><Button size="sm" onClick={() => onNavigate?.("analyses", evidence.analysis_run_id)}><ExternalLink size={13} /> Open analysis</Button><Button size="sm" variant="ghost" onClick={() => onNavigate?.("lineage", evidence.id)}>View lineage <ArrowUpRight size={13} /></Button></div>
  </div>;
}

export function CodeBlock({ value, label = "Machine-readable specification" }: { value: unknown; label?: string }) {
  return <div className="code-block"><div className="code-label"><span>{label}</span><Copy size={13} /></div><pre>{JSON.stringify(value, null, 2)}</pre></div>;
}

export function LockedPlan({ children }: { children: ReactNode }) {
  return <div className="locked-plan"><LockKeyhole size={15} /><div><strong>Frozen analysis plan</strong><span>Configuration is versioned and execution is append-only.</span></div>{children}</div>;
}

export function CheckLine({ children, state = "valid" }: { children: ReactNode; state?: "valid" | "warning" | "muted" }) {
  return <div className={`check-line check-${state}`}>{state === "valid" ? <Check size={13} /> : <CircleAlert size={13} />}<span>{children}</span></div>;
}
