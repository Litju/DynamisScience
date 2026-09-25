import { DataView } from "@/components/research/DataView";

export default async function SnapshotPage({ params }: { params: Promise<{ snapshotId: string }> }) {
  const { snapshotId } = await params;
  return <DataView snapshotId={snapshotId} />;
}
