// What a flow is at this moment, in one place. `draft` says it has not started:
// it can be changed at any time, and it runs once its review is confirmed.
import type { Flow, FlowStatus, Step } from "@/api/types";

/** On the board because something may still happen to it. */
const ACTIVE_STATUSES: FlowStatus[] = ["draft", "running", "needs_attention", "stopped"];

export const isActive = (flow: Flow) => ACTIVE_STATUSES.includes(flow.status);

/** A record of a run. It is not changed; it is run again, or opened as a copy. */
export const hasEnded = (flow: Flow) => flow.status === "finished" || flow.status === "failed";

/** A saved job dropped here would land: a draft, or a flow still going. */
export const acceptsAStep = (flow: Flow) => isActive(flow);

/** The steps not sent yet may be changed: in a draft, or a flow still going. A record is not. */
export const canChangeSteps = (flow: Flow) => !hasEnded(flow);

/**
 * Which job a step is, apart from its place: a step's id is its place, so a card
 * or an Undo uses this to notice that another job took that place.
 */
export const stepIdentity = (step: Step) =>
  `${step.preset_id}@${step.added_at}:${JSON.stringify(Object.entries(step.run_values ?? {}).sort())}`;
