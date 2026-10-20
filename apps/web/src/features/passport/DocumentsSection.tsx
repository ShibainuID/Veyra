import { Download, FilePlus2, FileText, ShieldCheck } from "lucide-react";
import { useId, useRef, useState } from "react";
import { Button, ButtonLink } from "../../components/Button";
import { ErrorNotice, LoadingRegion, Skeleton } from "../../components/feedback";
import { Mono, Timestamp } from "../../components/figures";
import { Section } from "../../components/layout";
import { Provenance } from "../../components/Provenance";
import { StatusPill } from "../../components/StatusPill";
import { useToast } from "../../components/Toast";
import { cn } from "../../lib/cn";
import { useRole } from "../../lib/role-store";
import type { Passport } from "./api";
import {
  DOCUMENT_ACCEPT,
  DOCUMENT_KINDS,
  MAX_DOCUMENT_BYTES,
  documentKindLabel,
  formatBytes,
  useDocuments,
  useUploadDocument,
  type DocumentKind,
} from "./documents";

const FIELD =
  "min-h-11 w-full rounded-control border-2 border-line-strong bg-bg px-3 py-2 text-base placeholder:text-muted focus:border-ink";

function UploadControl({ animalId, defaultKind }: { animalId: string; defaultKind: DocumentKind }) {
  const upload = useUploadDocument(animalId);
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<DocumentKind>(defaultKind);
  const [title, setTitle] = useState("");
  const [tooLarge, setTooLarge] = useState(false);
  const titleId = useId();

  const send = (file: File) => {
    if (file.size > MAX_DOCUMENT_BYTES) {
      setTooLarge(true);
      return;
    }
    setTooLarge(false);
    upload.mutate(
      { file, kind, title },
      {
        onSuccess: (document) => {
          setTitle("");
          toast.show({
            tone: "ok",
            title: `${documentKindLabel(document.kind)} document on file`,
            body: document.kind === "ownership" ? "It is now this animal's ownership reference for insurance eligibility." : document.title,
          });
        },
      },
    );
  };

  return (
    <div className="mt-6 flex flex-col gap-4 rounded-panel border-2 border-ink p-5">
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1.5 font-bold">
          Add a document
        </legend>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {DOCUMENT_KINDS.map((k) => (
            <label
              key={k.value}
              className={cn(
                "flex min-h-11 cursor-pointer items-center gap-2 rounded-control border-2 px-3 font-bold",
                kind === k.value ? "border-ink bg-surface-2" : "border-line-strong",
              )}
            >
              <input type="radio" name={`document-kind-${animalId}`} value={k.value} checked={kind === k.value} onChange={() => setKind(k.value)} className="size-5 accent-[var(--ink)]" />
              <span>{k.label}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={titleId} className="font-bold">
          Title <span className="font-regular text-muted">(optional)</span>
        </label>
        <input id={titleId} className={FIELD} value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} placeholder="Ownership certificate" />
      </div>
      <input
        ref={fileRef}
        type="file"
        accept={DOCUMENT_ACCEPT}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) send(file);
        }}
      />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button variant="primary" icon={FilePlus2} loading={upload.isPending} loadingLabel="Uploading…" onClick={() => fileRef.current?.click()}>
          Choose file and upload
        </Button>
        <span className="text-sm text-muted">PDF, JPEG, or PNG, up to 10 MB. Files download; they never open inside VEYRA.</span>
      </div>
      {tooLarge && <p role="alert" className="font-bold text-danger">That file is larger than 10 MB. Choose a smaller scan or PDF.</p>}
      {upload.error ? <ErrorNotice error={upload.error} title="The document wasn't added" /> : null}
    </div>
  );
}

/**
 * Documents kept with the passport (ownership certificates, receipts, vet records). An ownership document is the
 * animal's ownership reference, which the Mortality + Theft product requires.
 */
export function DocumentsSection({ passport }: { passport: Passport }) {
  const { animal } = passport;
  const documents = useDocuments(animal.id);
  const { role } = useRole();
  const canUpload = role === "manager" || role === "operator";
  const items = documents.data ?? [];
  const refsWithoutFile = animal.ownership_doc_refs.filter((ref) => !items.some((d) => d.id === ref));
  const hasOwnership = animal.ownership_doc_refs.length > 0;

  return (
    <Section
      title="Documents"
      anchor="documents"
      description="Ownership, purchase, and veterinary papers kept with this passport, each with its upload date and size."
      className="scroll-mt-(--shell-height)"
    >
      {documents.isPending ? (
        <LoadingRegion label="Loading documents">
          <Skeleton lines={2} />
        </LoadingRegion>
      ) : documents.error ? (
        <ErrorNotice error={documents.error} title="Documents couldn't load" onRetry={() => void documents.refetch()} />
      ) : items.length === 0 && refsWithoutFile.length === 0 ? (
        <div className="rounded-panel border-2 border-dashed border-line-strong px-6 py-6">
          <div className="flex max-w-[62ch] flex-col items-start gap-2">
            <FileText aria-hidden="true" className="size-7 text-muted" strokeWidth={2} />
            <h3 className="text-md font-bold">No documents on file</h3>
            <p className="text-muted">
              An ownership document is required for Mortality + Theft. Upload the ownership certificate and it becomes this animal's
              ownership reference; until then that product stays at "needs review".
            </p>
          </div>
        </div>
      ) : (
        <ul className="flex flex-col border-t-2 border-ink">
          {items.map((document) => (
            <li key={document.id} className="grid gap-x-6 gap-y-2 border-b border-line py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
              <span className="flex min-w-0 items-start gap-3">
                <FileText aria-hidden="true" className="mt-0.5 size-5 flex-none" strokeWidth={2.25} />
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-bold break-words">{document.title}</span>
                    {document.kind === "ownership" ? (
                      <StatusPill tone="ok" label="Ownership reference" />
                    ) : (
                      <StatusPill tone="neutral" label={documentKindLabel(document.kind)} />
                    )}
                  </span>
                  <span className="text-sm text-muted">
                    <Timestamp value={document.created_at} mode="absolute" /> · <Mono>{formatBytes(document.bytes)}</Mono> ·{" "}
                    {document.content_type === "application/pdf" ? "PDF" : document.content_type === "image/png" ? "PNG" : "JPEG"} · added by{" "}
                    {document.uploaded_by}
                  </span>
                  <span className="text-sm text-muted">
                    <Mono>{document.id}</Mono> · SHA-256 <Mono>{document.sha256.slice(0, 12)}</Mono>
                  </span>
                </span>
              </span>
              <a
                href={document.url}
                download={document.filename}
                className="inline-flex min-h-11 items-center gap-2 justify-self-start rounded-control border-2 border-ink px-4 font-bold no-underline hover:bg-surface-2"
              >
                <Download aria-hidden="true" className="size-5" strokeWidth={2.25} />
                Download
                <span className="sr-only"> {document.title}</span>
              </a>
            </li>
          ))}
          {refsWithoutFile.map((ref) => (
            <li key={ref} className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line py-4">
              <FileText aria-hidden="true" className="size-5 flex-none" strokeWidth={2.25} />
              <span className="flex min-w-0 flex-col gap-1">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-bold">Ownership reference</span>
                  <Provenance source="documented" />
                </span>
                <span className="text-sm text-muted">
                  <Mono>{ref}</Mono> · a reference from the herd register, with no file attached in VEYRA
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
      {hasOwnership && (
        <p className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2">
          <ShieldCheck aria-hidden="true" className="size-5 text-ok" strokeWidth={2.25} />
          <span>An ownership reference is on file, so Mortality + Theft can check its ownership rule.</span>
          <ButtonLink to={`/animals/${animal.id}/insurance`} variant="ghost">
            See eligibility
          </ButtonLink>
        </p>
      )}
      {canUpload ? (
        <UploadControl animalId={animal.id} defaultKind={hasOwnership ? "other" : "ownership"} />
      ) : (
        <p className="mt-4 text-muted">A manager or operator adds documents.</p>
      )}
    </Section>
  );
}
