import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";

// Film headlines: Inter (as the brief asks), weights 300/400/600/800.
loadInter("normal", { weights: ["300", "400", "600", "800"], subsets: ["latin"] });

// The app's own faces (Ear Tag design system), copied from apps/web's @fontsource-variable packages.
loadFont({
  family: "Atkinson Hyperlegible Next",
  url: staticFile("fonts/atkinson-hyperlegible-next-latin-wght-normal.woff2"),
  weight: "200 800",
});
loadFont({
  family: "Atkinson Hyperlegible Mono",
  url: staticFile("fonts/atkinson-hyperlegible-mono-latin-wght-normal.woff2"),
  weight: "200 800",
});
