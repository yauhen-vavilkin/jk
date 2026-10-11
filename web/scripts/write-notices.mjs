// Keep the licenses of installed production dependencies with the built panel.
// Include transitive dependencies too; a lockfile update updates the notices.
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = new URL("../", import.meta.url);
const lock = JSON.parse(readFileSync(new URL("package-lock.json", root), "utf8"));
const sections = ["JK frontend — third-party notices\nFonts have separate licenses in fonts/."];

for (const [path, metadata] of Object.entries(lock.packages).sort()) {
  if (!path || metadata.dev) continue;
  const directory = new URL(`${path}/`, root);
  const files = readdirSync(directory).filter((name) => /^(licen[cs]e|copying|notice)(\.|$)/i.test(name)).sort();
  if (!files.length) throw new Error(`Missing license for ${path}`);
  sections.push(`${path.replace(/^node_modules\//, "")} ${metadata.version}\n${files.map((name) => readFileSync(new URL(name, directory), "utf8").trim()).join("\n\n")}`);
}

writeFileSync(fileURLToPath(new URL("dist/THIRD_PARTY_NOTICES.txt", root)), sections.join("\n\n---\n\n") + "\n");
