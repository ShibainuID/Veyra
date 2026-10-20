import { RadioTower } from "lucide-react";
import { Button } from "../../components/Button";
import { ErrorNotice, LoadingRegion, Skeleton } from "../../components/feedback";
import { Mono, Timestamp } from "../../components/figures";
import { Provenance } from "../../components/Provenance";
import { StatusPill } from "../../components/StatusPill";
import { useRole } from "../../lib/role-store";
import { useCameras, usePublishGallery, type CameraOut, type Passport } from "./api";

const GALLERY_STATUSES = new Set(["confirmed", "pending_review"]);

function list(ids: readonly string[]) {
  return ids.map((id, i) => (
    <span key={id}>
      {i > 0 && ", "}
      <Mono>{id}</Mono>
    </span>
  ));
}

function latest(cameras: readonly CameraOut[]): string | null {
  const times = cameras.map((c) => c.gallery?.synced_at).filter((t): t is string => Boolean(t));
  return times.sort().at(-1) ?? null;
}

function Summary({ name, cameras, version }: { name: string; cameras: readonly CameraOut[]; version: number }) {
  const synced = cameras.filter((c) => c.gallery?.in_sync);
  const behind = cameras.filter((c) => !c.gallery?.in_sync);
  const at = latest(synced);
  if (synced.length === 0) {
    return (
      <p>
        No pen camera holds gallery <Mono>v{version}</Mono> yet, so the cameras don't know {name} yet.
      </p>
    );
  }
  return (
    <p>
      <span className="font-bold">Pen cameras know {name}:</span> gallery <Mono>v{version}</Mono> synced{" "}
      {at && <Timestamp value={at} mode="relative" />} on {list(synced.map((c) => c.id))}
      {behind.length > 0 && (
        <>
          ; {list(behind.map((c) => c.id))} not synced yet
        </>
      )}
      .
    </p>
  );
}

function CameraRow({ camera }: { camera: CameraOut }) {
  const gallery = camera.gallery;
  const pill = !gallery?.synced_version
    ? { tone: "neutral" as const, label: "Not synced" }
    : gallery.in_sync
      ? { tone: "ok" as const, label: `In sync · v${gallery.synced_version}` }
      : { tone: "uncertain" as const, label: `Out of date · has v${gallery.synced_version}` };
  return (
    <li className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-line py-2.5">
      <span className="flex min-w-0 flex-col">
        <span className="font-bold">{camera.name}</span>
        <Mono className="text-sm text-muted">{camera.id}</Mono>
      </span>
      <span className="flex flex-wrap items-center gap-2">
        <StatusPill tone={pill.tone} label={pill.label} />
        {gallery?.synced_at && <Timestamp value={gallery.synced_at} mode="relative" className="text-sm text-muted" />}
        {gallery?.source === "simulated" && <Provenance source="simulated" />}
      </span>
    </li>
  );
}

/**
 * What the pen cameras know about this animal: the cloud keeps the herd's muzzle gallery, and each camera
 * acknowledges the version it has loaded. A manager can push the current version to the cameras.
 */
export function CameraGallery({ passport }: { passport: Passport }) {
  const { animal, references } = passport;
  const cameras = useCameras();
  const publish = usePublishGallery();
  const { role } = useRole();
  const muzzle = references.find((r) => r.view === "muzzle");
  const listed = Boolean(muzzle) && GALLERY_STATUSES.has(animal.identity_status);
  const items = cameras.data ?? [];
  const version = items.find((c) => c.gallery)?.gallery?.current_version ?? null;

  return (
    <div className="flex flex-col gap-3" data-testid="camera-gallery">
      <h3 className="font-bold">Camera gallery</h3>
      {cameras.isPending ? (
        <LoadingRegion label="Loading the camera gallery">
          <Skeleton lines={2} />
        </LoadingRegion>
      ) : cameras.error ? (
        <ErrorNotice error={cameras.error} title="Camera gallery status couldn't load" onRetry={() => void cameras.refetch()} />
      ) : items.length === 0 || version === null ? (
        <p className="text-muted">This farm has no pen cameras to sync.</p>
      ) : (
        <>
          {listed ? (
            <Summary name={animal.name} cameras={items} version={version} />
          ) : (
            <p>
              {animal.name} is not in the camera gallery: {muzzle ? "the identity is not confirmed." : "no muzzle reference is on the passport."}
            </p>
          )}
          {listed && animal.identity_status === "pending_review" && (
            <p className="text-sm text-uncertain-ink">The gallery lists {animal.name} flagged as pending review.</p>
          )}
          {listed && muzzle && !muzzle.crop_url && !muzzle.media_url && (
            <p className="text-sm text-muted">
              {animal.name}'s muzzle reference has no footage attached, so the cameras receive the record without an image.
            </p>
          )}
          <ul className="flex flex-col border-t border-line">
            {items.map((camera) => (
              <CameraRow key={camera.id} camera={camera} />
            ))}
          </ul>
          {role === "manager" && (
            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant="secondary"
                icon={RadioTower}
                loading={publish.isPending}
                loadingLabel="Pushing…"
                onClick={() => publish.mutate()}
              >
                Push to cameras
              </Button>
              <span className="flex flex-wrap items-center gap-2 text-sm text-muted">
                {publish.data ? (
                  <>
                    Pushed <Mono>v{publish.data.version}</Mono> · <Mono>{publish.data.acknowledged.length}</Mono> camera
                    {publish.data.acknowledged.length === 1 ? "" : "s"} acknowledged
                  </>
                ) : (
                  "Sends the current gallery to the pen cameras."
                )}
                <Provenance source="simulated" />
                <span>Camera acknowledgements are simulated in the demo.</span>
              </span>
            </div>
          )}
          {publish.error ? <ErrorNotice error={publish.error} title="The gallery wasn't pushed" /> : null}
        </>
      )}
    </div>
  );
}
