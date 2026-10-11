// What a card says about a job: its values, never its parameter names. The
// target comes first on a line of its own, then what is still to be typed at
// launch, then the rest joined by a dot.
import type { Preset, Step, SummaryValue } from "@/api/types";
import { targetText } from "./target";

interface CardValue {
  name: string;
  /** The value as the card prints it: one line, `4 workers` for the worker count. */
  text: string;
  /** Typed at launch rather than saved with the job. */
  perRun: boolean;
}

export interface CardValues {
  /** `example-cluster / example-ns`, or the one of the two that is set; null when neither is. */
  target: string | null;
  /**
   * What stands before "at launch": the names still to be typed when they fit on
   * one line, `CLUSTER · NAMESPACE`, otherwise how many, `5`. Null when none are.
   */
  launch: string | null;
  /** The other values, already split into the lines the card prints. */
  lines: CardValue[][];
  /** Every value sent as `NAME=value`, then `At launch: …`, for the hover title. */
  title: string;
}

/** A value a job sends; `asked` when it is typed at launch. */
interface SentValue {
  name: string;
  value: string;
  asked: boolean;
}

const SHOWN = 4;
const SEPARATOR = " · ";
// A card line holds about this many mono characters; a longer value gets a line
// of its own and is cut there, instead of pushing its neighbours out of sight.
const LINE = 28;
// The words the card prints after the names, which share their line.
const AT_LAUNCH = " at launch";

/** Line breaks and runs of spaces in a value fold to one space on a card. */
export function oneLine(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function textOf(item: SummaryValue): string {
  const value = oneLine(item.value);
  // The only name-aware rule left: a bare number says nothing on its own.
  if (item.name === "NUMBER_OF_WORKERS" && value) {
    return `${value} ${value === "1" ? "worker" : "workers"}`;
  }
  return value;
}

/**
 * `launch`: the values asked at launch that nothing was typed for yet. They are
 * named once, on a line of their own, never cut: a count when the names do not fit.
 * `sent`: every value the job sends, for the hover title; the summary by default.
 */
export function cardValues(
  summary: SummaryValue[],
  launch: string[] = [],
  sent: SentValue[] = summary.map((item) => ({ name: item.name, value: item.value, asked: item.per_run })),
): CardValues {
  const waiting = new Set(launch);
  const shown = summary.filter((item) => !waiting.has(item.name)).slice(0, SHOWN);
  const find = (name: string) => oneLine(shown.find((item) => item.name === name)?.value);
  const cluster = find("CLUSTER");
  const namespace = find("NAMESPACE");

  const lines: CardValue[][] = [];
  let width = 0;
  for (const item of shown) {
    if (item.name === "CLUSTER" || item.name === "NAMESPACE") continue;
    const text = textOf(item);
    if (!text) continue;
    const value = { name: item.name, text, perRun: item.per_run };
    const current = lines[lines.length - 1];
    if (current && width + SEPARATOR.length + text.length <= LINE) {
      current.push(value);
      width += SEPARATOR.length + text.length;
    } else {
      lines.push([value]);
      width = text.length;
    }
  }

  const names = launch.join(SEPARATOR);
  return {
    target: cluster || namespace ? targetText(cluster, namespace) : null,
    launch:
      launch.length === 0 ? null : names.length + AT_LAUNCH.length <= LINE ? names : String(launch.length),
    lines,
    title: [
      ...sent.filter((item) => !waiting.has(item.name)).map((item) => `${item.name}=${item.value}`),
      ...(launch.length > 0 ? [`At launch: ${launch.join(", ")}`] : []),
    ].join("\n"),
  };
}

/** What a saved job sends: its fixed values, and each asked one with what was typed for it. */
function presetValues(preset: Preset, runValues: Record<string, string> = {}): SentValue[] {
  return Object.entries(preset.params)
    .filter(([, setting]) => setting.mode !== "default")
    .map(([name, setting]) =>
      setting.mode === "ask"
        ? { name, value: runValues[name] ?? "", asked: true }
        : { name, value: setting.value ?? "", asked: false },
    );
}

/**
 * What a step sends, or sent: the body fixed at review once there is one, else
 * its saved job with the values typed so far. Without the saved job, the summary.
 */
export function stepValues(step: Step, preset?: Preset, asked: string[] = []): SentValue[] {
  const marked = new Set([
    ...asked,
    ...step.summary.filter((item) => item.per_run).map((item) => item.name),
  ]);
  if (step.frozen_params) {
    return Object.entries(step.frozen_params).map(([name, value]) => ({
      name,
      value,
      asked: marked.has(name),
    }));
  }
  if (preset) return presetValues(preset, step.run_values);
  const known = step.summary.map((item) => ({ name: item.name, value: item.value, asked: item.per_run }));
  const missing = asked
    .filter((name) => !known.some((item) => item.name === name))
    .map((name) => ({ name, value: step.run_values[name] ?? "", asked: true }));
  return [...known, ...missing];
}

/** A saved job's card: what it sends, with every value asked at launch still to be typed. */
export function presetCardValues(preset: Preset): CardValues {
  const sent = presetValues(preset);
  const summary = preset.summary_params.flatMap((name) => {
    const item = sent.find((value) => value.name === name);
    return item ? [{ name, value: item.value, per_run: item.asked }] : [];
  });
  return cardValues(
    summary,
    sent.filter((item) => item.asked).map((item) => item.name),
    sent,
  );
}

export { SEPARATOR };
