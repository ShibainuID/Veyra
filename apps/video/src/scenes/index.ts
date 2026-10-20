import type React from "react";
import type { SceneId } from "../beats";
import { ProblemBack, ProblemFront } from "./Problem";
import { HerdBack, HerdFront, RevealFront } from "./Reveal";
import { EnrollBack, EnrollFront } from "./Enroll";
import { PassportFront } from "./Passport";
import { InsuranceFront } from "./Insurance";
import { ApprovalFront } from "./Approval";
import { MonitorBack, MonitorFront } from "./Monitor";
import { AskFront, AuditFront, ClaimBack, ClaimFront, CloseBack, CloseFront } from "./Late";

export type SceneParts = { Back?: React.FC; Front?: React.FC };

// Each scene group draws a background part (under the hero phone) and a foreground part (over it).
export const SCENE_PARTS: Partial<Record<SceneId, SceneParts>> = {
  problem: { Back: ProblemBack, Front: ProblemFront },
  reveal: { Front: RevealFront },
  herd: { Back: HerdBack, Front: HerdFront },
  enroll: { Back: EnrollBack, Front: EnrollFront },
  passport: { Front: PassportFront },
  insurance: { Front: InsuranceFront },
  approval: { Front: ApprovalFront },
  monitor: { Back: MonitorBack, Front: MonitorFront },
  ask: { Front: AskFront },
  claim: { Back: ClaimBack, Front: ClaimFront },
  audit: { Front: AuditFront },
  close: { Back: CloseBack, Front: CloseFront },
};
