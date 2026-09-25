"use client";

import type { ReactNode } from "react";
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, Trash2 } from "lucide-react";
import type { WorkbenchBlock } from "@/lib/types";
import { BLOCK_META, canMove, dependentsOf, move, removeBlock } from "@/lib/workbench";
import { IconButton, State } from "@/components/ui";
import { useWorkbench } from "./context";

export function BlockFrame({
  block,
  index,
  icon,
  title,
  sub,
  states = [],
  actions,
  children,
  removable = false,
}: {
  block: WorkbenchBlock;
  index: number;
  icon: ReactNode;
  title?: ReactNode;
  sub?: ReactNode;
  states?: (string | { label: string; tone?: string; title?: string })[];
  actions?: ReactNode;
  children: ReactNode;
  removable?: boolean;
}) {
  const wb = useWorkbench();
  const selected = wb.selectedBlockId === block.id;
  const meta = BLOCK_META[block.type];
  const upOk = canMove(wb.blocks, index, -1);
  const downOk = canMove(wb.blocks, index, 1);
  const dependents = dependentsOf(wb.blocks, block.id);
  const toggle = () => wb.setBlocks((blocks) => blocks.map((item) => (item.id === block.id ? { ...item, collapsed: !item.collapsed } : item)));
  const remove = () => {
    const next = removeBlock(wb.blocks, block.id);
    if (!next) {
      wb.notify(`${block.id} cannot be removed: ${dependents.map((item) => item.id).join(", ")} depend on it`);
      return;
    }
    wb.setBlocks(() => next);
    wb.selectBlock(null);
  };
  return (
    <section
      id={`block-${block.id}`}
      className={`block ${selected ? "is-selected" : ""} ${block.collapsed ? "is-collapsed" : ""}`}
      aria-label={`${meta.label} block: ${block.title}`}
      onMouseDown={(event) => {
        const target = event.target as HTMLElement;
        if (target.closest("button, input, select, textarea, a, canvas, [role='button']")) {
          if (!selected) wb.selectBlock(block.id, { inspect: false });
          return;
        }
        if (!selected) wb.selectBlock(block.id);
      }}
      onFocusCapture={() => { if (!selected) wb.selectBlock(block.id, { inspect: false }); }}
    >
      <header className="block-head">
        <button type="button" className="block-type" onClick={() => wb.selectBlock(block.id)} aria-label={`Inspect ${meta.label} block`} title={meta.description}>
          {icon}
          {meta.label}
        </button>
        <IconButton label={block.collapsed ? "Expand block" : "Collapse block"} onClick={toggle}>{block.collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}</IconButton>
        <div style={{ minWidth: 0, display: "flex", alignItems: "baseline", gap: 10 }}>
          <span className="block-title">{title ?? block.title}</span>
          {sub && <span className="block-title-sub">{sub}</span>}
        </div>
        <div className="block-states">
          {states.map((state) => (typeof state === "string" ? <State key={state}>{state}</State> : <State key={state.label} tone={state.tone} title={state.title}>{state.label}</State>))}
        </div>
        <div className="block-actions">
          {actions}
          <IconButton label="Move block up" disabled={!upOk} onClick={() => wb.setBlocks((blocks) => move(blocks, index, -1))}><ArrowUp size={13} /></IconButton>
          <IconButton label="Move block down" disabled={!downOk} onClick={() => wb.setBlocks((blocks) => move(blocks, index, 1))}><ArrowDown size={13} /></IconButton>
          {removable && <IconButton label={dependents.length ? `Remove (blocked: ${dependents.map((item) => item.id).join(", ")} depend on this block)` : "Remove block"} disabled={dependents.length > 0} onClick={remove}><Trash2 size={13} /></IconButton>}
        </div>
      </header>
      {!block.collapsed && <div className="block-body">{children}</div>}
    </section>
  );
}
