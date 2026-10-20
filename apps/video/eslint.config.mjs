import { config } from "@remotion/eslint-config-flat";

// src/audio/sound.js is the brief's SOUND kit, kept verbatim (browser script, not a module).
export default [{ ignores: ["src/audio/sound.js"] }, ...config];
