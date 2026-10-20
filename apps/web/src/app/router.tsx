import { lazy, Suspense } from "react";
import { createBrowserRouter, isRouteErrorResponse, useRouteError, type RouteObject } from "react-router";
import { ErrorNotice, LoadingRegion, Skeleton } from "../components/feedback";
import { PageHeader } from "../components/layout";
import { Page } from "../pages/Page";
import { AuditPage } from "../features/audit/AuditPage";
import { HerdPage } from "../features/herd/HerdPage";
import { LandingPage } from "../features/landing/LandingPage";
import { PassportPage } from "../features/passport/PassportPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { ApprovalsPage } from "../features/approvals/ApprovalsPage";
import { AskPage } from "../features/assistant/Ask";
import { ClaimPage } from "../features/claims/ClaimPage";
import { ClaimsPage } from "../features/claims/ClaimsPage";
import { EnrollPage } from "../features/enrollment/EnrollPage";
import { InsurancePage } from "../features/insurance/InsurancePage";
import { MonitorScreen } from "../features/monitor/MonitorScreen";
import { AgentPage } from "../features/agent/AgentPage";
import { AppShell } from "./AppShell";

function RouteError() {
  const error = useRouteError();
  const code = isRouteErrorResponse(error) && error.status === 404 ? "NOT_FOUND" : undefined;
  return (
    <Page>
      <PageHeader title="This screen couldn't load" />
      <ErrorNotice error={error} code={code} onRetry={() => window.location.reload()} />
    </Page>
  );
}

// The component gallery is for visual QA in development and never ships in a production build.
const DesignPage = import.meta.env.DEV ? lazy(() => import("../pages/DesignPage")) : null;

const devRoutes: RouteObject[] = DesignPage
  ? [
      {
        path: "_design",
        element: (
          <Suspense
            fallback={
              <Page>
                <LoadingRegion label="Loading the component gallery">
                  <Skeleton lines={4} />
                </LoadingRegion>
              </Page>
            }
          >
            <DesignPage />
          </Suspense>
        ),
      },
    ]
  : [];

export const routes: RouteObject[] = [
  // The pitch page stands outside the app shell, with its own nav; the app starts at /herd.
  { path: "/", element: <LandingPage />, errorElement: <RouteError /> },
  {
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      { path: "herd", element: <HerdPage /> },
      { path: "enroll", element: <EnrollPage /> },
      { path: "animals/:animalId", element: <PassportPage /> },
      { path: "animals/:animalId/insurance", element: <InsurancePage /> },
      // One Monitor element for both paths, so opening an alert's drawer keeps the replay running beneath it.
      {
        element: <MonitorScreen />,
        children: [
          { path: "monitor", element: null },
          { path: "alerts/:alertId", element: null },
        ],
      },
      { path: "approvals", element: <ApprovalsPage /> },
      { path: "claims", element: <ClaimsPage /> },
      { path: "claims/:claimId", element: <ClaimPage /> },
      { path: "audit", element: <AuditPage /> },
      { path: "ask", element: <AskPage /> },
      { path: "agent", element: <AgentPage /> },
      ...devRoutes,
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}
