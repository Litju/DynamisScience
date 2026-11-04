"use client";

import { useEffect, useRef, useState } from "react";
import { Plus } from "lucide-react";
import type { BlockType, WorkbenchBlock } from "@/lib/types";
import { BLOCK_META, blockIndexLabel, createBlock, dependencyOf, insertAfter } from "@/lib/workbench";
import { Button } from "@/components/ui";
import { useWorkbench } from "./context";
import { CohortBlock, DatasetBlock, QuestionBlock } from "./blocks/ContextBlocks";
import { ExploreBlock } from "./blocks/ExploreBlock";
import { AnalysisBlock, DiagnosticsBlock } from "./blocks/AnalysisBlocks";
import { EvidenceBlock, FigureBlock, InterpretationBlock, ReportSectionBlock } from "./blocks/EvidenceBlocks";
import { ForceTrialBlock, MatchEventBlock, ModelBlock, TableBlock } from "./blocks/ExtraBlocks";

function BlockBody({ block, index }: { block: WorkbenchBlock; index: number }) {
  switch (block.type) {
    case "question":
      return <QuestionBlock block={block} index={index} />;
    case "dataset":
      return <DatasetBlock block={block} index={index} />;
    case "cohort":
      return <CohortBlock block={block} index={index} />;
    case "explore":
      return <ExploreBlock block={block} index={index} />;
    case "analysis":
      return <AnalysisBlock block={block} index={index} />;
    case "diagnostics":
      return <DiagnosticsBlock block={block} index={index} />;
    case "evidence":
      return <EvidenceBlock block={block} index={index} />;
    case "figure":
      return <FigureBlock block={block} index={index} />;
    case "interpretation":
      return <InterpretationBlock block={block} index={index} />;
    case "report_section":
      return <ReportSectionBlock block={block} index={index} />;
    case "model":
      return <ModelBlock block={block} index={index} />;
    case "match_event":
      return <MatchEventBlock block={block} index={index} />;
    case "force_trial":
      return <ForceTrialBlock block={block} index={index} />;
    case "table":
      return <TableBlock block={block} index={index} />;
    default:
      return null;
  }
}

const ADDABLE: BlockType[] = (Object.keys(BLOCK_META) as BlockType[]).filter((type) => BLOCK_META[type].addable);

export function Workbench() {
  const wb = useWorkbench();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    menuRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setMenuOpen(false);
    const onDown = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onDown);
    };
  }, [menuOpen]);

  const add = (type: BlockType) => {
    const block = createBlock(wb.blocks, type);
    const anchor = wb.selectedBlockId && wb.blocks.some((item) => item.id === wb.selectedBlockId) && type !== "model" ? wb.selectedBlockId : null;
    wb.setBlocks((blocks) => insertAfter(blocks, block, anchor));
    setMenuOpen(false);
    wb.selectBlock(block.id, { scroll: true });
  };

  const byId = new Map(wb.blocks.map((block) => [block.id, block]));

  return (
    <div className="bench" id="workbench">
      <div className="bench-inner">
        <div className="bench-head">
          <h2>{wb.study.real_data ? "Real-data scientific investigation" : "Primary Intervention Analysis"}</h2>
          <span className="faint">{wb.investigationId} · v{wb.version} · {wb.blocks.length} blocks</span>
          <span className="save" role="status">
            {wb.saveState === "saving" && "saving investigation…"}
            {wb.saveState === "saved" && "investigation saved"}
            {wb.saveState === "error" && <span style={{ color: "var(--excluded)" }}>not saved: {wb.saveError}</span>}
          </span>
        </div>
        {wb.blocks.map((block, index) => {
          const dependencies = dependencyOf(block).map((id) => byId.get(id)).filter((item): item is WorkbenchBlock => Boolean(item));
          return (
            <div key={block.id} className={`block-row ${wb.selectedBlockId === block.id ? "is-selected" : ""}`}>
              <div className="gutter" aria-hidden="true">
                <span className="idx">{blockIndexLabel(index)}</span>
                <span className="rail" />
              </div>
              <div style={{ minWidth: 0 }}>
                {dependencies.length > 0 && (
                  <div className="link-note">
                    uses {dependencies.map((item) => `${BLOCK_META[item.type].label.toLowerCase()} ${blockIndexLabel(wb.blocks.indexOf(item))}`).join(" · ")}
                  </div>
                )}
                <BlockBody block={block} index={index} />
              </div>
            </div>
          );
        })}
        <div className="add-row">
          <Button onClick={() => setMenuOpen((open) => !open)} aria-expanded={menuOpen} aria-haspopup="menu"><Plus size={13} />Add block</Button>
          <span className="faint small">{wb.selectedBlockId ? `inserts after ${wb.selectedBlockId}` : "appends to the investigation"} · Model blocks append at the end</span>
          {menuOpen && (
            <div className="add-menu" role="menu" ref={menuRef}>
              {ADDABLE.map((type) => (
                <button key={type} type="button" role="menuitem" onClick={() => add(type)}>
                  <Plus size={13} style={{ marginTop: 2 }} />
                  <strong>{BLOCK_META[type].label}</strong>
                  <small>{BLOCK_META[type].description}</small>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
