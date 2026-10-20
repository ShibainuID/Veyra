import { MessageSquareText } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useLocation } from "react-router";
import { buttonClasses } from "../../components/Button";
import { Drawer } from "../../components/Drawer";
import { PageHeader } from "../../components/layout";
import { cn } from "../../lib/cn";
import { Page } from "../../pages/Page";
import { AskPanel } from "./AskPanel";

const DESCRIPTION = "Plain questions about the herd, answered from the farm's records.";

/**
 * The top bar's Ask control. Everywhere but /ask it opens the assistant in a drawer over the current screen;
 * on /ask it marks the current page. The drawer closes when an answer's link is followed.
 */
export function AskButton({ pathname }: { pathname: string }) {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const onAskPage = pathname === "/ask";

  useEffect(() => {
    setOpen(false);
  }, [location.pathname, location.search]);

  const content = (
    <>
      <MessageSquareText aria-hidden="true" className="size-5" strokeWidth={2.25} />
      {/* Icon-only between 1024 and 1280px, where the full bar is tightest. */}
      <span className="lg:max-xl:sr-only">Ask</span>
    </>
  );

  if (onAskPage) {
    return (
      <Link to="/ask" aria-current="page" className={buttonClasses("shell", "md", "border-tag px-3")}>
        {content}
      </Link>
    );
  }
  return (
    <>
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
        className={buttonClasses("shell", "md", cn("px-3", open && "border-tag"))}
      >
        {content}
      </button>
      {/* Portalled out of the shell bar, so the drawer takes the page's focus ring and ink, not the shell's. */}
      {createPortal(
      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title="Ask"
        description={
          <span className="flex flex-wrap items-baseline gap-x-3">
            {DESCRIPTION}
            <Link to="/ask" className="text-sm font-bold text-ink">
              Open as a page
            </Link>
          </span>
        }
      >
        {open && <AskPanel autoFocus />}
      </Drawer>,
        document.body,
      )}
    </>
  );
}

export function AskPage() {
  return (
    <Page className="max-w-4xl">
      <PageHeader title="Ask" meta={DESCRIPTION} />
      <AskPanel autoFocus />
    </Page>
  );
}
