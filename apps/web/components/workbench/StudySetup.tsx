"use client";

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Archive, GitFork, Lock, RefreshCw, Save, Settings2, Snowflake, Trash2, Unlock } from "lucide-react";
import { scienceApi, ScienceError } from "@/lib/api";
import type { AnalysisPlan, ResearchEligibility } from "@/lib/types";
import { Button, ErrorBox, KV, State } from "@/components/ui";
import { useWorkbench } from "./context";
import { useInvalidateScience } from "./data";

type Section = "definition" | "cohorts" | "plan" | "schedule" | "history";

const input = "input";
const select = "select";

function errorText(error: unknown): string | null {
  if (!error) return null;
  return error instanceof ScienceError ? error.detail || error.message : String(error);
}

function splitList(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

export function StudySetup() {
  const wb = useWorkbench();
  const study = wb.study;
  const client = useQueryClient();
  const invalidate = useInvalidateScience();
  const [section, setSection] = useState<Section>("definition");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const plan = study.current_plan;
  const cohort = study.current_cohort;
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["study", wb.studyId] });
    invalidate();
  };
  const act = (fn: () => Promise<unknown>, message: string): Promise<void> => {
    setError(null);
    return fn()
      .then(async () => {
        await client.refetchQueries({ queryKey: ["study", wb.studyId] });
        refresh();
        setNotice(message);
      })
      .catch((err) => setError(errorText(err)));
  };

  return (
    <div className="bench">
      <div className="bench-inner">
        <div className="bench-head">
          <h2>{study.kind === "MONITORING" ? "Monitoring program setup" : "Study setup"}</h2>
          <span className="faint">{study.study.id} · v{study.entity_version} · <State>{study.study.state}</State></span>
          <span className="save" role="status">{notice}</span>
        </div>
        <div className="block-toolbar" role="tablist" aria-label="Study setup sections">
          {(["definition", "cohorts", "plan", ...(study.kind === "MONITORING" ? ["schedule"] : []), "history"] as Section[]).map((item) => (
            <button key={item} type="button" className="chip" aria-pressed={section === item} onClick={() => setSection(item)}>{item}</button>
          ))}
          <span className="grow" />
          <span className="faint small">All edits are persisted; frozen objects never mutate.</span>
        </div>
        {error && <ErrorBox error={error} onRetry={() => setError(null)} />}
        {section === "definition" && <Definition studyId={wb.studyId} study={study} onAct={act} />}
        {section === "cohorts" && <Cohorts studyId={wb.studyId} cohort={cohort ?? study.cohort} cohorts={study.cohorts ?? []} onAct={act} />}
        {section === "plan" && <Plans studyId={wb.studyId} plan={plan} plans={study.plans ?? []} eligibility={study.eligibility ?? []} methods={study.methods ?? []} metrics={study.metrics ?? []} onAct={act} />}
        {section === "schedule" && <Schedule studyId={wb.studyId} schedule={(study.current_cohort as unknown as { schedule?: Record<string, unknown> })?.schedule ?? (study.program?.schedule ?? {})} onAct={act} />}
        {section === "history" && <History studyId={wb.studyId} />}
        <StateActions studyId={wb.studyId} study={study} onAct={act} />
      </div>
    </div>
  );
}

function Definition({ studyId, study, onAct }: { studyId: string; study: ReturnType<typeof useWorkbench>["study"]; onAct: (fn: () => Promise<unknown>, message: string) => void }) {
  const [title, setTitle] = useState(study.study.title);
  const [question, setQuestion] = useState(study.question.statement);
  const [population, setPopulation] = useState(study.question.population);
  const [design, setDesign] = useState(String((study.study as unknown as { design_code?: string }).design_code ?? study.designs?.[0]?.id ?? "OBSERVATIONAL_LONGITUDINAL"));
  const [hypothesis, setHypothesis] = useState(study.hypotheses[0]?.statement ?? "");
  useEffect(() => {
    setTitle(study.study.title);
    setQuestion(study.question.statement);
    setPopulation(study.question.population);
  }, [study.study.title, study.question.statement, study.question.population]);
  const save = useMutation({
    mutationFn: () => scienceApi.updateStudy(studyId, {
      title,
      research_question: question,
      population,
      design,
      hypotheses: hypothesis.trim() ? [{ statement: hypothesis.trim(), status: "PRIMARY", direction: "change" }] : undefined,
      base_version: study.entity_version,
    }),
  });
  return (
    <div className="frame">
      <div className="frame-body" style={{ display: "grid", gap: 10, padding: 12 }}>
        <div className="split">
          <label className="field" style={{ display: "grid" }}><span>Title</span><input className={input} value={title} onChange={(event) => setTitle(event.target.value)} /></label>
          <label className="field" style={{ display: "grid" }}><span>Design</span>
            <select className={select} value={design} onChange={(event) => setDesign(event.target.value)}>
              {(study.designs ?? []).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
          </label>
        </div>
        <label className="field" style={{ display: "grid" }}><span>Research question</span><textarea className={input} rows={3} value={question} onChange={(event) => setQuestion(event.target.value)} /></label>
        <label className="field" style={{ display: "grid" }}><span>Population</span><input className={input} value={population} onChange={(event) => setPopulation(event.target.value)} /></label>
        <label className="field" style={{ display: "grid" }}><span>Primary hypothesis</span><textarea className={input} rows={2} value={hypothesis} onChange={(event) => setHypothesis(event.target.value)} /></label>
        <div className="block-toolbar">
          <Button variant="primary" onClick={() => onAct(() => save.mutateAsync(), "Study definition saved as a new version.")} disabled={save.isPending}><Save size={12} />Save definition</Button>
          <span className="faint small">The dataset binding, snapshot checksum and historical versions are immutable.</span>
        </div>
        <KV rows={[["Study", study.study.id, "mono"], ["Project", study.project?.id ?? "—", "mono"], ["Snapshot", study.snapshot.id, "mono"], ["Design", study.study.design], ["Data class", study.real_data ? "REAL DATA" : "SYNTHETIC"], ["Version", String(study.entity_version)]]} />
      </div>
    </div>
  );
}

function Cohorts({ studyId, cohort, cohorts, onAct }: { studyId: string; cohort: ReturnType<typeof useWorkbench>["study"]["cohort"]; cohorts: NonNullable<ReturnType<typeof useWorkbench>["study"]["cohorts"]>; onAct: (fn: () => Promise<unknown>, message: string) => void }) {
  const definitions = Array.isArray(cohorts) ? cohorts : [];
  const currentCohort = cohort ?? ({ id: "", status: "DRAFT", subject_ids: [], snapshot_id: "" } as unknown as ReturnType<typeof useWorkbench>["study"]["cohort"]);
  const current = definitions.find((item) => item.id === currentCohort.id);
  const [name, setName] = useState("Eligible participants");
  const [excluded, setExcluded] = useState("");
  const [minimum, setMinimum] = useState(1);
  const [activity, setActivity] = useState("");
  const [freeze, setFreeze] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => scienceApi.createCohort(studyId, {
      name,
      description: "Authored in the study setup panel.",
      exclude_subject_ids: excluded.split(",").map((item) => item.trim()).filter(Boolean),
      min_metric_observations: minimum,
      activity: activity || undefined,
      freeze,
    }),
  });
  return (
    <div className="frame">
      <div className="frame-body" style={{ display: "grid", gap: 10, padding: 12 }}>
        <div className="section-title" style={{ margin: 0 }}><h2>Cohort definitions</h2><span>{definitions.length} versioned definition{definitions.length === 1 ? "" : "s"}</span></div>
        {definitions.map((item) => (
          <div key={item.id} className="study-row" style={{ gridTemplateColumns: "1.2fr 2fr auto" }}>
            <div><div className="mono faint">{item.id}</div><State>{item.status}</State></div>
            <div><strong>{item.name}</strong><div className="q">{item.description || "Snapshot-bound declarative cohort."}</div><div className="faint small">n={item.subject_ids?.length ?? 0} · snapshot {item.snapshot_id}</div></div>
            <div className="block-toolbar" style={{ margin: 0 }}>
              {item.status !== "FROZEN" && <Button size="sm" disabled={busyId === item.id} onClick={async () => { setBusyId(item.id); await onAct(() => scienceApi.freezeCohort(item.id), "Cohort frozen; historical runs keep their original cohort identity."); setBusyId(null); }}><Snowflake size={12} />Freeze cohort</Button>}
              <Button size="sm" disabled={busyId === item.id} onClick={async () => { setBusyId(item.id); await onAct(() => scienceApi.forkCohort(item.id), "Cohort forked as a new draft; the original remains immutable."); setBusyId(null); }}><GitFork size={12} />Fork cohort</Button>
            </div>
          </div>
        ))}
        <div className="block-toolbar"><span className="faint small">Current cohort <span className="mono">{currentCohort.id}</span> · {current?.status ?? currentCohort.status} · n={currentCohort.subject_ids?.length ?? 0}</span></div>
        <div className="section-title" style={{ marginTop: 6 }}><h2>New cohort definition</h2></div>
        <div className="split">
          <label className="field" style={{ display: "grid" }}><span>Name</span><input className={input} value={name} onChange={(event) => setName(event.target.value)} /></label>
          <label className="field" style={{ display: "grid" }}><span>Minimum valid observations / participant</span><input className={input} type="number" min={0} value={minimum} onChange={(event) => setMinimum(Number(event.target.value))} /></label>
        </div>
        <label className="field" style={{ display: "grid" }}><span>Exclude participant IDs (comma separated)</span><input className={input} value={excluded} onChange={(event) => setExcluded(event.target.value)} placeholder="e.g. MEN-04, MEN-14" /></label>
        <div className="split">
          <label className="field" style={{ display: "grid" }}><span>Activity filter (repeated-trial data only)</span><input className={input} value={activity} onChange={(event) => setActivity(event.target.value)} placeholder="e.g. Walking" /></label>
          <label className="field" style={{ display: "flex", alignItems: "center", gap: 6 }}><input type="checkbox" checked={freeze} onChange={(event) => setFreeze(event.target.checked)} /><span>Freeze immediately</span></label>
        </div>
        <div className="block-toolbar">
          <Button variant="primary" onClick={() => onAct(() => create.mutateAsync(), "Cohort created and resolved against the snapshot.")} disabled={create.isPending}><Save size={12} />Create cohort</Button>
          <span className="faint small">Changing rules creates a new cohort; historical runs retain the original cohort identity.</span>
        </div>
        <div className="note"><Lock size={12} /><span>Frozen cohorts are declarative, snapshot-bound and reusable. Exclusion is explicit; missing data is never imputed.</span></div>
      </div>
    </div>
  );
}

function Plans({ studyId, plan, plans, eligibility, methods, metrics, onAct }: { studyId: string; plan: ReturnType<typeof useWorkbench>["study"]["current_plan"]; plans: AnalysisPlan[]; eligibility: ResearchEligibility[]; methods: NonNullable<ReturnType<typeof useWorkbench>["study"]["methods"]>; metrics: NonNullable<ReturnType<typeof useWorkbench>["study"]["metrics"]>; onAct: (fn: () => Promise<unknown>, message: string) => void }) {
  const [methodId, setMethodId] = useState(plan?.method_id ?? methods[0]?.id ?? "METH-U-DESC");
  const [outcomeId, setOutcomeId] = useState(plan?.outcome_metric_id ?? metrics[0]?.id ?? "");
  const [reference, setReference] = useState(Number((plan?.parameters as Record<string, unknown>)?.reference_occasion ?? 1));
  const [contrast, setContrast] = useState(Number((plan?.parameters as Record<string, unknown>)?.contrast_occasion ?? 4));
  const [activity, setActivity] = useState(String((plan?.parameters as Record<string, unknown>)?.activity ?? "Walking"));
  const [estimand, setEstimand] = useState(plan?.primary_estimand ?? "");
  const [missing, setMissing] = useState(plan?.missing_data ?? "Complete-case at the outcome; no imputation.");
  const [covariates, setCovariates] = useState((plan?.covariates ?? []).join(", "));
  const [fixedEffects, setFixedEffects] = useState((plan?.fixed_effects ?? []).join(", "));
  const [randomEffects, setRandomEffects] = useState((plan?.random_effects ?? []).join(", "));
  const [timeCoding, setTimeCoding] = useState(plan?.time_coding ?? "");
  const [contrasts, setContrasts] = useState((plan?.contrasts ?? []).join(", "));
  useEffect(() => {
    if (!plan) return;
    setMethodId(plan.method_id);
    setOutcomeId(plan.outcome_metric_id);
    setEstimand(plan.primary_estimand);
    setMissing(plan.missing_data);
    setCovariates((plan.covariates ?? []).join(", "));
    setFixedEffects((plan.fixed_effects ?? []).join(", "));
    setRandomEffects((plan.random_effects ?? []).join(", "));
    setTimeCoding(plan.time_coding);
    setContrasts((plan.contrasts ?? []).join(", "));
    const parameters = plan.parameters as Record<string, unknown>;
    setReference(Number(parameters.reference_occasion ?? 1));
    setContrast(Number(parameters.contrast_occasion ?? 4));
    setActivity(String(parameters.activity ?? "Walking"));
  }, [plan]);
  const frozen = plan?.status === "FROZEN";
  const method = methods.find((item) => item.id === methodId);
  const parameters = methodId === "METH-REAL-TREND"
    ? { reference_occasion: reference, contrast_occasion: contrast, alpha: 0.05 }
    : methodId === "METH-REAL-RELIABILITY"
      ? { activity, max_trials: 8 }
      : {};
  const save = useMutation({
    mutationFn: () => plan
      ? scienceApi.updatePlan(plan.id, { method_id: methodId, outcome_metric_id: outcomeId, parameters, primary_estimand: estimand, missing_data: missing, covariates: splitList(covariates), fixed_effects: splitList(fixedEffects), random_effects: splitList(randomEffects), time_coding: timeCoding, contrasts: splitList(contrasts), base_version: plan.version })
      : scienceApi.createPlan(studyId, { method_id: methodId, outcome_metric_id: outcomeId, parameters, primary_estimand: estimand, missing_data: missing, covariates: splitList(covariates), fixed_effects: splitList(fixedEffects), random_effects: splitList(randomEffects), time_coding: timeCoding, contrasts: splitList(contrasts), name: `${method?.name ?? methodId} plan` }),
  });
  return (
    <div className="frame">
      <div className="frame-body" style={{ display: "grid", gap: 10, padding: 12 }}>
        <div className="section-title" style={{ margin: 0 }}><h2>Analysis plan</h2><span>{plan ? `${plan.id} · ${plan.status} · v${plan.version}` : "No plan"}</span></div>
        {plan && (
          <KV rows={[
            ["Plan", plan.id, "mono"],
            ["Status", plan.status],
            ["Method", `${plan.method_id} · ${plan.method_version}`],
            ["Outcome", plan.outcome_metric_id, "mono"],
            ["Cohort", plan.cohort_id, "mono"],
            ["Content hash", plan.content_hash ?? "not frozen", "mono"],
            ["Prospective", plan.prospective ? "yes" : "no — frozen locally, not externally preregistered"],
          ]} />
        )}
        {frozen ? (
          <div className="note warn"><Lock size={12} /><span>This plan is frozen and immutable. Fork it to author an exploratory change; the original frozen content and every run remain intact.</span></div>
        ) : (
          <>
            <div className="split">
              <label className="field" style={{ display: "grid" }}><span>Method</span>
                <select className={select} value={methodId} onChange={(event) => setMethodId(event.target.value)}>
                  {methods.filter((item) => eligibility.find((entry) => entry.method_id === item.id && entry.status === "ELIGIBLE")).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </label>
              <label className="field" style={{ display: "grid" }}><span>Outcome</span>
                <select className={select} value={outcomeId} onChange={(event) => setOutcomeId(event.target.value)}>
                  {metrics.map((item) => <option key={item.id} value={item.id}>{item.label} ({item.unit})</option>)}
                </select>
              </label>
            </div>
            {methodId === "METH-REAL-TREND" && (
              <div className="split">
                <label className="field" style={{ display: "grid" }}><span>Reference occasion</span><input className={input} type="number" min={1} value={reference} onChange={(event) => setReference(Number(event.target.value))} /></label>
                <label className="field" style={{ display: "grid" }}><span>Contrast occasion</span><input className={input} type="number" min={2} value={contrast} onChange={(event) => setContrast(Number(event.target.value))} /></label>
              </div>
            )}
            {methodId === "METH-REAL-RELIABILITY" && (
              <label className="field" style={{ display: "grid" }}><span>Activity</span><input className={input} value={activity} onChange={(event) => setActivity(event.target.value)} /></label>
            )}
            <label className="field" style={{ display: "grid" }}><span>Primary estimand</span><textarea className={input} rows={2} value={estimand} onChange={(event) => setEstimand(event.target.value)} /></label>
            <label className="field" style={{ display: "grid" }}><span>Missing-data statement</span><input className={input} value={missing} onChange={(event) => setMissing(event.target.value)} /></label>
            <div className="split">
              <label className="field" style={{ display: "grid" }}><span>Covariates (comma separated)</span><input className={input} value={covariates} onChange={(event) => setCovariates(event.target.value)} /></label>
              <label className="field" style={{ display: "grid" }}><span>Fixed effects</span><input className={input} value={fixedEffects} onChange={(event) => setFixedEffects(event.target.value)} /></label>
              <label className="field" style={{ display: "grid" }}><span>Random effects</span><input className={input} value={randomEffects} onChange={(event) => setRandomEffects(event.target.value)} /></label>
              <label className="field" style={{ display: "grid" }}><span>Time coding</span><input className={input} value={timeCoding} onChange={(event) => setTimeCoding(event.target.value)} /></label>
              <label className="field" style={{ display: "grid" }}><span>Contrasts</span><input className={input} value={contrasts} onChange={(event) => setContrasts(event.target.value)} /></label>
            </div>
            <div className="block-toolbar">
              <Button variant="primary" onClick={() => onAct(() => save.mutateAsync(), "Analysis plan saved as a draft.")} disabled={save.isPending}><Save size={12} />Save plan</Button>
              <Button onClick={() => plan && onAct(() => scienceApi.freezePlan(plan.id), "Plan frozen. Future deviations create exploratory specifications.")} disabled={!plan || Boolean(plan.content_hash)}><Snowflake size={12} />Freeze plan</Button>
            </div>
          </>
        )}
        <div className="block-toolbar">
          {plan && <Button onClick={() => onAct(() => scienceApi.forkPlan(plan.id), "Plan forked as a new draft; the frozen plan is untouched.")}><GitFork size={12} />Fork plan</Button>}
          <span className="faint small">{plans.length} plan version{plans.length === 1 ? "" : "s"} stored</span>
        </div>
        <div className="section-title" style={{ marginTop: 6 }}><h2>Registered methods and qualification</h2></div>
        {eligibility.map((item) => (
          <div key={item.method_id} className="note" style={{ borderColor: item.status === "ELIGIBLE" ? "var(--line-2)" : "var(--warning)" }}>
            <State>{item.status}</State>
            <span><strong>{item.name}</strong> · {item.method_id} · qualification {item.qualification.status} ({item.qualification.record}). {item.issues.join(" ")}</span>
          </div>
        ))}
        {plan?.frozen_at && <div className="note"><Lock size={12} /><span>Frozen at {plan.frozen_at}. Historical plan versions and runs remain pinned.</span></div>}
      </div>
    </div>
  );
}

function Schedule({ studyId, schedule, onAct }: { studyId: string; schedule: Record<string, unknown>; onAct: (fn: () => Promise<unknown>, message: string) => void }) {
  const [startWeek, setStartWeek] = useState(Number(schedule.start_week ?? 5));
  const [weeks, setWeeks] = useState(Number(schedule.weeks ?? 12));
  const [frequency, setFrequency] = useState(String(schedule.frequency ?? "weekly"));
  const [missingPolicy, setMissingPolicy] = useState(String(schedule.missing_policy ?? "Missing scheduled measurements remain missing and are never imputed."));
  const save = useMutation({
    mutationFn: () => scienceApi.updateStudy(studyId, {
      schedule: {
        ...schedule,
        kind: "PLANNED_WEEKLY",
        axis: "week",
        start_week: startWeek,
        weeks,
        frequency,
        missing_policy: missingPolicy,
        points: Array.from({ length: weeks }, (_, index) => ({ index: index + 1, week: startWeek + index, label: `Week ${startWeek + index}`, planned: true })),
      },
    }),
  });
  return (
    <div className="frame">
      <div className="frame-body" style={{ display: "grid", gap: 10, padding: 12 }}>
        <div className="section-title" style={{ margin: 0 }}><h2>Monitoring schedule</h2><span>prospective plan, not observations</span></div>
        <div className="split">
          <label className="field" style={{ display: "grid" }}><span>Start week</span><input className={input} type="number" min={1} value={startWeek} onChange={(event) => setStartWeek(Number(event.target.value))} /></label>
          <label className="field" style={{ display: "grid" }}><span>Planned weeks</span><input className={input} type="number" min={1} max={104} value={weeks} onChange={(event) => setWeeks(Number(event.target.value))} /></label>
          <label className="field" style={{ display: "grid" }}><span>Frequency</span><input className={input} value={frequency} onChange={(event) => setFrequency(event.target.value)} /></label>
        </div>
        <label className="field" style={{ display: "grid" }}><span>Missing-data policy</span><textarea className={input} rows={2} value={missingPolicy} onChange={(event) => setMissingPolicy(event.target.value)} /></label>
        <div className="block-toolbar"><Button variant="primary" onClick={() => onAct(() => save.mutateAsync(), "Monitoring schedule saved; planned measurements remain distinct from readings.")}><Save size={12} />Save schedule</Button></div>
        <div className="note warn"><Unlock size={12} /><span>Saving a schedule does not create measurements. A planned point without a reading is missing, never zero.</span></div>
      </div>
    </div>
  );
}

function History({ studyId }: { studyId: string }) {
  const [history, setHistory] = useState<Array<Record<string, unknown>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    scienceApi.studyHistory(studyId).then(setHistory).catch((err) => setError(errorText(err)));
  }, [studyId]);
  if (error) return <ErrorBox error={error} />;
  if (!history) return <div className="frame-body">Reading version history…</div>;
  return (
    <div className="frame">
      <div className="frame-body" style={{ display: "grid", gap: 6, padding: 12 }}>
        <div className="section-title" style={{ margin: 0 }}><h2>Version history</h2><span>{history.length} recorded version{history.length === 1 ? "" : "s"}</span></div>
        {history.map((item) => (
          <div key={`${String(item.version)}-${String(item.change_type)}`} className="note" style={{ display: "flex", gap: 8 }}>
            <span className="mono faint">v{String(item.version)}</span>
            <State>{String(item.change_type)}</State>
            <span>{String(item.state)} · {String(item.title)}</span>
            <span className="faint" style={{ marginLeft: "auto" }}>{String(item.recorded_at).slice(0, 19).replace("T", " ")}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function StateActions({ studyId, study, onAct }: { studyId: string; study: ReturnType<typeof useWorkbench>["study"]; onAct: (fn: () => Promise<unknown>, message: string) => void }) {
  const [target, setTarget] = useState("");
  return (
    <div className="frame" style={{ marginTop: 12 }}>
      <div className="frame-body" style={{ display: "flex", gap: 8, alignItems: "center", padding: 10, flexWrap: "wrap" }}>
        <Settings2 size={13} />
        <span className="faint small">State</span><State>{study.study.state}</State>
        <select className={select} aria-label="Target study state" value={target} onChange={(event) => setTarget(event.target.value)}>
          <option value="">— transition —</option>
          {(study.allowed_transitions ?? []).map((state) => <option key={state} value={state}>{state}</option>)}
        </select>
        <Button size="sm" disabled={!target} onClick={() => onAct(() => scienceApi.transitionStudy(studyId, target), `Study state changed to ${target}.`)}><RefreshCw size={12} />Transition</Button>
        <span className="grow" />
        {study.study.state === "ARCHIVED" ? (
          <Button size="sm" onClick={() => onAct(() => scienceApi.restoreStudy(studyId), "Study restored; historical artifacts remain.")}><Unlock size={12} />Restore</Button>
        ) : (
          <Button size="sm" variant="ghost" onClick={() => onAct(() => scienceApi.archiveStudy(studyId), "Study archived; no scientific artifact was deleted.")}><Archive size={12} />Archive</Button>
        )}
        <span className="faint small"><Trash2 size={11} /> Archiving never deletes runs, evidence or reports.</span>
      </div>
    </div>
  );
}

