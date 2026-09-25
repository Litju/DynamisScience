import { Suspense } from "react";
import { StudyWorkspace } from "@/components/workbench/StudyWorkspace";

export default async function StudyPage({ params }: { params: Promise<{ studyId: string }> }) {
  const { studyId } = await params;
  return (
    <Suspense fallback={null}>
      <StudyWorkspace studyId={studyId} />
    </Suspense>
  );
}
