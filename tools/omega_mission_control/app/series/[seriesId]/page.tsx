import OmegaSeriesDashboard from "../../../components/common/OmegaSeriesDashboard";

export default function SeriesDashboardPage({ params }: { params: { seriesId: string } }) {
  return <OmegaSeriesDashboard seriesId={decodeURIComponent(params.seriesId)} />;
}
