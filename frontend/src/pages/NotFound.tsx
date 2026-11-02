import { ButtonLink } from "../components/Button";
import { EmptyState } from "../components/Feedback";
import { PageHeader } from "../components/PageHeader";

export default function NotFound() {
  return (
    <>
      <PageHeader title="Page not found" />
      <EmptyState title="This page does not exist">
        <ButtonLink className="mt-4" to="/">
          Go to the Dashboard
        </ButtonLink>
      </EmptyState>
    </>
  );
}
