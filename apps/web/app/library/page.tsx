import { Suspense } from "react";
import { LibraryView } from "@/components/research/LibraryView";

export default function LibraryPage() {
  return (
    <Suspense fallback={null}>
      <LibraryView />
    </Suspense>
  );
}
