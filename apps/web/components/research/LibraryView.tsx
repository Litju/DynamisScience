"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { scienceApi } from "@/lib/api";
import { ErrorBox, Loading, State } from "@/components/ui";
import { LibraryDetail, type LibraryTab } from "./LibraryDetail";

const TABS: { id: LibraryTab; label: string }[] = [
  { id: "metrics", label: "Metrics" },
  { id: "protocols", label: "Protocols" },
  { id: "methods", label: "Methods" },
  { id: "models", label: "Models" },
];

export function LibraryView() {
  const params = useSearchParams();
  const router = useRouter();
  const tab = (TABS.some((item) => item.id === params.get("tab")) ? params.get("tab") : "metrics") as LibraryTab;
  const id = params.get("id");
  const library = useQuery({ queryKey: ["library"], queryFn: scienceApi.library });
  const select = (nextTab: LibraryTab, nextId?: string) => router.replace(`/library?tab=${nextTab}${nextId ? `&id=${nextId}` : ""}`, { scroll: false });

  const rows: { id: string; primary: string; secondary: string; meta: string; status: string }[] = !library.data
    ? []
    : tab === "metrics"
      ? library.data.metrics.map((item) => ({ id: item.id, primary: item.name, secondary: item.canonical_id, meta: item.unit, status: item.status }))
      : tab === "protocols"
        ? library.data.protocols.map((item) => ({ id: item.id, primary: item.name, secondary: item.id, meta: item.frequency, status: item.status }))
        : tab === "methods"
          ? library.data.methods.map((item) => ({ id: item.id, primary: item.name, secondary: item.id, meta: `v${item.version}`, status: item.status }))
          : library.data.models.map((item) => ({ id: item.id, primary: item.name, secondary: item.kind, meta: item.version ? `v${item.version}` : "", status: item.status }));
  const activeId = id ?? rows[0]?.id;

  return (
    <main className="page">
      <div className="page-inner">
        <div className="page-head">
          <div>
            <div className="crumb">LIBRARY</div>
            <h1>Library</h1>
            <p>Scientific definitions the workbench executes against. Different methods for the same apparent quantity remain different MetricDefinitions.</p>
          </div>
        </div>
        {library.isLoading && <Loading label="Loading scientific definitions" />}
        {library.error && <ErrorBox error={library.error} onRetry={() => void library.refetch()} />}
        {library.data && (
          <div className="lib-layout">
            <nav className="lib-tabs" aria-label="Library sections">
              {TABS.map((item) => (
                <button key={item.id} type="button" aria-pressed={tab === item.id} onClick={() => select(item.id)}>
                  {item.label}
                  <span className="mono faint">{library.data[item.id].length}</span>
                </button>
              ))}
            </nav>
            <div className="lib-list">
              <table className="table">
                <thead><tr><th>Definition</th><th>ID</th><th /><th>Status</th></tr></thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} role="button" tabIndex={0} className={`${row.id === activeId ? "is-selected" : ""} ${row.status === "UNAVAILABLE" ? "is-muted" : ""}`} onClick={() => select(tab, row.id)} onKeyDown={(event) => event.key === "Enter" && select(tab, row.id)}>
                      <td>{row.primary}</td>
                      <td className="mono faint">{row.secondary}</td>
                      <td className="mono faint">{row.meta}</td>
                      <td><State plain>{row.status}</State></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="lib-detail"><LibraryDetail library={library.data} tab={tab} id={activeId} /></div>
          </div>
        )}
      </div>
    </main>
  );
}
