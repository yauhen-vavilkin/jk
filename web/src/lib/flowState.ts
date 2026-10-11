// What a flow is at this moment, in one place. `draft` says it has not started,
// `editing` says the user is still building it. A draft that is not being
// edited is ready: it runs, and it does not change.
import type { Flow, FlowStatus } from "@/api/types";

/** On the board because something may still happen to it. */
const ACTIVE_STATUSES: FlowStatus[] = ["draft", "running", "needs_attention", "stopped"];

export const isActive = (flow: Flow) => ACTIVE_STATUSES.includes(flow.status);

/** A record of a run. It is not changed; it is run again, or opened as a copy. */
export const hasEnded = (flow: Flow) => flow.status === "finished" || flow.status === "failed";

/** A saved job dropped here would land. A ready draft is closed; a running flow is not. */
export const acceptsAStep = (flow: Flow) => (flow.status === "draft" ? flow.editing : isActive(flow));

/** The steps may be changed: a draft being built, or a flow still going. A record is not. */
export const canChangeSteps = (flow: Flow) =>
  flow.status === "draft" ? flow.editing : !hasEnded(flow);
