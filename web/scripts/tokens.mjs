// The one place the palette is read. design/tokens.json is the source of truth;
// this turns it into the CSS variables and the Tailwind colour scale, so a
// colour is never written twice.
import { readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";

const tokensPath = fileURLToPath(new URL("../../design/tokens.json", import.meta.url));
const tokens = JSON.parse(readFileSync(tokensPath, "utf8"));

/** Token name as used in CSS and Tailwind: lower kebab case. */
const cssName = (name) => name.replace(/_/g, "-");

export const palette = Object.fromEntries(
  [...Object.entries(tokens.palette), ...Object.entries(tokens.web_palette)].map(
    ([name, entry]) => [cssName(name), entry.hex],
  ),
);

/** `hairline` is the palette's `track` under the name the web uses. */
palette.hairline = palette.track;

export const cssVariables = Object.entries(palette)
  .map(([name, hex]) => `  --jk-${name}: ${hex};`)
  .join("\n");
