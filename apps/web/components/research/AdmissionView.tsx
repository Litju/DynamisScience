"use client";

import { useQuery } from "@tanstack/react-query";
import { scienceApi } from "@/lib/api";
import { ErrorBox, Loading } from "@/components/ui";

export function AdmissionView() {
  const sources = useQuery({ queryKey: ["admission-sources"], queryFn: scienceApi.admissionSources });
  const records = useQuery({ queryKey: ["admission-records"], queryFn: scienceApi.admissionRecords });
  const snapshots = useQuery({ queryKey: ["admission-snapshots"], queryFn: scienceApi.admissionSnapshots });
  const qualification = useQuery({ queryKey: ["qualification"], queryFn: scienceApi.qualification });

  if (sources.isLoading || records.isLoading || snapshots.isLoading || qualification.isLoading) {
    return <Loading label="Loading admission state" />;
  }
  if (sources.error) return <ErrorBox error={sources.error} onRetry={() => void sources.refetch()} />;

  return (
    <main className="page">
      <div className="page-inner">
        <div className="page-head">
          <div>
            <div className="crumb">DATA / ADMISSION</div>
            <h1>Real-data admission</h1>
            <p>Source rights, validation, harmonization and immutable snapshot admission.</p>
          </div>
        </div>
        <div className="frame">
          <div className="frame-head"><h3>Sources</h3></div>
          <div className="frame-body">
            <pre className="mono small">{JSON.stringify(sources.data ?? [], null, 2)}</pre>
          </div>
        </div>
        <div className="frame" style={{ marginTop: 14 }}>
          <div className="frame-head"><h3>Admission records</h3></div>
          <div className="frame-body">
            <pre className="mono small">{JSON.stringify(records.data ?? [], null, 2)}</pre>
          </div>
        </div>
        <div className="frame" style={{ marginTop: 14 }}>
          <div className="frame-head"><h3>Admitted snapshots</h3></div>
          <div className="frame-body">
            <pre className="mono small">{JSON.stringify(snapshots.data ?? [], null, 2)}</pre>
          </div>
        </div>
        <div className="frame" style={{ marginTop: 14 }}>
          <div className="frame-head"><h3>Scientific qualification</h3></div>
          <div className="frame-body">
            <pre className="mono small">{JSON.stringify(qualification.data ?? [], null, 2)}</pre>
          </div>
        </div>
      </div>
    </main>
  );
}