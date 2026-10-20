// Browser entry for scripts/render-effects.mjs: exposes the score and the film length to the SOUND kit page.
import { DURATION } from "../beats";
import { scoreSound } from "./score";

declare global {
  interface Window {
    scoreSound: typeof scoreSound;
    DURATION: number;
  }
}
window.scoreSound = scoreSound;
window.DURATION = DURATION;
