import { Link, useParams } from "react-router";
import { EmptyState } from "../components/Feedback";
import { PageHeader } from "../components/PageHeader";
import { PlanReview } from "../plans/PlanReview";

export default function PlanPage() {
  const runId = Number(useParams().runId);
  if (!Number.isInteger(runId) || runId <= 0) {
    return <EmptyState title="This Plan does not exist" />;
  }
  return (
    <>
      <PageHeader
        title="Plan review"
        documentTitle={`Plan ${runId}`}
        description={
          <>
            Plan of{" "}
            <Link className="text-accent hover:underline" to={`/history/${runId}`}>
              sync run {runId}
            </Link>
            . Choose the groups to apply to Rekordbox.
          </>
        }
      />
      <PlanReview runId={runId} />
    </>
  );
}
