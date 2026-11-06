"use client";

import type { ReactNode } from "react";
import { AlertTriangle, X } from "lucide-react";

export function PosChip({ tone = "neutral", children, plain = false }: { tone?: "ok" | "warn" | "bad" | "info" | "neutral"; children: ReactNode; plain?: boolean }) {
  return <span className={`pos-chip ${tone} ${plain ? "plain" : ""}`}>{children}</span>;
}

export function PosState({ children, tone = "neutral" }: { children: string; tone?: "ok" | "warn" | "bad" | "info" | "neutral" }) {
  return <PosChip tone={tone}>{children}</PosChip>;
}

export function toneForStatus(value: string | null | undefined): "ok" | "warn" | "bad" | "info" | "neutral" {
  switch (value) {
    case "VALID":
    case "COMPLETE":
    case "COMPLETED":
    case "PUBLISHED":
    case "FROZEN":
    case "ACTIVE":
    case "CURRENT":
      return "ok";
    case "WARNING":
    case "DRAFT":
    case "SCHEDULED":
    case "PARTIAL":
    case "REFERENCE":
    case "PLANNED":
      return "warn";
    case "EXCLUDED":
    case "UNAVAILABLE":
    case "FAILED":
    case "NO_DATA":
      return "bad";
    case "SYNTHETIC":
    case "SEGMENT_ONLY":
      return "info";
    default:
      return "neutral";
  }
}

export function PosReadout({ label, value, unit, detail }: { label: string; value: ReactNode; unit?: string; detail?: ReactNode }) {
  return (
    <div className="pos-stat">
      <div className="k">{label}</div>
      <div className="v">{value}{unit ? <span className="u">{unit}</span> : null}</div>
      {detail ? <div className="s">{detail}</div> : null}
    </div>
  );
}

export function PosLoading({ label }: { label: string }) {
  return <div className="pos-loading" role="status"><span className="bar" />{label}</div>;
}

export function PosError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div className="pos-error" role="alert">
      <strong>Computation unavailable</strong>
      {message}
      {onRetry ? <button type="button" className="pos-btn small" style={{ marginTop: 7 }} onClick={onRetry}>Retry</button> : null}
    </div>
  );
}

export function PosEmpty({ title, children, info = false }: { title: string; children: ReactNode; info?: boolean }) {
  return <div className={`pos-empty ${info ? "info" : ""}`}><b>{title}</b>{children}</div>;
}

export function Drawer({ title, subtitle, onClose, children, actions }: { title: string; subtitle?: ReactNode; onClose: () => void; children: ReactNode; actions?: ReactNode }) {
  return (
    <div className="pos-drawer-backdrop" onMouseDown={onClose}>
      <div className="pos-drawer" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <div className="pos-drawer-head">
          <h2>{title}</h2>
          {subtitle ? <span className="pos-note">{subtitle}</span> : null}
          <div className="right">{actions}<button type="button" className="pos-btn small ghost" onClick={onClose} aria-label="Close"><X size={12} /></button></div>
        </div>
        <div className="pos-drawer-body">{children}</div>
      </div>
    </div>
  );
}

export function Toast({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="pos-toast" role="status" aria-live="polite">{message}</div>;
}

export function ErrorInline({ message }: { message: string }) {
  return <div className="pos-error"><AlertTriangle size={12} /> {message}</div>;
}
