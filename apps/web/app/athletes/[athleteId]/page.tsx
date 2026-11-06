import { AthleteView } from "@/components/performance/AthleteView";

export default async function AthletePage({ params }: { params: Promise<{ athleteId: string }> }) {
  const { athleteId } = await params;
  return <AthleteView athleteId={athleteId} />;
}
