// Every flow that has started, active first. A row opens in place to show its
// run as the Board showed it; nothing here changes a run. A draft is not here:
// it has not run, and it is on the Board.
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import type { Flow } from "@/api/types";
import { useFlows, useRerunFlow } from "@/api/queries";
import { GroupLabel, QuietButton } from "@/components/ui/primitives";
import { isActive } from "@/lib/flowState";
import { headerStateOf } from "@/components/board/headerState";
import { CARD_CLASS, borderOf, statusOf } from "@/components/board/cardMetrics";
import { StepCardBody } from "@/components/board/StepCard";
import StepPopover from "@/components/board/StepPopover";
import { rowTime, startedLine } from "./when";

/**
 * Run again carries its copy so a failed list refresh cannot lose the review.
 * The original stays on the board until the copy starts successfully.
 */
export interface RunAgainState {
  review: Flow;
  source?: string;
}

/** History's own order, whatever order the list came in. */
function newestBy(when: (flow: Flow) => string | null) {
  const stamp = (value: string | null) => (value ? new Date(value).getTime() || 0 : 0);
  return (left: Flow, right: Flow) =>
    stamp(when(right)) - stamp(when(left)) || right.id.localeCompare(left.id);
}

export default function History() {
  const flows = useFlows();
  const rerun = useRerunFlow();
  const navigate = useNavigate();
  const [openId, setOpenId] = useState<string | null>(null);
  const [failed, setFailed] = useState<{ flowId: string; message: string } | null>(null);

  const all = (flows.data ?? []).filter((flow) => flow.status !== "draft");
  // What was taken off the board is over, whatever state it was left in.
  const going = (flow: Flow) => isActive(flow) && !flow.cleared;
  // Runs of one flow share the time it was made, so what ended last is first.
  const active = all.filter(going).sort(newestBy((flow) => flow.created_at));
  const finished = all
    .filter((flow) => !going(flow))
    .sort(newestBy((flow) => flow.finished_at ?? flow.updated_at));

  const runAgain = (flow: Flow) => {
    setFailed(null);
    rerun.mutate(
      { flowId: flow.id },
      {
        onSuccess: (again) =>
          navigate("/", {
            state: {
              review: again,
              source: flow.cleared ? undefined : flow.id,
            } satisfies RunAgainState,
          }),
        onError: (error) => setFailed({ flowId: flow.id, message: error.message }),
      },
    );
  };

  const toggle = (flow: Flow) => setOpenId((open) => (open === flow.id ? null : flow.id));

  return (
    <main className="flex flex-col gap-6 overflow-auto p-7">
      <h1 className="sr-only">History</h1>
      {!flows.isPending && all.length === 0 && (
        <div className="flex flex-col gap-1 text-[14px] text-dim">
          {flows.isError ? (
            <span>{flows.error.message}</span>
          ) : (
            <>
              <span>No runs yet.</span>
              <span>Start one from the board with a saved job or a saved flow.</span>
            </>
          )}
        </div>
      )}
      <Section label="active" flows={active} openId={openId} onToggle={toggle} failed={failed} />
      <Section
        label="finished"
        flows={finished}
        openId={openId}
        onToggle={toggle}
        failed={failed}
        onRerun={runAgain}
        rerunning={rerun.isPending}
      />
    </main>
  );
}

function Section({
  label,
  flows,
  openId,
  onToggle,
  failed,
  onRerun,
  rerunning = false,
}: {
  label: string;
  flows: Flow[];
  openId: string | null;
  onToggle: (flow: Flow) => void;
  failed: { flowId: string; message: string } | null;
  /** Only a flow that has ended can be run again; an active one is still on the board. */
  onRerun?: (flow: Flow) => void;
  /** A copy is being made; Run again waits for it. */
  rerunning?: boolean;
}) {
  if (flows.length === 0) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <GroupLabel>{label}</GroupLabel>
      {flows.map((flow) => {
        const state = headerStateOf(flow);
        const open = openId === flow.id;
        return (
          <div key={flow.id} className="flex flex-col">
            <div className="flex items-baseline gap-3.5 rounded-md px-3 py-2 transition-colors duration-150 hover:bg-surface">
              <button
                type="button"
                aria-expanded={open}
                onClick={() => onToggle(flow)}
                className="flex min-w-0 flex-1 items-baseline gap-3.5"
              >
                <span className="font-medium">{flow.name}</span>
                <span className={`font-mono text-[13px] ${state.tone}`}>{state.word}</span>
              </button>
              {onRerun && (
                <QuietButton onClick={() => onRerun(flow)} disabled={rerunning}>
                  Run again
                </QuietButton>
              )}
              <span className="whitespace-nowrap font-mono text-[13px] text-dim">{rowTime(flow)}</span>
            </div>
            {failed?.flowId === flow.id && (
              <div className="px-3 pb-2 text-[14px] text-warn">{failed.message}</div>
            )}
            {open && <Run flow={flow} />}
          </div>
        );
      })}
    </div>
  );
}

/** The run's step cards as the Board showed them. A click shows what a step sent. */
function Run({ flow }: { flow: Flow }) {
  // The card it opened from: the details open where they fit, and a second press closes them.
  const [openStep, setOpenStep] = useState<{ id: string; card: HTMLElement } | null>(null);
  const toggle = (step: string, card: HTMLElement) =>
    setOpenStep((open) => (open?.id === step ? null : { id: step, card }));

  return (
    <div className="flex flex-col gap-3 px-3 pb-4 pt-1">
      <div className="flex items-baseline gap-3.5">
        <span className="font-mono text-[13px] text-dim">{startedLine(flow)}</span>
        {!flow.cleared && (
          <Link to={`/#flow-${flow.id}`} className="text-[14px]">
            Open on the board
          </Link>
        )}
      </div>
      <div className="flex flex-wrap items-start gap-3" role="list">
        {flow.steps.map((step) => (
          <div key={step.id} role="listitem" className="relative flex">
            {/* Not a <button>: the card holds a build link, and links do not nest in buttons. */}
            <div
              role="button"
              tabIndex={0}
              aria-expanded={openStep?.id === step.id}
              aria-label={`Step ${step.position + 1}, ${step.preset_name}, ${statusOf(step, flow.status).word}`}
              onClick={(event) => toggle(step.id, event.currentTarget)}
              onKeyDown={(event) => {
                if (event.target !== event.currentTarget) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  toggle(step.id, event.currentTarget);
                }
              }}
              className={`${CARD_CLASS} flex cursor-pointer flex-col gap-[7px] overflow-hidden rounded-md border bg-surface px-3 py-2.5 text-left transition-colors duration-150 hover:bg-surface-2 ${borderOf(step)}`}
            >
              <StepCardBody step={step} flow={flow} />
            </div>
            {openStep?.id === step.id && (
              <StepPopover readOnly step={step} anchor={openStep.card} onClose={() => setOpenStep(null)} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
