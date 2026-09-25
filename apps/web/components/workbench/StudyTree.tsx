"use client";

import type { ReactNode } from "react";
import { BookOpen, CalendarRange, CircleHelp, Database, FileText, FlaskConical, GitCommitVertical, Hexagon, Lock, MapPin, ScrollText, Split, Users } from "lucide-react";
import { useWorkbench, type InspectTarget } from "./context";
import { useEvidenceList, useReport } from "./data";
import { BLOCK_META, updateState } from "@/lib/workbench";
import { State } from "@/components/ui";

function Item({ icon, label, tag, depth = 0, current = false, onClick, title }: { icon: ReactNode; label: string; tag?: ReactNode; depth?: number; current?: boolean; onClick: () => void; title?: string }) {
  return (
    <button type="button" className="tree-item" style={{ ["--depth" as string]: depth }} aria-current={current ? "true" : undefined} onClick={onClick} title={title ?? label}>
      {icon}
      <span className="label">{label}</span>
      {tag && <span className="tag">{tag}</span>}
    </button>
  );
}

function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="tree-group" role="group" aria-label={label}>
      <div className="tree-group-label">{label}</div>
      {children}
    </div>
  );
}

const same = (a: InspectTarget | null, b: InspectTarget) => JSON.stringify(a) === JSON.stringify(b);

export function StudyTree() {
  const wb = useWorkbench();
  const evidence = useEvidenceList();
  const report = useReport();
  const { study } = wb;
  const questionBlock = wb.blocks.find((block) => block.type === "question");
  const datasetBlock = wb.blocks.find((block) => block.type === "dataset");
  const cohortBlock = wb.blocks.find((block) => block.type === "cohort");
  const exploreBlock = wb.blocks.find((block) => block.type === "explore");

  const openDesign = (section: "hypotheses" | "arms" | "timeline" | "plan") => {
    wb.setMode("investigation");
    if (questionBlock) wb.selectBlock(questionBlock.id, { scroll: true, inspect: false });
    wb.inspect({ kind: "design", section });
  };
  const focusBlock = (id: string | undefined) => {
    if (!id) return;
    wb.setMode("investigation");
    wb.selectBlock(id, { scroll: true });
  };
  const focusPopulation = (population: "ALL" | "INTERVENTION" | "COMPARISON") => {
    if (exploreBlock) wb.setBlocks((blocks) => updateState(blocks, exploreBlock.id, { population }));
    focusBlock(cohortBlock?.id);
  };
  const citedIds = new Set(report.data?.evidence_ids ?? []);

  return (
    <aside className="tree" aria-label="Study tree">
      <div className="tree-head">
        <span className="upper">Study</span>
        <span className="mono small">{study.study.id}</span>
      </div>
      <div className="tree-scroll">
        <Group label="Question">
          <Item icon={<CircleHelp size={13} />} label="Research question" tag={study.question.id} current={wb.selectedBlockId === questionBlock?.id && wb.mode === "investigation" && wb.inspector?.kind === "block"} onClick={() => focusBlock(questionBlock?.id)} />
        </Group>
        <Group label="Study design">
          <Item icon={<BookOpen size={13} />} label="Hypotheses" tag={String(study.hypotheses.length)} depth={0} current={same(wb.inspector, { kind: "design", section: "hypotheses" })} onClick={() => openDesign("hypotheses")} />
          <Item icon={<Split size={13} />} label="Arms" tag={`${study.arm_counts.INTERVENTION}/${study.arm_counts.COMPARISON}`} current={same(wb.inspector, { kind: "design", section: "arms" })} onClick={() => openDesign("arms")} />
          <Item icon={<CalendarRange size={13} />} label="Timeline" tag={`w${study.study.start_week}–${study.study.end_week}`} current={same(wb.inspector, { kind: "design", section: "timeline" })} onClick={() => openDesign("timeline")} />
          <Item icon={<Lock size={13} />} label="Frozen analysis plan" tag={study.plan.status} current={same(wb.inspector, { kind: "design", section: "plan" })} onClick={() => openDesign("plan")} />
        </Group>
        <Group label="Data">
          <Item icon={<Database size={13} />} label={study.snapshot.id} tag="snapshot" current={wb.selectedBlockId === datasetBlock?.id} onClick={() => focusBlock(datasetBlock?.id)} />
          {study.protocols.map((protocol) => (
            <Item key={protocol.id} icon={<ScrollText size={13} />} label={protocol.name} tag={protocol.id.replace("PROT-", "")} depth={1} current={same(wb.inspector, { kind: "protocol", id: protocol.id })} onClick={() => wb.inspect({ kind: "protocol", id: protocol.id })} />
          ))}
          <Item icon={<MapPin size={13} />} label="Match segment · 4 events" tag="10 Hz" depth={1} onClick={() => wb.openViewer({ kind: "match" })} title="Open the synchronized field + pose viewer" />
        </Group>
        <Group label="Cohorts">
          <Item icon={<Users size={13} />} label={wb.excludedSubjectIds.length ? "All participants (draft)" : "All participants"} tag={String(28 - wb.excludedSubjectIds.length)} onClick={() => focusPopulation("ALL")} />
          <Item icon={<Users size={13} />} label="Intervention" tag={String(study.arm_counts.INTERVENTION)} depth={1} onClick={() => focusPopulation("INTERVENTION")} />
          <Item icon={<Users size={13} />} label="Comparison" tag={String(study.arm_counts.COMPARISON)} depth={1} onClick={() => focusPopulation("COMPARISON")} />
        </Group>
        <Group label="Investigations">
          <Item icon={<FlaskConical size={13} />} label="Primary Intervention Analysis" tag={wb.investigationId} onClick={() => { wb.setMode("investigation"); document.querySelector(".bench")?.scrollTo({ top: 0, behavior: "smooth" }); }} />
          {wb.blocks.map((block, index) => (
            <Item key={block.id} icon={<GitCommitVertical size={13} />} label={`${String(index + 1).padStart(2, "0")} ${BLOCK_META[block.type].label}`} tag={block.type === "analysis" && block.state.run_id ? String(block.state.run_id) : undefined} depth={1} current={wb.selectedBlockId === block.id && wb.mode === "investigation"} onClick={() => focusBlock(block.id)} title={block.title} />
          ))}
        </Group>
        <Group label="Evidence">
          {(evidence.data ?? []).map((item) => (
            <Item
              key={item.id}
              icon={<Hexagon size={13} />}
              label={item.title}
              tag={`${item.id.replace("EVID-", "E")}${citedIds.has(item.id) ? " ·R" : ""}`}
              current={same(wb.inspector, { kind: "evidence", id: item.id })}
              onClick={() => wb.inspect({ kind: "evidence", id: item.id })}
              title={`${item.id} · ${item.evidence_class ?? item.quality}${citedIds.has(item.id) ? " · cited in report" : ""}`}
            />
          ))}
        </Group>
        <Group label="Report">
          <Item icon={<FileText size={13} />} label={report.data?.title ?? "Report"} tag={report.data?.status} current={wb.mode === "report"} onClick={() => wb.setMode("report")} />
        </Group>
      </div>
      <div className="tree-foot">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>Plan</span>
          <State plain>{study.plan.status}</State>
        </div>
      </div>
    </aside>
  );
}
