// What the panel reads of the server's JSON. The server owns the contract
// (src/jk/web/schemas.py); extend this file by adding, never by renaming.

export type Condition = "unless_failure" | "after_success" | "always" | "after_failure";
export type ParamMode = "fixed" | "ask" | "default";
export type FlowStatus = "draft" | "running" | "needs_attention" | "stopped" | "finished" | "failed";
type StepState =
  | "planned"
  | "submit_pending"
  | "queued"
  | "running"
  | "SUCCESS"
  | "UNSTABLE"
  | "FAILURE"
  | "ABORTED"
  | "rejected"
  | "needs_attention"
  | "skipped"
  /** Needed attention, and the user ended the flow without linking a build ("not linked"). */
  | "closed";
export type Result = "SUCCESS" | "UNSTABLE" | "FAILURE" | "ABORTED";

export interface ApiErrorBody {
  error: { code: string; message: string };
}

export interface ParamSetting {
  mode: ParamMode;
  value: string | null;
  last_value: string | null;
}

export interface ParamDefinition {
  name: string;
  type: string;
  default: string | null;
  choices: string[] | null;
}

interface DriftItem {
  name: string;
  default: string | null;
  had: string | null;
  reason: string | null;
}

export interface Drift {
  added: DriftItem[];
  removed: DriftItem[];
  changed: DriftItem[];
  seen_at: string;
}

export interface Preset {
  id: string;
  name: string;
  operation: string;
  job_path: string;
  job_url: string;
  destructive: boolean;
  summary_params: string[];
  params: Record<string, ParamSetting>;
  definitions: ParamDefinition[];
  drift: Drift | null;
}

export interface SavedFlowStep {
  preset_id: string;
  condition: Condition;
  /** The values typed for what its saved job asks at launch. */
  run_values: Record<string, string>;
}

export interface SavedFlow {
  id: string;
  name: string;
  steps: SavedFlowStep[];
  /** Jenkins' guess for the whole flow; null unless every step's job has one. */
  estimate_ms: number | null;
}

export interface JenkinsJob {
  job_path: string;
  name: string;
  folder: string;
  param_count: number;
  run_count: number;
  url: string;
}

export interface JenkinsStatus {
  url: string;
  reachable: boolean;
  since: string | null;
  auth_ok: boolean;
}

export interface SummaryValue {
  name: string;
  value: string;
  per_run: boolean;
}

export interface Step {
  id: string;
  position: number;
  preset_id: string;
  preset_name: string;
  job_url: string;
  destructive: boolean;
  condition: Condition;
  summary: SummaryValue[];
  run_values: Record<string, string>;
  frozen_params: Record<string, string> | null;
  state: StepState;
  build_number: number | null;
  build_url: string | null;
  sent_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  elapsed_ms: number | null;
  estimate_ms: number | null;
  added_at: string;
  added_while_running: boolean;
  abort_state: "requested" | "accepted" | "failed" | null;
  note: string | null;
  /** Added after the start, or held after a restart or a Jenkins change: waits for a review. */
  held: boolean;
}

/**
 * Another flow that is, or may be, running on a CLUSTER and NAMESPACE of this one,
 * named once by its most urgent matching step. `state` says which: submit_pending,
 * queued or running (a build is, or is about to be, in Jenkins), needs_attention
 * (one may be), or planned (a later step of a flow that is running). Drafts and
 * steps a stopped flow never sent are not listed.
 */
export interface SameTarget {
  flow_id: string;
  flow_name: string;
  position: number;
  state: StepState;
  cluster: string;
  namespace: string;
  /** The build, once Jenkins gave one. */
  build_number: number | null;
}

export interface Flow {
  id: string;
  name: string;
  status: FlowStatus;
  steps: Step[];
  current_position: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
  cleared: boolean;
  failed_at_position: number | null;
  result: Result | null;
  /** The saved flow this flow is kept as, if it is. */
  saved_flow_id: string | null;
  /** Kept at the top of the board, and on it, until it is taken off. */
  pinned: boolean;
  /** The user is still building it: it can be changed, but not run. Only a draft is. */
  editing: boolean;
  /** What is left to run, from Jenkins' estimates; null unless every step left has one. */
  estimate_ms: number | null;
}

interface ReviewIssue {
  step_id: string;
  preset_name: string;
  parameter: string | null;
  failure: string;
  action: string;
  /** The saved job to open in Library; set when Jenkins changed it ("Review it in Library"). */
  preset_id: string | null;
}

/** A parameter JK leaves to Jenkins, and what Jenkins will use for it. */
export interface JenkinsDefault {
  name: string;
  /** null: Jenkins has no default ("no default"). */
  default: string | null;
}

export interface ReviewStep {
  step_id: string;
  position: number;
  preset_name: string;
  job_path: string;
  job_url: string;
  destructive: boolean;
  condition: Condition;
  sent: SummaryValue[];
  defaults_left: number;
  /** Every parameter Jenkins defines that the step neither sends nor asks, in Jenkins' order. */
  defaults: JenkinsDefault[];
}

export interface Review {
  ok: boolean;
  issues: ReviewIssue[];
  steps: ReviewStep[];
  same_target: SameTarget[];
  missing_run_values: { step_id: string; names: string[] }[];
  /** Sent back with the start, confirm or resume; the server refuses anything else. */
  review_token: string;
}

/** What a review is for: a draft's start, steps added after it, or a resume. */
export type ReviewScope =
  | { kind: "start" }
  | { kind: "held" }
  | { kind: "resume"; fromPosition?: number };

export interface AttentionCandidate {
  number: number;
  time: string;
  /** "RUNNING" while the build runs, otherwise its result, or "unknown". */
  state: string;
  detail: string;
  url: string;
}

export interface Attention {
  reason: string;
  never_again_text: string;
  job_path: string;
  sent_at: string | null;
  next_build_number: number | null;
  candidates: AttentionCandidate[];
  agreement_text: string | null;
  lookup_error: string | null;
}

/** One step that still uses a saved job: its flow, and where in it (0-based). */
export interface PresetUse {
  flow_id: string;
  flow_name: string;
  position: number;
}

export interface PresetUsage {
  /** Each step that still uses the saved job, in the order the flows were made. */
  steps: PresetUse[];
}

/** What a Jenkins change becomes when accepted: all defaults, or a decision per parameter. */
export interface RepairRequest {
  decisions?: Record<string, "default" | "fixed" | "ask" | "drop">;
  /** The value of each parameter decided as fixed (or asked, as its last value). */
  values?: Record<string, string>;
}

export interface StepCreate {
  preset_id: string;
}
