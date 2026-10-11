// A condition answers one question: what happens to this step when the step
// before it did not succeed? The label is a sentence that names the outcome, the
// icon and the colour say the same thing at a glance, and the hover title is the
// label word for word, so one hover teaches the icon.
import { ArrowRight, Check, ChevronsRight, X, type LucideIcon } from "lucide-react";

import type { Condition } from "@/api/types";

const DEFAULT_CONDITION: Condition = "unless_failure";

export const CONDITION_LABELS: Record<Condition, string> = {
  unless_failure: "End the flow if the step before failed",
  after_success: "Skip unless the step before succeeded",
  always: "Start even if the step before failed",
  after_failure: "Skip unless the step before failed",
};

export const CONDITION_ICON: Record<Condition, LucideIcon> = {
  unless_failure: ArrowRight,
  after_success: Check,
  always: ChevronsRight,
  after_failure: X,
};

/** The icon's colour; the default is the quiet one. */
export const CONDITION_COLOUR: Record<Condition, { text: string }> = {
  unless_failure: { text: "text-dim" },
  after_success: { text: "text-ok" },
  always: { text: "text-accent" },
  after_failure: { text: "text-warn" },
};

export const CONDITION_ORDER: Condition[] = [
  "unless_failure",
  "after_success",
  "always",
  "after_failure",
];

/**
 * The line Review prints beside a step, the default included: a cleanup step
 * after it reads "ends the flow if step 2 failed". Nothing for the default on
 * the first step, which has no step before it.
 */
export function conditionLine(condition: Condition, previousPosition: number): string | null {
  if (condition === DEFAULT_CONDITION && previousPosition < 0) return null;
  const step = previousPosition < 0 ? "the step before" : `step ${previousPosition + 1}`;
  if (condition === "after_success") return `skipped unless ${step} succeeded`;
  if (condition === "always") return `even if ${step} failed`;
  if (condition === "after_failure") return `skipped unless ${step} failed`;
  return `ends the flow if ${step} failed`;
}
