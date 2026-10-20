import { ClipboardList } from "lucide-react";
import { ButtonLink } from "../components/Button";
import { EmptyState } from "../components/feedback";
import { PageHeader } from "../components/layout";
import { Page } from "./Page";

/** The catch-all screen for an address that matches no route, and for an animal that doesn't exist. */
export function NotFoundPage() {
  return (
    <Page>
      <PageHeader title="Page not found" meta="This address doesn't match any screen." />
      <EmptyState
        title="Nothing lives at this address"
        icon={ClipboardList}
        action={
          <ButtonLink to="/herd" variant="primary">
            Back to the herd
          </ButtonLink>
        }
      >
        Check the link, or go back to the herd and open the animal from there.
      </EmptyState>
    </Page>
  );
}
