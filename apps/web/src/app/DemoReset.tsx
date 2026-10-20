import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, RotateCcw } from "lucide-react";
import { useId, useState } from "react";
import { useNavigate } from "react-router";
import { Button, buttonClasses } from "../components/Button";
import { Drawer } from "../components/Drawer";
import { ErrorNotice } from "../components/feedback";
import { useToast } from "../components/Toast";
import { resetAskHistory } from "../features/assistant/AskPanel";
import { setMonitorState } from "../features/monitor/api";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { useRole } from "../lib/role-store";

type Scenario = "fresh" | "post-enrollment";

const SCENARIOS: readonly { value: Scenario; label: string; detail: string }[] = [
  { value: "fresh", label: "Fresh herd", detail: "Five seeded cattle. Sari is not enrolled yet: start the demo from enrollment." },
  {
    value: "post-enrollment",
    label: "After enrollment",
    detail: "Sari is already enrolled with a confirmed valuation: start the demo from coverage.",
  },
];

/**
 * The demo's reset control, for managers only: reseeds the sandbox to a scenario, then drops every
 * cached screen, the Monitor's replay, and the Ask history. The confirmation is inline in the panel.
 */
export function DemoReset({ compact = false }: { compact?: boolean }) {
  const role = useRole();
  const [open, setOpen] = useState(false);
  if (role.role !== "manager") return null;
  return (
    <>
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
        title={compact ? undefined : "Demo controls"}
        className={buttonClasses("shell", "md", compact ? "px-3" : "px-2.5")}
      >
        <FlaskConical aria-hidden="true" className="size-5" strokeWidth={2.25} />
        {/* Icon-only in the top bar, where the wallet and role need the room. */}
        <span className={compact ? undefined : "sr-only"}>Demo</span>
      </button>
      <ResetPanel open={open} onClose={() => setOpen(false)} />
    </>
  );
}

function ResetPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const name = useId();
  const [scenario, setScenario] = useState<Scenario>("fresh");
  const [confirming, setConfirming] = useState(false);

  const reset = useMutation({
    mutationFn: async (value: Scenario) =>
      (await api.POST("/api/v1/demo/reset", { params: { query: { scenario: value } } })).data!,
    onSuccess: (result) => {
      setMonitorState({ scenarioId: null, replayId: null, cameraId: null });
      resetAskHistory();
      queryClient.clear();
      close();
      navigate("/herd");
      toast.show({
        tone: "ok",
        title: "Demo reset",
        body: `${SCENARIOS.find((s) => s.value === result.scenario)?.label ?? result.scenario}: ${result.animals} animals seeded.`,
      });
    },
  });

  const close = () => {
    setConfirming(false);
    reset.reset();
    onClose();
  };

  return (
    <Drawer
      open={open}
      onClose={close}
      title="Demo controls"
      description="Sandbox only. A reset erases every record made since the last one and reseeds the herd."
      footer={
        confirming ? (
          <div className="flex flex-col gap-3">
            <p className="font-bold">Reset to “{SCENARIOS.find((s) => s.value === scenario)!.label}”? This can't be undone.</p>
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="danger" icon={RotateCcw} loading={reset.isPending} loadingLabel="Resetting…" onClick={() => reset.mutate(scenario)}>
                Reset the demo
              </Button>
              <Button variant="ghost" onClick={() => setConfirming(false)} disabled={reset.isPending}>
                Keep the current records
              </Button>
            </div>
          </div>
        ) : (
          <Button variant="secondary" icon={RotateCcw} onClick={() => setConfirming(true)}>
            Reset demo…
          </Button>
        )
      }
    >
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 font-bold">Start from</legend>
        {SCENARIOS.map((option) => (
          <label
            key={option.value}
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-control border-2 px-4 py-3",
              scenario === option.value ? "border-ink bg-surface-2" : "border-line-strong",
            )}
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={scenario === option.value}
              onChange={() => {
                setScenario(option.value);
                setConfirming(false);
              }}
              className="mt-1 size-5 flex-none accent-[var(--ink)]"
            />
            <span className="flex flex-col gap-0.5">
              <span className="font-bold">{option.label}</span>
              <span className="text-sm text-muted">{option.detail}</span>
            </span>
          </label>
        ))}
      </fieldset>
      {reset.error ? <ErrorNotice className="mt-4" error={reset.error} title="The demo didn't reset" /> : null}
    </Drawer>
  );
}
