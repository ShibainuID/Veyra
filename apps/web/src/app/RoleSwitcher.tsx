import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown, UserRound } from "lucide-react";
import { useToast } from "../components/Toast";
import { ROLE_OPTIONS, roleForToken, setToken, useRole } from "../lib/role-store";

/**
 * Switches the demo bearer token (manager, operator, vet). A switch drops every cached response,
 * because what a role may see and do differs, then refetches what is on screen.
 */
export function RoleSwitcher() {
  const role = useRole();
  const queryClient = useQueryClient();
  const toast = useToast();

  return (
    <label className="relative flex items-center">
      <span className="sr-only">Demo role</span>
      <UserRound
        aria-hidden="true"
        className="pointer-events-none absolute left-3 hidden size-5 text-on-shell-muted sm:block"
        strokeWidth={2.25}
      />
      <select
        value={role.token}
        onChange={(event) => {
          const token = event.target.value;
          setToken(token);
          void queryClient.resetQueries();
          toast.show({ title: `Now acting as ${roleForToken(token).label}`, tone: "neutral", duration: 3500 });
        }}
        className="min-h-11 cursor-pointer appearance-none rounded-control border-2 border-shell-line bg-shell py-1 pr-9 pl-3 font-bold sm:pr-10 sm:pl-10 text-on-shell transition-colors hover:bg-shell-2 [&>option]:bg-bg [&>option]:text-ink"
      >
        {ROLE_OPTIONS.map((option) => (
          <option key={option.token} value={option.token}>
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-3 size-5 text-on-shell-muted" strokeWidth={2.25} />
    </label>
  );
}
