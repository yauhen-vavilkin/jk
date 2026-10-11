// Exactly what will be sent, checked against Jenkins, with every destructive
// step named beside its target. The server sends only what a review showed: the
// button hands back the review's token, and anything that changed since is
// refused. The same modal reviews a draft, steps added to a started flow, and
// what a resume would send.
import { ExternalLink } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { Flow, Review, ReviewScope, ReviewStep, SameTarget, SummaryValue } from "@/api/types";
import { ApiError, UNREACHABLE } from "@/api/client";
import { useReview, type RunValues } from "@/api/queries";
import { CONDITION_COLOUR, CONDITION_ICON, conditionLine } from "@/lib/conditions";
import { JENKINS_DEFAULTS, targetGroups, targetText } from "@/lib/target";
import { PrimaryButton, QuietButton } from "@/components/ui/primitives";
import { DestructiveMark } from "@/components/ui/DestructiveMark";
import Modal from "./Modal";
import StatusIcon, { type StatusIconName } from "@/components/ui/StatusIcon";

export const CANT_RUN = "Can't run yet. Nothing was sent.";
const NOTHING_SENT = "Nothing was sent.";

/** The window's words. Steps added to a started flow are named when there is one. */
export function reviewWords(
  kind: ReviewScope["kind"],
  positions: number[],
): { title: string; button: string; label: string; discard: string } {
  if (kind === "start") {
    return { title: "Run", button: "Run flow", label: "Review and run", discard: "Cancel" };
  }
  if (kind === "resume") {
    return { title: "Resume", button: "Resume flow", label: "Resume", discard: "Cancel" };
  }
  const which = positions.length === 1 ? `step ${positions[0]! + 1}` : "steps";
  return {
    title: `Review added ${which}`,
    button: `Confirm ${which}`,
    label: `Review added ${which}`,
    discard: `Remove ${which}`,
  };
}

/** Another flow on the same target: running, maybe running, or getting there later. */
export function sameTargetLine(other: SameTarget): {
  icon: StatusIconName;
  colour: string;
  before: string;
  after: string;
} {
  const step = other.position + 1;
  if (other.state === "needs_attention") {
    const after = ` (step ${step} needs attention).`;
    return { icon: "alert", colour: "text-warn", before: " may be running on ", after };
  }
  if (other.state === "planned") {
    return { icon: "ready", colour: "text-dim", before: " reaches ", after: ` at step ${step}.` };
  }
  const build = other.build_number === null ? "" : `, #${other.build_number}`;
  const after = ` (step ${step}${build}).`;
  return { icon: "running", colour: "text-info", before: " is running on ", after };
}

/** Why there is no review: JK's own reason, or that JK could not be reached. */
export function errorText(error: unknown): string {
  const reason = error instanceof ApiError && error.message ? error.message : UNREACHABLE;
  return reason.endsWith(NOTHING_SENT) ? reason : `${reason} ${NOTHING_SENT}`;
}

export default function ReviewRun({
  flow,
  scope,
  onClose,
  onRun,
  onDiscard,
}: {
  flow: Flow;
  scope: ReviewScope;
  onClose: () => void | Promise<void>;
  onRun: (runValues: RunValues, token: string) => void;
  /** Opened by a drop on a started flow: takes the added steps back in place of Cancel. */
  onDiscard?: () => void;
}) {
  const review = useReview(flow.id, scope);
  const [closing, setClosing] = useState(false);
  const [closeError, setCloseError] = useState<string | null>(null);
  const close = async () => {
    if (closing) return;
    setClosing(true);
    setCloseError(null);
    try {
      await onClose();
    } catch {
      setCloseError("Could not cancel the copy. Nothing was sent. Connect to JK and cancel again.");
    } finally {
      setClosing(false);
    }
  };
  // Seeded once: a change elsewhere in the flow must not undo what was typed here.
  const [values, setValues] = useState<RunValues>(() =>
    Object.fromEntries(flow.steps.map((step) => [step.id, { ...step.run_values }])),
  );
  const [openDefaults, setOpenDefaults] = useState<Set<string>>(new Set());

  const data = review.data;
  const steps = data?.steps ?? [];
  const words = reviewWords(scope.kind, steps.map((step) => step.position));

  // What is still empty now: a value typed here counts at once.
  const missing = (data?.missing_run_values ?? [])
    .map((item) => ({
      ...item,
      names: item.names.filter((name) => !(values[item.step_id]?.[name] ?? "").trim()),
    }))
    .filter((item) => item.names.length > 0);
  const ready = Boolean(data?.ok) && steps.length > 0 && missing.length === 0;

  // What a step sends, with a value typed here in place of the saved one.
  const shown = (step: ReviewStep, item: SummaryValue) =>
    item.per_run ? (values[step.step_id]?.[item.name] ?? item.value) : item.value;
  const valueOf = (step: ReviewStep, name: string) => {
    const item = step.sent.find((entry) => entry.name === name);
    return item ? shown(step, item) : "";
  };
  const destructive = targetGroups(
    steps
      .filter((step) => step.destructive)
      .map((step) => ({
        position: step.position,
        cluster: valueOf(step, "CLUSTER"),
        namespace: valueOf(step, "NAMESPACE"),
      })),
  );
  const sameTarget = data?.same_target ?? [];
  const firstIssue = data?.issues[0];

  const toggleDefaults = (stepId: string) =>
    setOpenDefaults((current) => {
      const next = new Set(current);
      if (!next.delete(stepId)) next.add(stepId);
      return next;
    });

  // Only a step with a value asked at launch carries values back.
  const answered = (): RunValues =>
    Object.fromEntries(
      steps
        .filter((step) => step.sent.some((item) => item.per_run))
        .map((step) => [step.step_id, values[step.step_id] ?? {}]),
    );

  return (
    <Modal width={822} top={40} onClose={close} locked={closing} label={words.label}>
      <div className="flex flex-col gap-1.5 px-7 pb-4 pt-[22px]">
        <div className="flex flex-wrap items-baseline gap-x-3.5 gap-y-1">
          <span className="text-[20px] font-semibold">{words.title}</span>
          <span className="text-key">{flow.name}</span>
          <span className="flex flex-1 whitespace-nowrap font-mono text-[13px]">
            <ValidationStatus review={data} loading={review.isPending} error={review.error} />
          </span>
        </div>
        {data && !data.ok && (
          <div className="flex flex-col gap-0.5 pt-1 font-mono text-[13px] text-dim">
            {data.issues.map((issue, index) => (
              <span key={`${issue.step_id}-${issue.parameter ?? index}`}>
                {issue.preset_name}
                {issue.parameter ? ` ${issue.parameter}` : ""}: {issue.failure}
              </span>
            ))}
            {firstIssue && (
              <span className="pt-1 font-sans text-[14px] text-key">
                {firstIssue.preset_id ? (
                  <Link to={`/library/${firstIssue.preset_id}`} className="underline underline-offset-2">
                    {firstIssue.action}
                  </Link>
                ) : (
                  firstIssue.action
                )}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-col overflow-auto px-7">
        {steps.map((step) => {
          // Step 1 has no step before it, so it has no condition.
          const condition = step.position > 0 ? conditionLine(step.condition, step.position - 1) : null;
          const open = openDefaults.has(step.step_id);
          return (
            <div
              key={step.step_id}
              className="grid grid-cols-[36px_minmax(0,1fr)] gap-x-3 gap-y-0 border-t border-hairline py-3.5"
            >
              <span className="pt-0.5 font-mono text-[13px] text-dim">{step.position + 1}</span>
              <div className="flex min-w-0 flex-col gap-1.5">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="font-medium">{step.preset_name}</span>
                  <a
                    href={step.job_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex min-w-0 items-center gap-1.5 font-mono text-[13px]"
                  >
                    {step.job_path} <ExternalLink size={13} aria-hidden className="flex-none" />
                  </a>
                  <span className="ml-auto inline-flex items-center gap-3">
                    {condition && <ConditionLine condition={step.condition} line={condition} />}
                    {step.destructive && <DestructiveMark />}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-x-6 font-mono text-[13px] leading-[1.7] text-text">
                  {step.sent.map((item) => (
                    <div key={item.name} className="flex items-center gap-2.5">
                      <span className="w-[160px] flex-none text-dim">{item.name}</span>
                      {item.per_run ? (
                        <PerRunValue
                          name={item.name}
                          value={shown(step, item)}
                          onChange={(next) =>
                            setValues((current) => ({
                              ...current,
                              [step.step_id]: {
                                ...current[step.step_id],
                                [item.name]: next,
                              },
                            }))
                          }
                        />
                      ) : (
                        <span className="[overflow-wrap:anywhere]">
                          {item.value || <span className="text-dim">empty</span>}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
                {step.defaults.length > 0 ? (
                  <button
                    type="button"
                    aria-expanded={open}
                    onClick={() => toggleDefaults(step.step_id)}
                    className="self-start text-[13px] text-dim hover:text-text"
                  >
                    {open ? "−" : "+"} {step.defaults_left} on Jenkins defaults
                  </button>
                ) : (
                  // Jenkins did not answer: the count is from the saved job, with nothing to list.
                  step.defaults_left > 0 && (
                    <span className="text-[13px] text-dim">+ {step.defaults_left} on Jenkins defaults</span>
                  )
                )}
                {open && (
                  <div className="grid grid-cols-2 gap-x-6 font-mono text-[13px] leading-[1.7] text-dim">
                    {step.defaults.map((item) => (
                      <div key={item.name} className="flex items-center gap-2.5">
                        <span className="w-[160px] flex-none">{item.name}</span>
                        <span className="[overflow-wrap:anywhere]">
                          {item.default === null ? "no default" : item.default || "empty"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
        {/* In the scrolling part: with many lines, a fixed footer would leave the steps no room. */}
        {(destructive.length > 0 || sameTarget.length > 0) && (
          <div className="flex flex-col gap-3 border-t border-hairline py-4">
            {destructive.map((group) => (
              <div key={group.steps} className="flex items-baseline gap-2.5">
                <DestructiveMark className="flex-none" />
                <span>
                  {group.steps} ·{" "}
                  {/* Left to Jenkins is words, not a target name. */}
                  <span className={group.target === JENKINS_DEFAULTS ? "text-dim" : "font-mono text-[13px]"}>
                    {group.target}
                  </span>
                </span>
              </div>
            ))}
            {sameTarget.map((other) => {
              const line = sameTargetLine(other);
              return (
                <div key={other.flow_id} className="flex items-center gap-2.5">
                  <StatusIcon name={line.icon} className={line.colour} />
                  <span>
                    <span className="font-medium">{other.flow_name}</span>
                    {line.before}
                    <span className="font-mono text-[13px]">{targetText(other.cluster, other.namespace)}</span>
                    {line.after}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {closeError && <div role="alert" className="px-7 pt-4 text-[14px] text-warn">{closeError}</div>}
      <div className="flex items-center gap-5 px-7 pb-[22px] pt-4">
        {missing.length > 0 && (
          // Run is off until every value asked at launch is typed: say which.
          <span className="min-w-0 text-[14px] text-accent">{missingText(missing, steps)}</span>
        )}
        <div className="flex-1" />
        <QuietButton
          disabled={closing}
          onClick={() => {
            onDiscard?.();
            void close();
          }}
        >
          {onDiscard ? words.discard : "Cancel"}
        </QuietButton>
        <PrimaryButton
          disabled={!ready || closing}
          onClick={() => ready && data && onRun(answered(), data.review_token)}
        >
          {words.button}
        </PrimaryButton>
      </div>
    </Modal>
  );
}

/** Which values are still empty, step by step: `Fill NAMESPACE in step 2`. */
export function missingText(
  missing: { step_id: string; names: string[] }[],
  steps: { step_id: string; position: number }[],
): string {
  const parts = missing.map((item) => {
    const position = steps.find((step) => step.step_id === item.step_id)?.position;
    const where = position === undefined ? "" : ` in step ${position + 1}`;
    return `${item.names.join(", ")}${where}`;
  });
  return `Fill ${parts.join("; ")}`;
}

/** A value for this run: always a field, so it is plain that it can be typed here. */
function PerRunValue({
  name,
  value,
  onChange,
}: {
  name: string;
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <input
      value={value}
      aria-label={`Value for ${name}`}
      onChange={(event) => onChange(event.target.value)}
      // Enter never starts a flow: it only leaves the field.
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === "Escape") event.currentTarget.blur();
      }}
      className="h-7 min-w-0 flex-1 rounded-[5px] border border-dim bg-transparent px-2 text-text outline-hidden focus:border-accent"
    />
  );
}

function ValidationStatus({
  review,
  loading,
  error,
}: {
  review: Review | undefined;
  loading: boolean;
  error: unknown;
}) {
  if (loading) {
    return (
      <span className="ml-auto text-info">
        <StatusIcon name="running" size={14} className="jk-pulse" /> Checking…
      </span>
    );
  }
  if (error || !review) {
    return (
      <span className="ml-auto text-warn">
        <StatusIcon name="alert" size={14} /> {errorText(error)}
      </span>
    );
  }
  if (review.ok) {
    return (
      <span className="ml-auto text-ok">
        <StatusIcon name="check" size={14} /> matches Jenkins
      </span>
    );
  }
  return (
    <span className="ml-auto text-warn">
      <StatusIcon name="alert" size={14} /> {CANT_RUN}
    </span>
  );
}

/** The condition in the colour and with the icon it has on the card. */
function ConditionLine({ condition, line }: { condition: Flow["steps"][number]["condition"]; line: string }) {
  const Icon = CONDITION_ICON[condition];
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap text-[13px] ${CONDITION_COLOUR[condition].text}`}
    >
      <Icon size={14} aria-hidden /> {line}
    </span>
  );
}
