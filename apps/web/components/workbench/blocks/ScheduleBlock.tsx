"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarClock, Info } from "lucide-react";
import { scienceApi } from "@/lib/api";
import type { WorkbenchBlock } from "@/lib/types";
import { ErrorBox, Loading, Readout, State } from "@/components/ui";
import { BlockFrame } from "../Block";
import { useWorkbench } from "../context";

export function ScheduleBlock({ block, index }: { block: WorkbenchBlock; index: number }) {
  const wb = useWorkbench();
  const schedule = useQuery({
    queryKey: ["program-schedule", wb.studyId],
    queryFn: () => scienceApi.studySchedule(wb.studyId),
    enabled: wb.study.kind === "MONITORING",
  });
  const data = schedule.data;
  const program = wb.study.program;
  const rule = program?.schedule;
  const planned = (data?.planned ?? program?.planned ?? []) as Array<Record<string, unknown>>;
  const observed = (data?.observed_available ?? program?.observed_available ?? []) as Array<string | number>;
  const qualityRules = Array.isArray(rule?.quality_rules) ? (rule.quality_rules as unknown[]).map((item) => String(item)) : [];
  return (
    <BlockFrame
      block={block}
      index={index}
      icon={<CalendarClock size={12} />}
      title="Monitoring schedule"
      sub={rule?.frequency ? `${String(rule.frequency)} · ${planned.length} planned measurements` : `${planned.length} planned measurements`}
      states={["PLANNED", String(data?.status ?? program?.status ?? "SCHEDULE")]}
    >
      {schedule.isLoading && <Loading label="Reading the persisted monitoring schedule" />}
      {schedule.error && <ErrorBox error={schedule.error} onRetry={() => void schedule.refetch()} />}
      <div className="readouts">
        <Readout label="Planned" value={planned.length} detail="future measurements · no reading implied" />
        <Readout label="Available readings" value={observed.length} detail={String(data?.observed_label ?? "deposited observations")} />
        <Readout label="Schedule" value={<span className="readout-small">{rule?.missing_policy ? "MISSING ≠ 0" : "PERSISTED"}</span>} detail="planned and recorded are distinct" />
      </div>
      {planned.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div className="upper faint" style={{ marginBottom: 4 }}>Planned future measurements</div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {planned.map((point, pointIndex) => (
              <span key={String(point.index ?? pointIndex)} className="chip" title="Scheduled measurement; not an observed value">
                {String(point.label ?? point.week ?? `Point ${pointIndex + 1}`)}
              </span>
            ))}
          </div>
        </div>
      )}
      {observed.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div className="upper faint" style={{ marginBottom: 4 }}>Available readings from the bound snapshot</div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {observed.map((point) => <span key={String(point)} className="chip" aria-label={`Available reading ${point}`}>{String(point)}</span>)}
          </div>
          <div className="faint small" style={{ marginTop: 4 }}>{String(data?.observed_note ?? program?.observed_note ?? "")}</div>
        </div>
      )}
      {(qualityRules.length > 0 || rule?.missing_policy) && (
        <div className="note" style={{ marginTop: 10 }}>
          <Info size={12} />
          <span>
            {rule?.missing_policy ? `${String(rule.missing_policy)} ` : ""}
            {qualityRules.join(" ")}
          </span>
        </div>
      )}
      <div className="note warn" style={{ marginTop: 6 }}>
        <Info size={12} />
        <span>{Array.isArray(data?.limitations) ? (data.limitations as unknown[]).map(String).join(" ") : "A planned measurement without a reading is missing, not zero. No readiness, fatigue or injury score is computed."}</span>
      </div>
      <div className="block-toolbar small" style={{ marginTop: 6 }}>
        <State>{wb.study.kind === "MONITORING" ? "MONITORING PROGRAM" : "STUDY"}</State>
        <span className="faint">Schedule version is stored with the study; reopening restores the same plan.</span>
      </div>
    </BlockFrame>
  );
}
