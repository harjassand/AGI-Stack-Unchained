import OmegaDashboard from "../../../components/common/OmegaDashboard";

export default function RunDashboardPage({ params }: { params: { runId: string } }) {
  return <OmegaDashboard runId={decodeURIComponent(params.runId)} />;
}
