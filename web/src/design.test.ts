// The panel's design rules (design/UI_DESIGN.md): the palette is the one in
// design/tokens.json, and there is no emoji anywhere.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

// vitest runs from web/, so the checkout root is one level up.
const SOURCE = resolve(process.cwd(), "src");
const TOKENS = JSON.parse(
  readFileSync(resolve(process.cwd(), "..", "design", "tokens.json"), "utf8"),
) as {
  palette: Record<string, { hex: string }>;
  web_palette: Record<string, { hex: string }>;
  glyphs: string[];
};

const PALETTE = new Set(
  [...Object.values(TOKENS.palette), ...Object.values(TOKENS.web_palette)].map((entry) =>
    entry.hex.toLowerCase(),
  ),
);

const ALLOWED_GLYPHS = new Set(TOKENS.glyphs);

function sources(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.(ts|tsx|css)$/.test(path) && !path.endsWith(".test.ts") ? [path] : [];
  });
}

const FILES = sources(SOURCE).filter((path) => !path.endsWith("tokens.css"));

describe("the panel keeps its design rules", () => {
  it("has files to check", () => {
    expect(FILES.length).toBeGreaterThan(5);
  });

  it("writes no colour that is not in design/tokens.json", () => {
    const strays: string[] = [];
    for (const path of FILES) {
      for (const found of readFileSync(path, "utf8").match(/#[0-9a-fA-F]{6}\b/g) ?? []) {
        if (!PALETTE.has(found.toLowerCase())) strays.push(`${path}: ${found}`);
      }
    }
    expect(strays).toEqual([]);
  });

  it("uses no emoji and no unapproved glyph", () => {
    const strays: string[] = [];
    for (const path of FILES) {
      for (const character of readFileSync(path, "utf8")) {
        const code = character.codePointAt(0) ?? 0;
        if (code > 127 && !ALLOWED_GLYPHS.has(character)) {
          strays.push(`${path}: ${character} (U+${code.toString(16).toUpperCase()})`);
        }
      }
    }
    expect(strays).toEqual([]);
  });

  it("offers nothing that would send a step again", () => {
    // `retry:` is a TanStack Query option and "retrying" is the approved copy
    // for a Jenkins that cannot be reached; a control called Retry is not.
    const forbidden = [/\bRetry\b/, /\bresend\b/i, /\bsend again\b/i, /\btry again\b/i];
    const strays: string[] = [];
    for (const path of FILES) {
      const text = readFileSync(path, "utf8");
      for (const pattern of forbidden) {
        if (pattern.test(text)) strays.push(`${path}: ${pattern}`);
      }
    }
    expect(strays).toEqual([]);
  });
});
