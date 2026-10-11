// One step of a flow. Order in the row is the execution order; there are no
// arrows, and a non-default condition says so in words.
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { ExternalLink, X } from "lucide-react";

import type { Condition, Flow, Preset, Step } from "@/api/types";
import CardValuesBlock from "@/components/ui/CardValuesBlock";
import { DestructiveMark } from "@/components/ui/DestructiveMark";
import StatusIcon from "@/components/ui/StatusIcon";
import { cardValues, stepValues } from "@/lib/cardValues";
import {
  clock,
  elapsed,
  estimateFraction,
  estimateText,
  roundMinutes,
} from "@/lib/time";
import { canChangeSteps } from "@/lib/flowState";
import { CARD_CLASS, borderOf, notStarted, statusOf } from "./cardMetrics";
import { fillLabel } from "./headerState";
import ConditionButton from "./ConditionButton";
import { DriftLink } from "./DriftLink";

/** The row 1 word; a draft has none, what it is sits in its header. */
const cardStatusOf = (step: Step, flowStatus: Flow["status"]) =>
  flowStatus === "draft" ? null : statusOf(step, flowStatus);

/**
 * The inside of a step card. Without callbacks it changes nothing, as on the
 * drag ghost and in History.
 */
export function StepCardBody({
  step,
  flow,
  asked: askedGiven,
  preset,
  onCondition,
  onRemove,
  onFillValues,
  displayPosition = step.position,
}: {
  step: Step;
  flow: Flow;
  /** Position preview while a saved job is held over an insertion slot. */
  displayPosition?: number;
  /** The parameters this step's saved job asks for at launch; without it, those its summary marks. */
  asked?: string[];
  /** The step's saved job: what it sends, and whether Jenkins changed it. */
  preset?: Preset;
  /** Opens the window where the asked values are typed. Absent on a drag ghost. */
  onFillValues?: () => void;
  /** Absent on a drag ghost, which shows the icon and changes nothing. */
  onCondition?: (condition: Condition) => void;
  onRemove?: () => void;
}) {
  const flowStatus = flow.status;
  const draft = flowStatus === "draft";
  const canChange = canChangeSteps(flow);
  const status = cardStatusOf(step, flowStatus);
  const planned = step.state === "planned";
  // Held ones too: a step added to a running flow can be taken off before its review.
  const removable = planned && canChange && onRemove !== undefined;
  const asked = askedGiven ?? step.summary.filter((item) => item.per_run).map((item) => item.name);
  // A value asked at launch belongs to this run, not to the shape of the flow,
  // so a flow that is built and waiting still offers to fill it.
  const answerable = draft && onFillValues !== undefined && asked.length > 0;
  const unfilled = planned ? asked.filter((name) => !(step.run_values[name] ?? "").trim()) : [];
  const empty = unfilled.length;
  const drifted = planned && Boolean(preset?.drift);

  return (
    <>
      <div className="flex min-h-6 flex-wrap items-center gap-x-2 gap-y-1 whitespace-nowrap font-mono text-[13px]">
        {/* Step 1 has no step before it, so it has no condition. */}
        {step.position > 0 && (
          <ConditionButton
            condition={step.condition}
            editable={planned && canChange && (draft || step.held) && onCondition !== undefined}
            onChange={(next) => onCondition?.(next)}
          />
        )}
        <span className="text-dim">STEP {displayPosition + 1}</span>
        {/* A long status beside a condition can be wider than the card: it then
            takes a line of its own, still on the right. */}
        <span className="ml-auto flex items-center">
          {status && (
            <span className={status.wordClass}>
              {status.glyph && (
                <>
                  <StatusIcon
                    name={status.glyph}
                    size={14}
                    className={`${status.glyphClass} ${status.pulse ? "jk-pulse" : ""}`}
                  />{" "}
                </>
              )}
              {status.word}
            </span>
          )}
          {/* Beside the status, never over it; the hit area is wider than the icon. */}
          {removable && (
            <button
              type="button"
              title="Remove step"
              aria-label="Remove step"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={(event) => {
                event.stopPropagation();
                onRemove?.();
              }}
              className="-mr-[5px] inline-flex h-6 w-6 flex-none items-center justify-center text-dim transition-colors duration-150 hover:text-text"
            >
              <X size={14} aria-hidden />
            </button>
          )}
        </span>
      </div>

      {/* "destructive" sits after the name, so the status line above stays one line
          and the values below keep their room; the name gives way first. */}
      <div className="flex min-w-0 items-baseline gap-2">
        <span title={step.preset_name} className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap font-medium">
          {step.preset_name}
        </span>
        {step.destructive && <DestructiveMark className="ml-auto flex-none" />}
      </div>

      {/* The card is one size whatever it holds: the values give way, the footer stays. */}
      <div className="min-h-0 flex-1 overflow-hidden">
        <CardValuesBlock
          values={cardValues(step.summary, unfilled, stepValues(step, preset, asked))}
          clipped
        />
      </div>

      {drifted && <DriftLink presetId={step.preset_id} />}

      {draft ? (
        <div className="flex flex-none items-center justify-between gap-2 font-mono text-[13px] text-dim">
          {answerable && (
            <button
              type="button"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={(event) => {
                event.stopPropagation();
                onFillValues?.();
              }}
              className={
                empty > 0
                  ? "flex h-7 min-w-0 flex-1 items-center rounded-[5px] border border-border px-2 font-sans text-[14px] text-accent transition-colors duration-150 hover:border-dim"
                  : "flex-none self-start font-sans text-[14px] text-dim transition-colors duration-150 hover:text-text"
              }
            >
              {empty > 0 ? fillLabel(empty) : "Edit values"}
            </button>
          )}
          <span className="ml-auto flex-none">{typical(step)}</span>
        </div>
      ) : (
        <StepFooter step={step} flowStatus={flowStatus} />
      )}
    </>
  );
}

/** How long Jenkins expects a step that has not started to take; a guess, so `~`. */
const typical = (step: Step) =>
  step.state === "planned" && step.estimate_ms
    ? `~${roundMinutes(step.estimate_ms)}`
    : "";

function StepFooter({ step, flowStatus }: { step: Step; flowStatus: Flow["status"] }) {
  const running = step.state === "running";
  const finished = ["SUCCESS", "UNSTABLE", "FAILURE", "ABORTED"].includes(
    step.state,
  );

  return (
    <div className="mt-auto font-mono text-[13px] text-dim">
      {running && (
        <div className="mb-1.5 h-[3px] overflow-hidden rounded-xs bg-hairline">
          <div
            className="h-full bg-info transition-[width] duration-[600ms] ease-linear"
            style={{
              width: `${estimateFraction(step.elapsed_ms, step.estimate_ms) * 100}%`,
            }}
          />
        </div>
      )}
      <div className="flex justify-between gap-2">
        <span>
          {running
            ? estimateText(step.elapsed_ms, step.estimate_ms)
            : finished
              ? elapsed(step.elapsed_ms)
              : step.abort_state === "requested"
                ? "abort requested"
                : step.abort_state === "failed"
                  ? "abort request failed"
                  : step.added_while_running
                    ? `added ${clock(step.added_at)} while running`
                    : notStarted(step, flowStatus)
                      ? ""
                      : typical(step)}
        </span>
        {step.build_number !== null && step.build_url && (
          <a
            href={step.build_url}
            target="_blank"
            rel="noreferrer"
            onClick={(event) => event.stopPropagation()}
            className="inline-flex items-center gap-1.5"
          >
            #{step.build_number} <ExternalLink size={13} aria-hidden />
          </a>
        )}
      </div>
    </div>
  );
}

export default function StepCard({
  step,
  flow,
  onOpen,
  asked,
  preset,
  onCondition,
  onRemove,
  onFillValues,
  displayPosition = step.position,
}: {
  step: Step;
  flow: Flow;
  /** Position preview while a saved job is held over an insertion slot. */
  displayPosition?: number;
  /** `card`: where its details open from. */
  onOpen: (step: Step, card: HTMLElement) => void;
  asked: string[];
  preset?: Preset;
  onCondition: (condition: Condition) => void;
  onRemove: () => void;
  onFillValues: () => void;
}) {
  const movable = step.state === "planned" && canChangeSteps(flow);
  // While a flow is edited a card is also a place: a saved job dropped on it
  // takes its number, and this card and the ones after it move aside.
  const place = flow.editing && movable;
  const sortable = useSortable({
    id: step.id,
    disabled: !movable,
    data: place ? { insertInto: flow.id, index: step.position } : undefined,
  });
  const status = cardStatusOf(step, flow.status);

  return (
    <div
      ref={sortable.setNodeRef}
      style={{
        transform: CSS.Translate.toString(sortable.transform),
        transition: sortable.transition,
        opacity: sortable.isDragging ? 0.4 : 1,
      }}
      // Only the pointer listeners: the card inside is the one Tab stop, and
      // dnd-kit's own role and "press space" hints describe no key that works here.
      {...(movable ? sortable.listeners : {})}
      role="listitem"
      className={`${CARD_CLASS} flex`}
    >
      {/* Not a <button>: the card holds controls of its own, and buttons do not nest. */}
      <div
        role="button"
        tabIndex={0}
        data-step-id={step.id}
        aria-label={[`Step ${displayPosition + 1}`, step.preset_name, status?.word]
          .filter(Boolean)
          .join(", ")}
        onClick={(event) => onOpen(step, event.currentTarget)}
        onKeyDown={(event) => {
          if (event.target !== event.currentTarget) return;
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onOpen(step, event.currentTarget);
          }
        }}
        className={`jk-card-in flex w-full cursor-pointer flex-col gap-[7px] overflow-hidden rounded-md border bg-surface px-3 py-2.5 text-left transition-colors duration-150 hover:bg-surface-2 ${borderOf(step)}`}
      >
        <StepCardBody
          step={step}
          displayPosition={displayPosition}
          flow={flow}
          asked={asked}
          preset={preset}
          onCondition={onCondition}
          onRemove={onRemove}
          onFillValues={onFillValues}
        />
      </div>
    </div>
  );
}
