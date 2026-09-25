"use client";

import type { AlgorithmEntry, Library, Metric, MethodEntry, ModelEntry, Protocol } from "@/lib/types";
import { KV, State } from "@/components/ui";

export type LibraryTab = "metrics" | "protocols" | "methods" | "models";

function List({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) return null;
  return (
    <>
      <h4>{title}</h4>
      <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
    </>
  );
}

export function MetricDetail({ metric }: { metric: Metric }) {
  return (
    <div>
      <div className="mono faint">{metric.id}</div>
      <h3>{metric.name}</h3>
      <State>{metric.status}</State>
      <h4>Definition</h4>
      <KV rows={[
        ["Canonical ID", metric.canonical_id, "mono"],
        ["Quantity", metric.quantity],
        ["Unit", metric.unit, "mono"],
        ["Method", metric.method],
        ["Protocol", metric.protocol_id, "mono"],
        ["Algorithm", `${metric.algorithm}@${metric.version}`, "mono"],
      ]} />
      <List title="Dependencies" items={metric.dependencies} />
      <List title="Known limitations" items={metric.known_limitations} />
      <h4>Usages</h4>
      <div className="mono small muted">{metric.usages?.length ? metric.usages.join(" · ") : "Not referenced by any spec or run"}</div>
    </div>
  );
}

export function ProtocolDetail({ protocol }: { protocol: Protocol }) {
  return (
    <div>
      <div className="mono faint">{protocol.id}</div>
      <h3>{protocol.name}</h3>
      <State>{protocol.status}</State>
      <h4>Acquisition</h4>
      <KV rows={[["Frequency", protocol.frequency], ["Method", protocol.method ?? protocol.description]]} />
    </div>
  );
}

export function MethodDetail({ method, algorithm }: { method: MethodEntry; algorithm?: AlgorithmEntry }) {
  return (
    <div>
      <div className="mono faint">{method.id} · v{method.version}</div>
      <h3>{method.name}</h3>
      <State>{method.status}</State>
      <h4>Estimation</h4>
      <KV rows={[
        ["Estimator", method.estimator],
        ["Fallback", method.fallback],
        ["Estimand", method.estimand],
        ["Algorithm", algorithm ? `${algorithm.id}@${algorithm.version}` : method.algorithm, "mono"],
        ["Implementation", algorithm?.implementation, "mono"],
      ]} />
      <List title="Requirements" items={method.requirements} />
      <List title="Outputs" items={method.outputs} />
      <List title="Known limitations" items={method.known_limitations} />
      <h4>Specs and runs</h4>
      <div className="mono small muted">{[...(method.specs ?? []), ...(method.runs ?? [])].join(" · ") || "—"}</div>
    </div>
  );
}

export function ModelDetail({ model, library }: { model: ModelEntry; library?: Library }) {
  const spec = library?.model_spec;
  const unavailable = model.status === "UNAVAILABLE";
  return (
    <div>
      <div className="mono faint">{model.id}</div>
      <h3>{model.name}</h3>
      <div style={{ display: "flex", gap: 6 }}><State>{model.status}</State><State tone="tone-neutral">{model.kind.toUpperCase()}</State></div>
      <h4>Description</h4>
      <p className="muted">{model.description}</p>
      {!unavailable && spec && spec.id === model.id && (
        <>
          <h4>Specification</h4>
          <KV rows={[
            ["Kind", spec.kind],
            ["Version", spec.version, "mono"],
            ["Inputs", spec.inputs.join(", "), "mono"],
            ["Outputs", spec.outputs.join(", "), "mono"],
          ]} />
        </>
      )}
      <List title="Inputs" items={model.inputs} />
      <List title="Known limitations" items={model.known_limitations} />
      {unavailable && <div className="note warn" style={{ marginTop: 10 }}>Not implemented. Listed so the method space is explicit; nothing in the workbench computes with it.</div>}
    </div>
  );
}

export function LibraryDetail({ library, tab, id }: { library: Library; tab: LibraryTab; id?: string | null }) {
  if (tab === "metrics") {
    const metric = library.metrics.find((item) => item.id === id) ?? library.metrics[0];
    return metric ? <MetricDetail metric={metric} /> : null;
  }
  if (tab === "protocols") {
    const protocol = library.protocols.find((item) => item.id === id) ?? library.protocols[0];
    return protocol ? <ProtocolDetail protocol={protocol} /> : null;
  }
  if (tab === "methods") {
    const method = library.methods.find((item) => item.id === id) ?? library.methods[0];
    return method ? <MethodDetail method={method} algorithm={library.algorithms.find((item) => item.id === method.algorithm)} /> : null;
  }
  const model = library.models.find((item) => item.id === id) ?? library.models[0];
  return model ? <ModelDetail model={model} library={library} /> : null;
}
