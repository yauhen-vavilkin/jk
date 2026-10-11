// What a flow's header says about itself. The word is always there beside the
// colour, so the state never depends on the colour alone.
import type { Drift, Flow, SavedFlow, Step } from "@/api/types";
import type { StatusIconName } from "@/components/ui/StatusIcon";
import { elapsed, roundMinutes } from "@/lib/time";

interface HeaderState {
  /** `editing`: the user is still building it. `ready`: built, and waiting to run. */
  glyph: StatusIconName;
  word: string;
  /** The colour of the glyph and of the word. */
  tone: string;
  pulse: boolean;
}

/** The values its saved job asks at launch that are still empty on one step. */
const emptyOf = (step: Step, askedOf: (step: Step) => string[]) =>
  askedOf(step).filter((name) => !(step.run_values[name] ?? "").trim());

/** How many values its saved jobs ask at launch are still empty, across a flow's steps. */
export function unfilledOf(flow: Flow, askedOf: (step: Step) => string[]): number {
  return flow.steps.reduce((count, step) => count + emptyOf(step, askedOf).length, 0);
}

/** The first step, in order, with a value still empty: where filling goes next. */
export function firstUnfilled(flow: Flow, askedOf: (step: Step) => string[]): Step | undefined {
  return flow.steps.find((step) => emptyOf(step, askedOf).length > 0);
}

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** What stands in for Run while values are missing: it opens the next step to fill. */
export const fillLabel = (unfilled: number) => `Fill ${plural(unfilled, "value")}`;

/** Its title: which step it opens. `position` counts from 0, as a step's does. */
export const fillNextTitle = (position: number) =>
  `Opens step ${position + 1}, the first with an empty value`;

/** One step per saved job that Jenkins changed, in step order: each needs a look in Library. */
export function changedJobsOf(flow: Flow, driftOf: (step: Step) => Drift | null): Step[] {
  const seen = new Set<string>();
  return flow.steps.filter((step) => {
    if (seen.has(step.preset_id) || !driftOf(step)) return false;
    seen.add(step.preset_id);
    return true;
  });
}

/** What stands in for Run once every value is filled but a job changed in Jenkins. */
export const reviewJobsLabel = (changed: number) => `Review ${plural(changed, "job")}`;

/** The step the failure came from: the last one that ran before the flow gave up. */
// A skipped step between them is passed over: it never ran, so it cannot have failed.
function failingStep(flow: Flow): Step | undefined {
  const at = flow.failed_at_position;
  if (at === null) return undefined;
  return flow.steps
    .filter((step) => step.position < at)
    .reverse()
    .find((step) => ["FAILURE", "ABORTED", "rejected"].includes(step.state));
}

/**
 * `unfilled`: the values still empty, and `changed`: the saved jobs Jenkins
 * changed, which keep a built draft from being ready.
 */
export function headerStateOf(flow: Flow, unfilled = 0, changed = 0): HeaderState {
  switch (flow.status) {
    case "running":
      return {
        glyph: "running",
        word: "RUNNING",
        tone: "text-info",
        pulse: true,
      };
    case "needs_attention":
      return {
        glyph: "alert",
        word: "NEEDS ATTENTION",
        tone: "text-warn",
        pulse: false,
      };
    case "failed": {
      // Ended from Needs attention: the user closed it, nothing is known to have failed.
      if (flow.steps.some((step) => step.state === "closed")) {
        return {
          glyph: "stopped",
          word: "ENDED",
          tone: "text-dim",
          pulse: false,
        };
      }
      const failing = failingStep(flow);
      return {
        glyph: "alert",
        word: failing
          ? `${failing.state === "ABORTED" ? "ABORTED" : "FAILURE"} at step ${failing.position + 1}`
          : (flow.result ?? "FAILURE"),
        tone: "text-warn",
        pulse: false,
      };
    }
    case "stopped":
      return {
        glyph: "stopped",
        word: "STOPPED",
        tone: "text-dim",
        pulse: false,
      };
    case "finished":
      return flow.result === "SUCCESS" || flow.result === null
        ? { glyph: "check", word: "SUCCESS", tone: "text-ok", pulse: false }
        : {
            glyph: "alert",
            word: flow.result,
            tone: "text-warn",
            pulse: false,
          };
    default:
      // A draft is being built, cannot run yet, or is ready to run, and it says
      // which; the button beside it says what is missing. Whether it is kept as a
      // saved flow is the bookmark button's to say.
      if (flow.editing) {
        return {
          glyph: "editing",
          word: "EDITING",
          tone: "text-text",
          pulse: false,
        };
      }
      return {
        glyph: "ready",
        word: unfilled > 0 || changed > 0 ? "NOT READY" : "READY",
        tone: "text-dim",
        pulse: false,
      };
  }
}

/**
 * What a flow's Save button says. `new`: nothing to compare with -- never kept as
 * a saved flow, or the one it is kept as is not in the list (not read yet, or
 * gone). `changed`: its steps, their conditions or their values are not the saved flow's. `saved`: there is nothing
 * to save. `saving`: on its way.
 */
type SaveState = "new" | "changed" | "saving" | "saved";

/**
 * Save writes each step's job, its condition and the values typed for it, in
 * order, and nothing else: the flow's name is not part of the saved flow.
 */
function sameAsSaved(flow: Flow, saved: SavedFlow): boolean {
  return (
    flow.steps.length === saved.steps.length &&
    flow.steps.every((step, index) => {
      const kept = saved.steps[index];
      return (
        kept !== undefined &&
        step.preset_id === kept.preset_id &&
        step.condition === kept.condition &&
        sameValues(step.run_values, kept.run_values ?? {})
      );
    })
  );
}

/** A blank value is the same as none: the server keeps only what was typed. */
function sameValues(mine: Record<string, string>, kept: Record<string, string>): boolean {
  const typed = (values: Record<string, string>) =>
    Object.entries(values).filter(([, value]) => value.trim() !== "");
  const ours = typed(mine);
  return ours.length === typed(kept).length && ours.every(([name, value]) => kept[name] === value);
}

export function saveStateOf(flow: Flow, keptAs: SavedFlow | null, saving: boolean): SaveState {
  if (saving) return "saving";
  if (!flow.saved_flow_id || !keptAs) return "new";
  return sameAsSaved(flow, keptAs) ? "saved" : "changed";
}

/** The mono line beside the status word: never a second copy of it, never a count. */
export function headerMetaOf(flow: Flow, now: number = Date.now()): string {
  // Everything from a Jenkins estimate says `~`: it is a guess, never progress.
  const left = flow.estimate_ms ? `~${roundMinutes(flow.estimate_ms)}` : "";
  // A draft has nothing else to report: its cards say what it holds.
  if (flow.status === "draft") return left;
  if (flow.status === "stopped") return stoppedMeta(flow);
  const length = runLength(flow, now);
  if (flow.status !== "running") return length;
  const position = (flow.current_position ?? flow.steps.length - 1) + 1;
  return [`step ${position} of ${flow.steps.length}`, length, left && `${left} left`]
    .filter(Boolean)
    .join(" · ");
}

function runLength(flow: Flow, now: number): string {
  if (!flow.started_at) return "";
  const end = flow.finished_at ? new Date(flow.finished_at).getTime() : now;
  return elapsed(end - new Date(flow.started_at).getTime());
}

/** A stopped flow still has a step in Jenkins, or its time ends with its last build. */
function stoppedMeta(flow: Flow): string {
  const going = inFlight(flow);
  if (going) return `${buildOrStep(going)} still ${STILL[going.state]}`;
  const ends = flow.steps.flatMap((step) =>
    step.finished_at ? [new Date(step.finished_at).getTime()] : [],
  );
  if (!flow.started_at || ends.length === 0) return "";
  return elapsed(Math.max(...ends) - new Date(flow.started_at).getTime());
}

/** The states of a step that is in Jenkins, or on its way there, and what each is doing. */
const STILL: Record<string, string> = { submit_pending: "sending", queued: "queued", running: "running" };

const inFlight = (flow: Flow) => flow.steps.find((step) => step.state in STILL);

/** A step by its build once Jenkins gave one, by its number before. */
const buildOrStep = (step: Step) =>
  step.build_number ? `#${step.build_number}` : `step ${step.position + 1}`;

/** The step whose outcome the user still has to decide in Needs attention. */
export const undecidedStep = (flow: Flow) =>
  flow.steps.find((step) => step.state === "needs_attention");

/**
 * What the trash does. A draft never ran, so it is deleted outright; anything
 * that ran is cleared from the board and stays in History; a flow that is going,
 * still has a build in Jenkins, or has a step to resolve, waits.
 */
export function trashAction(flow: Flow): "delete" | "clear" | "disabled" {
  if (flow.status === "draft") return "delete";
  if (undecidedStep(flow)) return "disabled";
  if (flow.status === "finished" || flow.status === "failed") return "clear";
  if (flow.status === "stopped") return inFlight(flow) ? "disabled" : "clear";
  return "disabled";
}

/** Why Remove is off, when it is something other than the flow still going. */
export function removeWaitsFor(flow: Flow): string | null {
  const undecided = undecidedStep(flow);
  if (undecided) return `Resolve step ${undecided.position + 1} first`;
  const going = flow.status === "stopped" ? inFlight(flow) : undefined;
  return going ? `Wait for ${buildOrStep(going)} to end` : null;
}

interface StopChoices {
  /** Stops the flow; the build in Jenkins, if any, keeps running. */
  stop: string;
  /** Also ends the build in Jenkins. Null when there is none, or it was already asked. */
  abort: string | null;
}

/** Each label says exactly what its button does, so the second click is the confirmation. */
export function stopChoices(flow: Flow): StopChoices {
  const current = flow.steps.find((step) => step.position === flow.current_position);
  const build = current?.build_number ? `#${current.build_number}` : null;
  const stop = build ? `Stop after ${build}` : "Stop flow";
  // One stop request per build, ever: once asked, it is not offered again.
  const asked = current?.abort_state !== null && current?.abort_state !== undefined;
  if (!current || asked) return { stop, abort: null };
  if (current.state === "queued") return { stop, abort: "Cancel queued build and stop" };
  if (current.state === "running" && build) return { stop, abort: `Abort ${build} and stop` };
  return { stop, abort: null };
}
