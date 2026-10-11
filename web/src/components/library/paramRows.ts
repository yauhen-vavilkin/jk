// Which parameters the table shows, and in which order: the order Jenkins
// declares them in. A row never moves when what is sent for it changes, so the
// one being edited stays under the cursor; what Jenkins removed comes last.
import type { ParamDefinition, ParamMode, ParamSetting, Preset, RepairRequest } from "@/api/types";

type RowKind = "sent" | "added" | "removed" | "default";

export interface ParamRow {
  name: string;
  kind: RowKind;
  mode: ParamMode;
  value: string;
  lastValue: string | null;
  definition: ParamDefinition | null;
  isPassword: boolean;
}

export type Draft = Record<string, ParamSetting>;

export function rowsOf(preset: Preset, draft: Draft): ParamRow[] {
  const definitions = new Map(preset.definitions.map((item) => [item.name, item]));
  const declared = preset.definitions.map((item) => item.name);
  const added = new Set((preset.drift?.added ?? []).map((item) => item.name));
  const removed = new Set((preset.drift?.removed ?? []).map((item) => item.name));
  // What the saved job held for a parameter Jenkins removed, as the drift recorded it.
  const had = new Map((preset.drift?.removed ?? []).map((item) => [item.name, item.had]));
  // A parameter Jenkins added is not in the saved definitions until the change is
  // accepted; the drift says what Jenkins defaults it to, and that is enough to set it.
  for (const item of preset.drift?.added ?? []) {
    if (!definitions.has(item.name)) {
      definitions.set(item.name, {
        name: item.name,
        type: "",
        default: item.default,
        choices: null,
      });
    }
  }

  const names = new Set([...Object.keys(draft), ...definitions.keys(), ...removed]);
  const rows: ParamRow[] = [];

  for (const name of names) {
    const setting = draft[name] ?? { mode: "default" as ParamMode, value: null, last_value: null };
    const definition = definitions.get(name) ?? null;
    rows.push({
      name,
      kind: removed.has(name)
        ? "removed"
        : added.has(name)
          ? "added"
          : setting.mode === "default"
            ? "default"
            : "sent",
      mode: setting.mode,
      value: removed.has(name) ? (had.get(name) ?? setting.value ?? "") : (setting.value ?? ""),
      lastValue: setting.last_value,
      definition,
      isPassword: definition?.type === "PasswordParameterDefinition",
    });
  }

  const declaredAt = (name: string) => {
    const index = declared.indexOf(name);
    return index === -1 ? Number.MAX_SAFE_INTEGER : index;
  };
  return rows.sort(
    (left, right) =>
      declaredAt(left.name) - declaredAt(right.name) ||
      left.name.localeCompare(right.name),
  );
}

export const PASSWORD_BLOCKER = "A password parameter has no value.";
/** What Jenkins answers for an Active Choices parameter it cannot compute yet. */
const ERROR_PLACEHOLDER = "error";
export const placeholderBlocker = (name: string) =>
  `${name} still holds Jenkins' error placeholder. Choose its value.`;
export const valueNeededBlocker = (name: string) =>
  `${name} has no Jenkins default. Give it a value, or ask for one at launch.`;

/** A value the user typed that is Jenkins' placeholder, not a value. */
export function holdsPlaceholder(
  definition: ParamDefinition | null | undefined,
  value: string,
): boolean {
  return definition?.type === "CascadeChoiceParameter" && value.trim() === ERROR_PLACEHOLDER;
}

/** What a row going to `fixed` starts from: the last value, else the Jenkins default, never the placeholder. */
export function fixedStart(row: ParamRow): string {
  for (const candidate of [row.lastValue, row.definition?.default]) {
    if (candidate && !holdsPlaceholder(row.definition, candidate)) return candidate;
  }
  return "";
}

/**
 * An Active Choices parameter whose value Jenkins cannot supply: it answers the
 * `error` placeholder, or nothing at all. Leaving it out does not fall back on a
 * Jenkins default, because there is none — the build runs without the value.
 */
export function needsAValue(definition: ParamDefinition | null | undefined): boolean {
  if (definition?.type !== "CascadeChoiceParameter") return false;
  const declared = (definition.default ?? "").trim();
  return declared === "" || declared === ERROR_PLACEHOLDER;
}

export const DRIFT_BLOCKER = "Accept the Jenkins change above first.";

/** Why Save is off, or nothing at all. */
export function saveBlocker(preset: Preset | null, draft: Draft, name: string): string | null {
  if (!name.trim()) return "A saved job needs a name.";
  if (preset?.drift) return DRIFT_BLOCKER;
  const definitions = new Map((preset?.definitions ?? []).map((item) => [item.name, item]));
  for (const [key, setting] of Object.entries(draft)) {
    const type = definitions.get(key)?.type;
    const value = setting.value ?? "";
    if (type === "PasswordParameterDefinition" && setting.mode === "fixed" && !value.trim()) {
      return PASSWORD_BLOCKER;
    }
    if (setting.mode === "fixed" && holdsPlaceholder(definitions.get(key), value)) {
      return placeholderBlocker(key);
    }
  }
  for (const definition of preset?.definitions ?? []) {
    if (!needsAValue(definition)) continue;
    const setting = draft[definition.name];
    const answered =
      setting?.mode === "ask" ||
      (setting?.mode === "fixed" && (setting.value ?? "").trim() !== "");
    if (!answered) return valueNeededBlocker(definition.name);
  }
  return null;
}

/**
 * "Accept as shown": each parameter Jenkins added is stored as its row is set, and
 * what Jenkins removed goes. A row left alone keeps the Jenkins default.
 */
export function repairRequest(rows: ParamRow[]): RepairRequest {
  const decisions: NonNullable<RepairRequest["decisions"]> = {};
  const values: Record<string, string> = {};
  for (const row of rows) {
    if (row.kind !== "added") continue;
    decisions[row.name] = row.mode;
    if (row.mode === "fixed") values[row.name] = row.value;
  }
  return { decisions, values };
}

/** JK suggests the flag; the user sets it. Only ever for a saved job that is new. */
export function suggestsDestructive(jobPath: string): boolean {
  return /delete|createNamespace|destroy|teardown/i.test(jobPath);
}
