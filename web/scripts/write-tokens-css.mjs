// Writes src/tokens.css from design/tokens.json. Run by `npm run build` and
// `npm run dev` through the Vite plugin in vite.config.ts.
import { writeFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";
import { cssVariables } from "./tokens.mjs";

const target = fileURLToPath(new URL("../src/tokens.css", import.meta.url));
writeFileSync(
  target,
  `/* Generated from design/tokens.json by scripts/write-tokens-css.mjs. Do not edit. */\n:root {\n${cssVariables}\n}\n`,
);
