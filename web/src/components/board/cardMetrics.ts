// Every card on the board is the same size. These are border-box numbers (the
// rendered size), not the content box inside them.
export const CARD_CLASS = "w-[246px] h-[164px] flex-none";

/** What the row 1 status of a step card says, and in which role colour. */
import type { FlowStatus, Step } from "@/api/types";
import type { StatusIconName } from "@/components/ui/StatusIcon";

interface StatusWord {
  glyph: StatusIconName | null;
  /** The warn colour belongs to the glyph alone when the word is not a result. */
  glyphClass: string;
  word: string;
  wordClass: string;
  pulse: boolean;
}

/** A step its flow did not reach before it failed or finished. */
export const notStarted = (step: Step, flowStatus?: FlowStatus) =>
  step.state === "planned" && (flowStatus === "failed" || flowStatus === "finished");

/** `flowStatus`: the step's flow, which decides whether a planned step still waits. */
export function statusOf(step: Step, flowStatus?: FlowStatus): StatusWord {
  const quiet = { glyph: null, glyphClass: "", wordClass: "text-dim", pulse: false } as const;
  if (notStarted(step, flowStatus)) return { ...quiet, word: "not started" };
  switch (step.state) {
    case "SUCCESS":
      return { glyph: "check", glyphClass: "text-ok", word: "SUCCESS", wordClass: "text-ok", pulse: false };
    case "UNSTABLE":
    case "FAILURE":
    case "ABORTED":
      return { glyph: null, glyphClass: "", word: step.state, wordClass: "text-warn", pulse: false };
    case "rejected":
      return { glyph: null, glyphClass: "", word: "not sent", wordClass: "text-warn", pulse: false };
    case "running":
      return { glyph: "running", glyphClass: "text-info", word: "RUNNING", wordClass: "text-info", pulse: true };
    case "queued":
      return { ...quiet, word: "queued" };
    case "submit_pending":
      return { ...quiet, word: "sending…" };
    case "needs_attention":
      return {
        glyph: "alert",
        glyphClass: "text-warn",
        word: "NEEDS ATTENTION",
        wordClass: "text-warn",
        pulse: false,
      };
    case "skipped":
      return { ...quiet, word: "skipped" };
    case "closed":
      // It needed attention, and the flow was ended without linking a build.
      return { ...quiet, word: "not linked" };
    case "planned":
      if (step.held) {
        return { glyph: "alert", glyphClass: "text-warn", word: "needs review", wordClass: "text-dim", pulse: false };
      }
      return { ...quiet, word: "waiting" };
    default:
      // The destructive marker is the icon in the card's header, not part of this word.
      return { ...quiet, word: "waiting" };
  }
}

/** The border is the only thing that distinguishes a card at a glance. */
export function borderOf(step: Step): string {
  if (step.state === "running") return "border-info";
  if (step.state === "needs_attention") return "border-warn";
  return "border-surface";
}
