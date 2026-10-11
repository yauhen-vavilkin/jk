// What the saved-job editor holds, whether it differs from the saved job, and
// how the user's edits are carried onto a newer copy of that saved job.
import type { ParamDefinition, Preset } from "@/api/types";
import { holdsPlaceholder, suggestsDestructive, type Draft } from "./paramRows";

export interface EditorValue {
  name: string;
  operation: string;
  destructive: boolean;
  params: Draft;
}

export function seedFrom(
  preset: Preset | null,
  jobPath: string,
  definitions: ParamDefinition[],
): EditorValue {
  if (preset) {
    return {
      name: preset.name,
      operation: preset.operation,
      destructive: preset.destructive,
      params: { ...preset.params },
    };
  }
  const params: Draft = {};
  for (const definition of definitions) {
    // Jenkins' placeholder is not a value anyone sent, so it is never the last one.
    const declared = definition.default;
    const last = declared !== null && holdsPlaceholder(definition, declared) ? null : declared;
    params[definition.name] = { mode: "default", value: null, last_value: last };
  }
  return {
    name: "",
    operation: "",
    destructive: suggestsDestructive(jobPath),
    params,
  };
}

type Setting = Draft[string];

/** What the user sets on a parameter. `last_value` is JK's own note of what went last. */
function sameSetting(a: Setting | undefined, b: Setting | undefined): boolean {
  if (a === undefined || b === undefined) return a === b;
  return a.mode === b.mode && (a.value ?? "") === (b.value ?? "");
}

/** Nothing to save: the same name, operation, flag, and parameters as the user set them. */
export function sameEditorValue(a: EditorValue, b: EditorValue): boolean {
  if (a.name !== b.name || a.operation !== b.operation || a.destructive !== b.destructive) {
    return false;
  }
  const names = new Set([...Object.keys(a.params), ...Object.keys(b.params)]);
  return [...names].every((name) => sameSetting(a.params[name], b.params[name]));
}

/** Everything the saved job says, in an order of its own, so a new copy of the same says so. */
export function signatureOf(value: EditorValue): string {
  const params = Object.keys(value.params)
    .sort()
    .map((name) => {
      const setting = value.params[name];
      return [name, setting?.mode, setting?.value ?? "", setting?.last_value ?? ""];
    });
  return JSON.stringify([value.name, value.operation, value.destructive, params]);
}

/**
 * The user's edits carried onto a newer copy of the saved job -- saved in another
 * tab, repaired, or read again. What they changed stays theirs; what they did not
 * follows the newer copy; a parameter they removed stays removed. A parameter the
 * newer copy removed goes, even one the user changed: a repair removes what
 * Jenkins no longer defines, and the server would refuse to save it. `last_value`
 * always comes from the newer copy: JK keeps it, not the user.
 */
export function rebase(base: EditorValue, mine: EditorValue, theirs: EditorValue): EditorValue {
  const params: Draft = {};
  const names = new Set([
    ...Object.keys(theirs.params),
    ...Object.keys(mine.params),
    ...Object.keys(base.params),
  ]);
  for (const name of names) {
    if (name in base.params && !(name in theirs.params)) continue;
    const touched = !sameSetting(mine.params[name], base.params[name]);
    const kept = touched ? mine.params[name] : theirs.params[name];
    if (kept === undefined) continue;
    const newer = theirs.params[name];
    params[name] = touched && newer ? { ...kept, last_value: newer.last_value } : kept;
  }
  return {
    name: mine.name !== base.name ? mine.name : theirs.name,
    operation: mine.operation !== base.operation ? mine.operation : theirs.operation,
    destructive: mine.destructive !== base.destructive ? mine.destructive : theirs.destructive,
    params,
  };
}
