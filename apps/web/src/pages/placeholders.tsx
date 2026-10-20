/*
 * Placeholder screens (F1). Each uses the real page header and an empty state that says what
 * the screen will hold, so the shell and routes can be walked before F3–F10 land.
 */
import {
  Cctv,
  ClipboardList,
  FileCheck2,
  MessageSquareText,
  ScanLine,
  ScrollText,
  ShieldCheck,
  Siren,
  Stamp,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { useParams } from "react-router";
import { ButtonLink } from "../components/Button";
import { EmptyState } from "../components/feedback";
import { Mono } from "../components/figures";
import { PageHeader } from "../components/layout";
import { Page } from "./Page";

function Placeholder({
  title,
  meta,
  emptyTitle,
  icon,
  children,
  action,
}: {
  title: string;
  meta: ReactNode;
  emptyTitle: string;
  icon: LucideIcon;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <Page>
      <PageHeader title={title} meta={meta} />
      <EmptyState title={emptyTitle} icon={icon} action={action}>
        {children}
      </EmptyState>
    </Page>
  );
}

export function HerdPage() {
  return (
    <Placeholder
      title="Herd"
      meta="Every tagged animal, its exposure, and its cover."
      emptyTitle="The herd table and passbook go here"
      icon={ClipboardList}
      action={
        <ButtonLink to="/enroll" variant="primary" icon={ScanLine}>
          Enroll an animal
        </ButtonLink>
      }
    >
      Each animal will be listed with its ear tag first, its indicative exposure, and its cover. Selecting one opens its
      passbook beside the table.
    </Placeholder>
  );
}

export function EnrollPage() {
  return (
    <Placeholder
      title="Enroll"
      meta="Register a new animal from a short guided video."
      emptyTitle="Guided enrollment goes here"
      icon={ScanLine}
    >
      You will record the muzzle, teeth, and body in turn. VEYRA proposes an identity, and you confirm, link, or reject it
      before the animal gets its tag.
    </Placeholder>
  );
}

export function PassportPage() {
  const { animalId = "" } = useParams();
  return (
    <Placeholder title="Passport" meta={<Mono>{animalId}</Mono>} emptyTitle="This animal's passport goes here" icon={ClipboardList}>
      It will show the ear tag, the registered evidence frames, each estimate with its uncertainty and source, the cover, and
      every passbook line.
    </Placeholder>
  );
}

export function InsurancePage() {
  const { animalId = "" } = useParams();
  return (
    <Placeholder
      title="Insurance options"
      meta={<Mono>{animalId}</Mono>}
      emptyTitle="Product comparison goes here"
      icon={ShieldCheck}
    >
      Three sandbox products will be compared for this animal, each marked eligible, ineligible, or unknown, with its premium
      basis, exclusions, and terms reference.
    </Placeholder>
  );
}

export function MonitorPage() {
  return (
    <Placeholder title="Monitor" meta="Camera replay and movement alerts, by pen." emptyTitle="Camera replay goes here" icon={Cctv}>
      Each camera track will show the animal it belongs to, beside a pen map that shares coordinates with the herd table.
      Alerts post to a live feed as they are raised.
    </Placeholder>
  );
}

export function AlertPage() {
  const { alertId = "" } = useParams();
  return (
    <Placeholder title="Alert" meta={<Mono>{alertId}</Mono>} emptyTitle="Alert details go here" icon={Siren}>
      This alert will open as a drawer over Monitor, with the observation window, the clip, and the acknowledge and note
      actions.
    </Placeholder>
  );
}

export function ApprovalsPage() {
  return (
    <Placeholder
      title="Approvals"
      meta="Lines waiting on your stamp, and the sandbox wallet."
      emptyTitle="The approval queue goes here"
      icon={Stamp}
    >
      Every action the agent prepares waits here, with exactly what will execute, until a manager approves and stamps it or
      declines it.
    </Placeholder>
  );
}

export function ClaimsPage() {
  return (
    <Placeholder title="Claims" meta="Incidents and their sandbox claim submissions." emptyTitle="No claims yet" icon={FileCheck2}>
      A recorded incident becomes a claim here, with its evidence checklist, the declaration, and the submission receipt.
    </Placeholder>
  );
}

export function ClaimPage() {
  const { claimId = "" } = useParams();
  return (
    <Placeholder title="Claim" meta={<Mono>{claimId}</Mono>} emptyTitle="This claim's file goes here" icon={FileCheck2}>
      It will show the incident, the evidence checklist with anything missing named, the declaration, and the receipt once
      submitted.
    </Placeholder>
  );
}

export function AuditPage() {
  return (
    <Placeholder title="Audit" meta="Every proposal, decision, and provider result, in order." emptyTitle="The audit trail goes here" icon={ScrollText}>
      Each event will name its actor (a person, the agent, the system, or a provider) and link to the animal and record it
      touched.
    </Placeholder>
  );
}

export function AskPage() {
  return (
    <Placeholder title="Ask" meta="Plain questions about the herd." emptyTitle="The assistant goes here" icon={MessageSquareText}>
      Ask something like "where was animal-demo-001 last seen?" and the answer will cite the records behind it, each one a
      link.
    </Placeholder>
  );
}

export function NotFoundPage() {
  return (
    <Placeholder
      title="Page not found"
      meta="This address doesn't match any screen."
      emptyTitle="Nothing lives at this address"
      icon={ClipboardList}
      action={
        <ButtonLink to="/" variant="primary">
          Back to the herd
        </ButtonLink>
      }
    >
      Check the link, or go back to the herd and open the animal from there.
    </Placeholder>
  );
}
